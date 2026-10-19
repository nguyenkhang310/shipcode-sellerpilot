// Isolated UI fixture, no installed extension, Shopee account, backend or model calls.
// Only the browser-origin predicate in the served test bundle is rewritten; the
// production package on disk and the message transport are not modified.
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const root = path.resolve(__dirname, '../dist');
const output = path.resolve(__dirname, '../../../docs/evaluations/extension-panel');
const origin = 'https://sellerpilot.extension.test';
(async () => {
  const browser = await chromium.launch({headless: true, executablePath: process.env.CHROME_EXECUTABLE || undefined});
  try {
    fs.mkdirSync(output, {recursive: true});
    const errors = [], outgoing = [], checks = [];
    const page = await browser.newPage({viewport: {width: 380, height: 760}});
    page.on('pageerror', e => errors.push(e.message));
    await page.addInitScript(() => {
      const id = '12345678-1234-1234-1234-123456789abc';
      const connection = {id, mode: 'shopee', tab_id: 7, tab_status: 'linked', target_matches: true, document_id: 'fixture', page_context: 'fixture-context', target: {label: 'fixture-shop'}};
      window.fixtureConnection = connection;
      window.rpcCalls = [];
      const turns = [];
      window.chrome = {runtime: {sendMessage: async message => {
        window.rpcCalls.push(message);
        const ok = data => ({ok: true, data: structuredClone(data)});
        if (message.kind === 'connection' || message.kind === 'connection_status') return ok(connection);
        if (message.kind === 'list_scopes') return ok([]);
        if (message.kind === 'scan') return ok({document_id: 'fixture', page_context: 'fixture-context', target: connection.target,
          snapshot: {url: 'https://banhang.shopee.vn/', captured_at: new Date().toISOString()},
          fields: [], metrics: [{label: 'Doanh số', value: '1.500.000đ'}, {label: 'Đơn hàng', value: '2'}],
          tables: [[['Sản phẩm', 'Giá'], ['Bàn phím', '500.000đ']], [['Mã đơn hàng', 'Tổng tiền'], ['ORDER-1', '500.000đ']]]});
        if (message.kind === 'backend_health') return ok({status: 'ok'});
        if (message.kind !== 'api') return {ok: false, error: 'Unexpected fixture RPC: ' + message.kind};
        if (message.path === '/conversations') return ok({data: {items: turns.length ? [{id, title: turns[0].message, updated_at: new Date().toISOString(), turns: turns.length}] : []}});
        if (message.path === '/conversations/' + id) return ok({data: {id, turns}});
        if (message.path === '/chat') {
          const body = JSON.parse(message.body);
          await new Promise(resolve => setTimeout(resolve, 900));
          const data = {run_id: 1, conversation_id: id, answer: 'Phân tích từ dữ liệu trang hiện tại.\n\n' + Array.from({length: 24}, (_, i) => 'Mục ' + (i + 1) + ': Kiểm tra tồn kho và ưu tiên sản phẩm.').join('\n\n'), intent: 'sales_advice', mode: 'ai', provider: 'gemini', model: 'fixture', fallback_reason: null, facts: {}, proposal: null, product_draft: null, integration_mode: 'shopee_browser', suggestions: []};
          turns.push({message: body.message, response: data, created_at: new Date().toISOString()});
          return ok({data});
        }
        return {ok: false, status: 404, error: 'No fixture route: ' + message.path};
      }}};
    });
    await page.route('**/*', async route => {
      const url = new URL(route.request().url());
      if (url.origin !== origin) {outgoing.push(url.origin + url.pathname); return route.abort();}
      const filename = path.resolve(root, '.' + decodeURIComponent(url.pathname === '/' ? '/index.html' : url.pathname));
      if (!filename.startsWith(root + path.sep) || !fs.existsSync(filename)) return route.fulfill({status: 404, body: 'Not found'});
      let body = fs.readFileSync(filename);
      const ext = path.extname(filename);
      if (ext === '.js' && url.pathname.includes('/expo/static/')) {
        const source = body.toString();
        const predicate = /(['"])chrome-extension:\1===location\.protocol/g;
        assert.equal([...source.matchAll(predicate)].length, 1, 'test origin rewrite must stay narrow');
        body = Buffer.from(source.replace(predicate, "'https:'===location.protocol"));
      }
      const mime = {'.html': 'text/html; charset=utf-8', '.js': 'application/javascript', '.png': 'image/png', '.ttf': 'font/ttf', '.ico': 'image/x-icon'};
      return route.fulfill({contentType: mime[ext] || 'application/octet-stream', body});
    });
    await page.goto(origin, {waitUntil: 'networkidle'});
    await page.getByTestId('extension-shell').waitFor();
    assert.equal(await page.getByTestId('bottom-dock').count(), 0);
    assert.equal(await page.getByText('SellerPilot', {exact: true}).count(), 1);
    await page.getByRole('button', {name: 'Cập nhật', exact: true}).click();
    await page.getByRole('tab', {name: 'Tổng quan', exact: true}).click();
    await page.getByText('1.500.000đ', {exact: true}).waitFor();
    await page.evaluate(() => {window.fixtureConnection.target_matches = false;});
    await page.getByText('Kiểm tra lại tài khoản Shopee', {exact: true}).waitFor();
    assert.equal(await page.getByText('1.500.000đ', {exact: true}).count(), 0, 'account mismatch must clear old metrics');
    await page.evaluate(() => {window.fixtureConnection.target_matches = true;});
    await page.getByText('1.500.000đ', {exact: true}).waitFor();
    await page.getByRole('tab', {name: 'Sản phẩm', exact: true}).click();
    await page.getByText('Bàn phím', {exact: true}).waitFor();
    await page.getByRole('tab', {name: 'Đơn hàng', exact: true}).click();
    await page.getByText('ORDER-1', {exact: true}).waitFor();
    await page.getByRole('tab', {name: 'Shop', exact: true}).click();
    await page.getByText('Liên kết trình duyệt · Chưa cấp quyền Open API', {exact: true}).waitFor();
    await page.getByRole('tab', {name: 'Trợ lý', exact: true}).click();
    const input = page.getByRole('textbox', {name: 'Nhắn cho SellerPilot'});
    for (const width of [320, 380, 520]) {
      await page.setViewportSize({width, height: 760});
      await input.fill(Array.from({length: 14}, (_, i) => 'Dòng ' + i + ': mô tả sản phẩm tiếng Việt').join('\n'));
      await page.waitForFunction(() => document.querySelector('textarea').clientHeight >= 100);
      const field = await input.boundingBox(), composer = await page.getByTestId('chat-composer').boundingBox();
      assert(field.height <= 129 && field.y + field.height <= 760, 'composer stays inside side panel');
      assert(composer.x >= 0 && composer.x + composer.width <= width + 1, 'composer fits panel width');
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > innerWidth + 1), false);
      await input.fill('Ngắn');
      await page.waitForFunction(() => document.querySelector('textarea').clientHeight <= 50);
      await page.screenshot({path: path.join(output, 'panel-' + width + '.png')});
    }
    checks.push('Compact header, five desktop tabs, no floating mobile dock, structured metrics/product/order tables; 320/380/520px widths');
    await page.setViewportSize({width: 380, height: 760});
    await input.fill('Phân tích số liệu trang này');
    await page.getByRole('button', {name: 'Gửi tin nhắn', exact: true}).click();
    await page.getByTestId('typing-indicator').waitFor();
    await page.getByTestId('typing-indicator').waitFor({state: 'detached'});
    await page.waitForFunction(() => {const el = document.querySelector('[data-testid="chat-scroll"]'); return el.scrollHeight - el.scrollTop - el.clientHeight < 12;});
    await page.getByRole('button', {name: 'Lịch sử trò chuyện', exact: true}).click();
    await page.getByTestId('chat-history-panel').waitFor();
    await page.getByRole('button', {name: 'Đóng lịch sử', exact: true}).click({position: {x: 375, y: 300}});
    await page.getByTestId('chat-history-panel').waitFor({state: 'detached'});
    await page.getByRole('button', {name: 'Cài đặt kết nối', exact: true}).click();
    await page.getByRole('button', {name: 'Chọn tài khoản trên trang', exact: true}).waitFor();
    await page.waitForFunction(() => document.getAnimations().every(animation => animation.playState !== 'running'));
    await page.screenshot({path: path.join(output, 'connection.png')});
    await page.getByRole('button', {name: 'Đóng kết nối', exact: true}).click();
    const apiCalls = await page.evaluate(() => window.rpcCalls.filter(row => row.kind === 'api').map(row => row.path));
    assert(!apiCalls.some(value => value.startsWith('/management/')), 'Shopee shell must not load local dashboard API');
    assert.deepEqual(errors, []); assert.deepEqual(outgoing, []);
    checks.push('Multiline input grows/shrinks, typing feedback, long-answer autoscroll, history modal and connection modal; no local management calls or real network');
    const result = {checks, errors, outgoing};
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result, null, 2));
  } catch (error) {
    const pages = browser.contexts().flatMap(context => context.pages());
    if (pages[0]) {console.error((await pages[0].locator('body').innerText()).slice(0, 4000)); await pages[0].screenshot({path: path.join(output, 'failure.png')});}
    throw error;
  } finally {await browser.close();}
})().catch(error => {console.error(error); process.exitCode = 1;});
