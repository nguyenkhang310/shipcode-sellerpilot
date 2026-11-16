const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { snapshot, mockApi, enterApp } = require('./management-fixture.cjs');
const output = path.resolve(__dirname, '../../docs/evaluations/chat-motion');
fs.mkdirSync(output, { recursive: true });
let browser, page, releaseChat;
(async () => {
  browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await mockApi(page, (route, days, headers) => route.fulfill({ headers, json: { data: snapshot(days) } }));
  let productReads = 0;
  const products = Array.from({ length: 20 }, (_, i) => ({ id: i + 1, name: 'Sản phẩm kiểm tra chuyển mục ' + i, sku: 'QA-' + i, price_vnd: 500000, stock: 20, sold_count: 10, image_url: null, status: 'active' }));
  await page.route('**/api/v1/management/products?*', route => { productReads++; return route.fulfill({ headers: { 'Access-Control-Allow-Origin': '*' }, json: { data: { items: products, total: products.length } } }); });
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  await enterApp(page);
  const names = { 'Quản lý': 'home', 'Sản phẩm': 'products', 'Đơn hàng': 'orders', Shop: 'shop', SellerPilot: 'assistant' };
  let scrollTop;
  for (const name of ['Sản phẩm', 'Đơn hàng', 'Shop', 'Quản lý', 'SellerPilot', 'Quản lý', 'SellerPilot']) {
    const tab = page.getByRole('tab', { name, exact: true });
    await tab.click(); assert.equal(await tab.getAttribute('aria-selected'), 'true');
    const state = await page.getByTestId('tab-scene-' + names[name]).evaluate(el => {
      let opaque = true;
      for (let node = el; node; node = node.parentElement) if (+getComputedStyle(node).opacity < .999) opaque = false;
      return { opaque, transform: getComputedStyle(el).transform, visible: el.getClientRects().length > 0 };
    });
    assert(state.visible && state.opaque && state.transform === 'none', 'Tab content appears immediately without a fade/slide: ' + name);
    assert.equal(await page.locator('[data-testid^="tab-scene-"]').evaluateAll(nodes => nodes.filter(el => getComputedStyle(el).display !== 'none').length), 1);
    if (name === 'Sản phẩm') {
      await page.getByTestId('product-card-20').waitFor();
      scrollTop = await page.getByTestId('tab-scene-products').evaluate(el => {
        const scroll = [...el.querySelectorAll('div')].find(node => getComputedStyle(node).overflowY === 'auto');
        scroll.scrollTop = 400; return scroll.scrollTop;
      });
    }
  }
  await page.getByRole('tab', { name: 'Sản phẩm', exact: true }).click();
  assert.equal(productReads, 1, 'Warm tab return must not re-fetch/rebuild all product cards');
  const restoredScroll = await page.getByTestId('tab-scene-products').evaluate(el => [...el.querySelectorAll('div')].find(node => getComputedStyle(node).overflowY === 'auto').scrollTop);
  assert(Math.abs(restoredScroll - scrollTop) < 1, 'Product scroll position is preserved');
  await page.getByRole('tab', { name: 'Quản lý', exact: true }).click();
  await page.getByRole('button', { name: 'Đồng bộ số liệu', exact: true }).click();
  const refreshedProducts = page.waitForResponse(response => new URL(response.url()).pathname.endsWith('/management/products'));
  await page.getByRole('tab', { name: 'Sản phẩm', exact: true }).click();
  await refreshedProducts;
  await page.waitForFunction(() => document.querySelector('[data-testid="product-card-20"]'));
  await page.getByTestId('tab-scene-products').getByRole('progressbar').waitFor({ state: 'hidden' });
  assert.equal(productReads, 2, 'An explicit shop refresh invalidates the warm product tab');
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  const input = page.getByRole('textbox', { name: 'Nhắn cho SellerPilot', exact: true });
  await input.fill('Bản nháp cần giữ nguyên');
  for (let index = 0; index < 4; index++) {
    await page.getByRole('button', { name: 'Lịch sử trò chuyện', exact: true }).click();
    const panel = page.getByTestId('chat-history-panel');
    await panel.waitFor();
    await panel.getByRole('button', { name: 'Đóng lịch sử trò chuyện', exact: true }).click();
    await panel.waitFor({ state: 'hidden' });
    assert.equal(await input.inputValue(), 'Bản nháp cần giữ nguyên');
  }
  checks.push('Chuyển tab và mở/đóng lịch sử liên tục không để màn hình trống, lớp che hay mất bản nháp');
  checks.push('Nội dung tab hiện đầy đủ ngay, chỉ một tab tương tác; giữ vị trí cuộn và tránh tải lại sản phẩm vừa xem; đồng bộ thủ công vẫn làm mới danh mục');
  const long = Array.from({ length: 55 }, (_, i) => `Dòng ${i + 1}: mô tả sản phẩm và các thông tin cần gửi.`).join('\n');
  await input.fill(long);
  await input.pressSequentially('\nDÒNG CUỐI ĐANG NHẬP', { delay: 15 });
  await page.waitForTimeout(250);
  const geometry = await input.evaluate(el => ({ height: el.clientHeight, top: el.scrollTop,
    content: el.scrollHeight, cursor: el.selectionStart, length: el.value.length }));
  assert(geometry.height >= 100 && geometry.height <= 129, JSON.stringify(geometry));
  assert.equal(geometry.cursor, geometry.length);
  assert(geometry.content - geometry.top - geometry.height < 30, 'The last input line and caret must stay visible: ' + JSON.stringify(geometry));
  const field = await input.boundingBox(), dock = await page.getByTestId('bottom-dock').boundingBox();
  assert(field.y + field.height < dock.y);
  await page.screenshot({ path: path.join(output, 'long-composer.png') });
  await input.fill('Gọn'); await page.waitForFunction(() => document.querySelector('textarea').clientHeight <= 50);
  checks.push('Input 55 dòng cuộn theo con trỏ, dòng cuối còn nhìn thấy; xóa ngắn lại thì khung co đúng');
  let cancelled = 0;
  await page.route('**/api/v1/chat/requests/*/cancel', route => { cancelled++; return route.fulfill({ json: { data: {} } }); });
  await page.route('**/api/v1/chat', async route => {
    const request = route.request().postDataJSON();
    await new Promise(resolve => { releaseChat = resolve; });
    return route.fulfill({ headers: { 'Access-Control-Allow-Origin': '*' }, json: { data: { run_id: 101, conversation_id: request.conversation_id,
      answer: 'Phản hồi vẫn được giữ khi bạn chuyển tab.', intent: 'shop_summary', mode: 'ai', provider: 'gemini', model: 'fixture', fallback_reason: null,
      tool: null, facts: {}, proposal: null, product_draft: null, integration_mode: 'local_store', suggestions: [] } } });
  });
  await input.fill('Thống kê giúp mình');
  await page.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
  await page.getByTestId('typing-indicator').waitFor();
  await page.waitForFunction(() => +getComputedStyle(document.querySelector('[data-testid="typing-dot-0"]')).opacity > .5);
  await page.getByRole('tab', { name: 'Đơn hàng', exact: true }).click();
  await page.waitForFunction(() => +getComputedStyle(document.querySelector('[data-testid="typing-dot-0"]')).opacity <= .41);
  assert.equal(cancelled, 0, 'Changing tabs must not cancel the chat request');
  releaseChat();
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  await page.getByText('Phản hồi vẫn được giữ khi bạn chuyển tab.', { exact: true }).waitFor();
  checks.push('Ba chấm dừng khi rời tab Trợ lý; yêu cầu AI tiếp tục và phản hồi vẫn xuất hiện khi quay lại');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.getByRole('tab', { name: 'Quản lý', exact: true }).click();
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  await input.fill('Vẫn nhập bình thường');
  assert.equal(await input.inputValue(), 'Vẫn nhập bình thường');
  checks.push('Bật Giảm chuyển động vẫn thao tác được bình thường');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ checks, geometry, errors }, null, 2));
  console.log(JSON.stringify({ checks, geometry, errors }, null, 2));
  await browser.close();
})().catch(async error => {
  releaseChat?.();
  console.error(error);
  if (page) { console.error((await page.locator('body').innerText()).slice(-2000)); await page.screenshot({ path: path.join(output, 'failure.png') }); }
  if (browser) await browser.close(); process.exit(1);
});
