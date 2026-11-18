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
    assert.equal((await message({kind: 'auto_detect_target'})).data.label, null, 'Unknown header layout requires explicit selection');
    await page.locator('#account').evaluate(el => {el.className = 'user-name';});
    assert.equal((await message({kind: 'auto_detect_target'})).data.label, 'fixture-shop');
    await page.evaluate(() => {
      const other = document.createElement('span'); other.className = 'shop-name'; other.id = 'other-account';
      other.textContent = 'other-shop'; document.querySelector('header').append(other);
    });
    assert.equal((await message({kind: 'auto_detect_target'})).data.label, null, 'Two visible account labels cannot be auto-selected');
    assert.equal((await message({kind: 'read'})).ok, false, 'Conflicting account headers block reads and writes');
    await page.locator('#other-account').evaluate(el => el.remove());
    await page.locator('#account').evaluate(el => {el.hidden = true;});
    assert.equal((await message({kind: 'target_status'})).data.target_check, 'unverified');
    const waitingRead = await message({kind: 'read'});
    assert.equal(waitingRead.ok, false); assert.equal(waitingRead.code, 'target_unverified');
    await page.locator('#account').evaluate(el => {el.hidden = false;});
    assert.equal((await message({kind: 'target_status'})).data.target_check, 'matched');
    await page.evaluate(() => {const duplicate = document.createElement('span'); duplicate.id = 'account-badge'; duplicate.textContent = 'fixture-shop'; document.body.append(duplicate);});
    assert.equal((await message({kind: 'target_status'})).data.target_check, 'matched', 'A repeated badge outside the account header is not an account change');
    await page.locator('#account-badge').evaluate(el => el.remove());
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
    assert.equal((await message({kind: 'target_status'})).data.target_check, 'mismatch');
    assert.equal((await message({kind: 'read'})).ok, false);
    assert.equal((await message({kind: 'fill', document_id: snapshot.data.document_id, url: snapshot.data.snapshot.url, draft})).ok, false);
    await page.locator('#account').evaluate(el => {el.textContent = 'fixture-shop';});
    // Discover real menu hrefs and traverse pagination without submitting a form.
    await page.evaluate(() => {
      const aside = document.createElement('aside');
      aside.innerHTML = '<a href="/observed-catalog">Tất cả sản phẩm</a><a href="https://evil.example/">Tất cả đơn hàng</a>';
      document.body.append(aside);
      document.querySelector('main').innerHTML = '<h1>Tất cả sản phẩm</h1><table><thead><tr><th>Sản phẩm</th><th>SKU</th><th>Tồn kho</th><th>Điện thoại</th></tr></thead><tbody><tr><td>Bàn phím</td><td>K1</td><td>3</td><td>0900000000</td></tr></tbody></table><nav class="pagination"><button aria-current="page">1</button><button>2</button><button id="next" aria-label="Trang sau">→</button></nav>';
      document.querySelector('#next').addEventListener('click', () => {
        document.querySelector('tbody').innerHTML = '<tr><td>Chuột</td><td>M1</td><td>0</td><td>0900000000</td></tr>';
        document.querySelector('[aria-current]').removeAttribute('aria-current');
        document.querySelectorAll('.pagination button')[1].setAttribute('aria-current', 'page');
        document.querySelector('#next').disabled = true;
      });
    });
    const firstPage = await message({kind: 'read'});
    assert.equal(firstPage.data.navigation.products, 'https://banhang.shopee.vn/observed-catalog');
    assert.equal(firstPage.data.navigation.orders, null);
    assert.equal(firstPage.data.pagination.current, 1);
    assert.equal(firstPage.data.inventory[0].sku, 'K1');
    assert.equal(firstPage.data.inventory[0].stock, '3');
    assert(!JSON.stringify(firstPage.data).includes('0900000000'));
    const turn = await message({kind: 'next_page', document_id: firstPage.data.document_id, page_context: firstPage.data.page_context});
    assert(turn.ok, turn.error);
    const secondPage = await message({kind: 'read'});
    assert.equal(secondPage.data.pagination.current, 2); assert.equal(secondPage.data.pagination.at_last, true);
    assert.equal(secondPage.data.inventory[0].stock, '0');
    assert.equal(await page.evaluate(() => window.submitted), false);
    // Div-based seller tables must follow the same strict header allowlist.
    await page.evaluate(() => {
      document.querySelector('main').innerHTML = '<div class="shopee-table"><div class="shopee-table__header"><div class="shopee-table__row"><div class="shopee-table__cell">Sản phẩm</div><div class="shopee-table__cell">Tồn kho</div></div></div><div class="shopee-table__body"><div class="shopee-table__row"><div class="shopee-table__cell"><a href="/portal/product/123/edit">Tai nghe</a></div><div class="shopee-table__cell">5</div></div></div></div>';
    });
    const divTable = await message({kind: 'read'});
    assert.equal(divTable.data.inventory[0].key, 'product:123');
    assert.equal(divTable.data.inventory[0].stock, '5');
    // A normal product editor must remain untouched until an explicit fill.
    await page.evaluate(() => {
      history.replaceState(null, '', '/portal/product/new');
      document.querySelector('main').innerHTML = '<form><label>Tên sản phẩm<input id="name" value="Tên gốc"></label><label>Mô tả<textarea id="description">Giữ nguyên mô tả ngắn.</textarea></label><label>Giá bán<input id="price" value="350000"></label><div class="eds-form-item is-required"><label>Kho hàng<input id="stock" value="0"></label></div><label>Trọng lượng (g)<input id="weight"></label><input id="photos" type="file" accept="image/png" multiple><button type="submit">Lưu & Hiển thị</button></form>';
      window.uploadChanges = 0;
      document.querySelector('#photos').addEventListener('change', () => window.uploadChanges++);
    });
    await page.waitForTimeout(1700);
    assert.equal(await page.locator('#price').inputValue(), '350000');
    assert.equal(await page.locator('#stock').inputValue(), '0');
    assert.equal(await page.locator('#description').inputValue(), 'Giữ nguyên mô tả ngắn.');
    const formPage = await message({kind: 'read'}); pageContext = formPage.data.page_context;
    const scan = await message({kind: 'scan_required'});
    assert(!scan.data.missing_fields.includes('Kho hàng'), 'Zero inventory is valid and must never become a default positive quantity');
    assert.equal((await message({kind: 'scan_required', target: {label: 'wrong-shop'}})).ok, false);
    assert.equal((await message({kind: 'fill', document_id: 'stale', bypass_context_check: true, url: formPage.data.snapshot.url, draft: {price_vnd: 1}})).ok, false);
    const image = 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScLbtAAAAABJRU5ErkJggg==';
    const imageFill = await message({kind: 'fill', document_id: formPage.data.document_id, url: formPage.data.snapshot.url,
      draft: {name: 'Tên người bán', description: 'Giữ nguyên mô tả ngắn.', price_vnd: 350000, stock: 0, weight_g: 250, images: [image]}});
    assert(imageFill.ok, imageFill.error);
    assert.equal(imageFill.data.submitted, false);
    assert.equal(imageFill.data.images, 'handed_to_uploader');
    assert.equal(await page.evaluate(() => window.uploadChanges), 1, 'An image must not be uploaded once via change and again via synthetic drop');
    assert.equal(await page.locator('#weight').inputValue(), '250');
    assert.equal(await page.locator('#stock').inputValue(), '0');
    await page.evaluate(() => {const input = document.createElement('input'); input.type = 'password'; document.body.append(input);});
    assert.equal((await message({kind: 'read'})).ok, false);
    console.log('Passed: trusted account selection, account mismatch read/write guards, structured metrics/tables, private-data exclusion, native field events, Vietnamese multiline, stale document, no submit.');
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
