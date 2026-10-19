// DOM regression on intercepted fixture HTML, never a real authenticated Shopee page.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_EXECUTABLE || undefined});
  try {
    const page = await browser.newPage();
    await page.route('https://banhang.shopee.vn/**', route => route.fulfill({contentType: 'text/html', body: `<!doctype html><html lang="vi"><meta charset="utf-8"><title>private title</title><body><header><button><span id="account">fixture-shop</span></button></header><main>
      <p>Private customer: Nguyen Example, 0900000000, 123 private street</p>
      <div><span>Doanh số</span><strong>1.500.000đ</strong></div><div><span>Đơn hàng</span><strong>2</strong></div>
      <form><label>Tên sản phẩm<input id="name" /></label><label>Mô tả sản phẩm<textarea id="description"></textarea></label>
      <label>Giá bán<input id="price" type="text" /></label><label>Tồn kho<input id="stock" type="number" /></label>
      <button type="submit">Lưu & Hiển thị</button></form>
      <table><thead><tr><th>Sản phẩm</th><th>Giá</th><th>Người mua</th><th>Điện thoại</th></tr></thead><tbody><tr><td>Bàn phím</td><td>500.000đ</td><td>Nguyen Example</td><td>0900000000</td></tr></tbody></table>
      </main></body></html>`}));
    await page.goto('https://banhang.shopee.vn/?secret=private-query');
    await page.evaluate(() => {
      window.targetMessages = [];
      window.chrome = {runtime: {id: 'test', onMessage: {addListener: value => {window.listener = value;}}, sendMessage: async value => {window.targetMessages.push(value); return {ok: true};}}};
      window.submitted = false; window.eventsSeen = [];
      document.querySelector('form').addEventListener('submit', event => {event.preventDefault(); window.submitted = true;});
      document.addEventListener('input', event => window.eventsSeen.push(event.target.id));
    });
    await page.addScriptTag({content: fs.readFileSync(path.resolve(__dirname, '../content/shopee.js'), 'utf8')});
    const target = {label: 'fixture-shop'};
    let pageContext;
    const message = value => page.evaluate(value => new Promise(resolve => window.listener(value, {id: 'test'}, resolve)), {target, page_context: pageContext, ...value});
    assert.equal((await message({kind: 'read', target: null})).ok, false);
    assert.equal((await message({kind: 'read', target: {label: 'other-shop'}})).ok, false);
    const nonce = '12345678-1234-1234-1234-123456789abc';
    await message({kind: 'select_target', nonce});
    await page.evaluate(() => document.querySelector('#account').click());
    assert.equal(await page.evaluate(() => window.targetMessages.length), 0, 'synthetic clicks cannot select an account');
    await page.locator('#account').click();
    assert.equal(await page.evaluate(() => window.targetMessages[0].nonce), nonce);
    const snapshot = await message({kind: 'read'});
    pageContext = snapshot.data.page_context;
    assert(snapshot.ok); assert.equal(snapshot.data.fields.length, 4);
    const serialized = JSON.stringify(snapshot.data);
    for (const secret of ['Nguyen Example', '0900000000', 'private street', 'private-query', 'private title']) assert(!serialized.includes(secret), secret);
    assert.deepEqual(snapshot.data.tables[0], [['Sản phẩm', 'Giá'], ['Bàn phím', '500.000đ']]);
    assert.deepEqual(snapshot.data.metrics, [{label: 'Doanh số', value: '1.500.000đ'}, {label: 'Đơn hàng', value: '2'}]);
    assert.equal(JSON.parse(snapshot.data.snapshot.text).period, 'unverified');
    const status = await message({kind: 'target_status'});
    assert.equal(status.data.target_matches, true);
    assert.equal(status.data.page_context, snapshot.data.page_context);
    await page.evaluate(() => {
      const duplicate = document.createElement('div'); duplicate.id = 'duplicate-metric';
      duplicate.innerHTML = '<span>Doanh số</span><strong>9.000.000đ</strong>';
      document.querySelector('main').append(duplicate);
    });
    assert.equal((await message({kind: 'read'})).data.metrics.some(row => row.label === 'Doanh số'), false, 'duplicate metrics are ambiguous and must not be guessed');
    await page.locator('#duplicate-metric').evaluate(el => el.remove());
    const draft = {name: 'Bàn phím trắng', description: 'Dòng một\nDòng hai tiếng Việt', price_vnd: 500000, stock: 12};
    const filled = await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft});
    assert(filled.ok, filled.error);
    assert(filled.data.report.every(row => row.status === 'filled'), JSON.stringify(filled.data));
    assert.equal(await page.locator('#description').inputValue(), draft.description);
    assert.equal(await page.locator('#price').inputValue(), '500000');
    assert.equal(await page.evaluate(() => window.submitted), false);
    assert.deepEqual(await page.evaluate(() => window.eventsSeen), ['name', 'description', 'price', 'stock']);
    // Two matching prices must be rejected, rather than silently updating the wrong variant.
    await page.evaluate(() => {const label = document.createElement('label'); label.innerHTML = 'Giá bán<input>'; document.querySelector('form').append(label);});
    const ambiguous = await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft: {price_vnd: 700000}});
    assert.equal(ambiguous.data.report[0].status, 'unmapped');
    const stale = await message({kind: 'fill', document_id: 'old-document', url: snapshot.data.snapshot.url, draft});
    assert.equal(stale.ok, false);
    // A controlled field that rejects the synthetic input cannot be marked retained.
    await page.evaluate(() => document.querySelector('#stock').addEventListener('input', event => {event.target.value = '1';}));
    const rejected = await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft: {stock: 20}});
    assert.equal(rejected.data.report[0].status, 'not_retained');
    await page.evaluate(() => history.replaceState(null, '', '?secret=changed-private-query'));
    assert.equal((await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft})).ok, false, 'query-only navigation invalidates form fill without exposing query values');
    await page.evaluate(() => history.replaceState(null, '', '?secret=private-query'));
    await page.locator('#account').evaluate(el => {el.textContent = 'different-shop';});
    assert.equal((await message({kind: 'target_status'})).data.target_matches, false);
    assert.equal((await message({kind: 'read'})).ok, false);
    assert.equal((await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft})).ok, false);
    await page.locator('#account').evaluate(el => {el.textContent = 'fixture-shop';});
    await page.evaluate(() => {const input = document.createElement('input'); input.type = 'password'; document.body.append(input);});
    assert.equal((await message({kind: 'read'})).ok, false);
    console.log('Passed: trusted account selection, account mismatch read/write guards, structured metrics/tables, private-data exclusion, native field events, Vietnamese multiline, stale document, no submit.');
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
