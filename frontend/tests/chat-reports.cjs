// Uses the disposable chat_reliability_server.py only; never a real seller shop.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path');
const { randomUUID } = require('node:crypto');
const { enterApp } = require('./management-fixture.cjs');
const origin = process.env.QA_API_ORIGIN || 'http://127.0.0.1:8123';
const output = path.resolve(__dirname, '../../docs/evaluations/chat-reports');
fs.mkdirSync(output, { recursive: true });
let browser, page;
(async () => {
  browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_EXECUTABLE || undefined });
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  page.setDefaultTimeout(30000);
  assert.equal((await (await page.request.get(origin + '/qa/identity')).json()).temporary_shop, true);
  const errors = [], reports = [];
  page.on('pageerror', error => errors.push(error.message));
  const headers = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
  await page.route('**/api/v1/**', async route => {
    const request = route.request(), url = new URL(request.url());
    if (request.method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    if (url.pathname.endsWith('/auth/login')) return route.fulfill({ headers, json: { data: {
      token: 'synthetic-report-qa', user: { id: 1, username: 'qa-seller', email: 'qa@example.test' },
      shop: { slug: 'utech-official', name: 'Gian hàng QA', role: 'owner' }, expires_at: '2099-01-01T00:00:00Z',
    } } });
    const response = await route.fetch({ url: origin + url.pathname + url.search });
    if (url.pathname.endsWith('/chat') && response.ok()) reports.push((await response.json()).data.report);
    await route.fulfill({ response, headers: { ...response.headers(), ...headers } });
  });
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174');
  await enterApp(page);
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  async function send(message) {
    const previous = await page.getByTestId('chat-report').count();
    await page.getByRole('textbox', { name: 'Nhắn cho SellerPilot' }).fill(message);
    await page.getByRole('button', { name: 'Gửi tin nhắn', exact: true }).click();
    await page.waitForFunction(count => document.querySelectorAll('[data-testid="chat-report"]').length === count + 1, previous);
    return page.getByTestId('chat-report').last();
  }
  const sales = await send('Vẽ biểu đồ doanh thu 7 ngày qua');
  const report = reports.at(-1);
  const header = sales.getByRole('heading', { name: 'Hiệu quả kinh doanh' });
  await page.waitForFunction(() => {
    const report = document.querySelector('[data-testid="chat-report"]');
    const scroll = document.querySelector('[data-testid="chat-scroll"]');
    return report.getBoundingClientRect().top >= scroll.getBoundingClientRect().top;
  });
  assert(await header.isVisible(), 'A new report must open at its beginning, not its footer');
  assert.equal(await page.getByRole('button', { name: 'Cuộn đến tin nhắn mới nhất', exact: true }).count(), 0,
    'The latest-message button must not cover report controls during automatic positioning');
  assert.equal(await sales.getByTestId('chat-report-chart').count(), 1, 'Only one visualization at a time');
  assert.equal(await sales.getByTestId('chat-report-table').count(), 0);
  assert.equal(await sales.getByTestId('chat-report-metric').count(), 2, 'Only two headline metrics');
  assert((await sales.boundingBox()).height < 620, 'Default report must fit a compact chat card');
  assert.equal(report.metrics[0].value, report.charts[0].points.reduce((sum, p) => sum + p.value, 0));
  assert.match(await sales.innerText(), new RegExp(report.metrics[0].value.toLocaleString('vi-VN')));
  const trend = sales.getByTestId('chat-report-trend');
  await trend.scrollIntoViewIfNeeded();
  const bounds = await trend.boundingBox();
  await trend.click({ position: { x: bounds.width * 0.95, y: bounds.height * 0.5 } });
  await page.waitForFunction(() => document.querySelector('[data-testid="chat-report-trend"]').getAttribute('aria-valuenow') === '6');
  await sales.getByRole('tab', { name: 'Trạng thái', exact: true }).click();
  assert.equal(await sales.getByTestId('chat-report-trend').count(), 0);
  assert.equal(await sales.getByTestId('chat-report-chart').count(), 1);
  await sales.getByRole('tab', { name: 'Bảng số liệu', exact: true }).click();
  assert.equal(await sales.getByTestId('chat-report-chart').count(), 0);
  await sales.getByRole('button', { name: 'Xem đủ 7 dòng' }).click();
  assert.equal(await sales.getByTestId('chat-report-table').count(), 1);
  await sales.getByRole('button', { name: 'Thu gọn bảng' }).click();
  await sales.getByRole('tab', { name: 'Xu hướng', exact: true }).click();
  await sales.getByRole('button', { name: 'Chi tiết báo cáo' }).click();
  assert.equal(await sales.getByTestId('chat-report-details').count(), 1);
  await sales.getByRole('button', { name: 'Thu gọn báo cáo' }).click();
  assert.equal(reports.length, 1, 'Switching report tabs must not call AI/API again');
  for (const width of [320, 390, 520]) {
    for (const theme of ['light', 'dark']) {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ colorScheme: theme, reducedMotion: 'reduce' });
      await header.scrollIntoViewIfNeeded();
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      assert(await sales.evaluate(el => el.getBoundingClientRect().width <= innerWidth));
      await page.screenshot({ path: path.join(output, `sales-${width}-${theme}.png`) });
    }
  }
  // Seed a real low-stock variant through the QA API after verifying its
  // disposable identity. This checks populated rows, not just an empty header.
  const product = (await (await page.request.get(origin + '/api/v1/management/products/1')).json()).data;
  if (product.variants[0].stock !== 3) {
    const updated = await page.request.patch(origin + '/api/v1/management/products/1', { data: {
      request_id: randomUUID(), expected_version: product.version, variant_id: product.variants[0].id, stock: 3,
    } });
    assert.equal(updated.status(), 200);
  }
  const stock = await send('Hàng sắp hết');
  await stock.getByRole('tab', { name: 'Bảng số liệu', exact: true }).click();
  const table = stock.getByTestId('chat-report-table');
  await table.scrollIntoViewIfNeeded();
  assert.match(await table.innerText(), /Giá bán/);
  assert.match(await table.innerText(), /SEED-PHONE/);
  assert.equal(reports.at(-1).table.rows[0][1], 3);
  await page.setViewportSize({ width: 320, height: 740 });
  const horizontal = table.getByTestId('chat-report-table-scroll');
  assert(await horizontal.evaluate(el => el.scrollWidth > el.clientWidth));
  await horizontal.evaluate(el => { el.scrollLeft = el.scrollWidth; });
  assert(await horizontal.evaluate(el => el.scrollLeft > 0));
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
  await page.screenshot({ path: path.join(output, 'stock-320-dark.png') });
  const empty = await send('Doanh thu ngày 01/01/1999');
  assert.equal(reports.at(-1).metrics[0].value, 0);
  assert.match(await empty.innerText(), /Chưa có số liệu phát sinh/);
  assert(!/NaN|Infinity/.test(await empty.innerText()));
  const input = page.getByRole('textbox', { name: 'Nhắn cho SellerPilot' });
  const sendButton = page.getByRole('button', { name: 'Gửi tin nhắn', exact: true });
  await input.fill('Xin chào');
  const normalReply = page.waitForResponse(r => r.url().endsWith('/chat') && r.request().method() === 'POST');
  await sendButton.click();
  assert.equal((await (await normalReply).json()).data.report, null);
  await page.waitForFunction(() => {
    const el = document.querySelector('[data-testid="chat-scroll"]');
    return el.scrollHeight - el.scrollTop - el.clientHeight < 20;
  });
  const countBefore = await page.getByTestId('chat-report').count();
  await input.fill('Vẽ biểu đồ doanh thu 30 ngày qua'); await sendButton.click();
  await page.getByTestId('typing-indicator').waitFor();
  const scroll = page.getByTestId('chat-scroll'), boundsToRead = await scroll.boundingBox();
  await page.mouse.move(boundsToRead.x + boundsToRead.width / 2, boundsToRead.y + 70);
  await page.mouse.wheel(0, -600);
  await page.getByRole('button', { name: 'Cuộn đến tin nhắn mới nhất', exact: true }).waitFor();
  const readingTop = await scroll.evaluate(el => el.scrollTop);
  await page.waitForFunction(count => document.querySelectorAll('[data-testid="chat-report"]').length === count + 1, countBefore);
  assert(await scroll.evaluate(el => el.scrollHeight - el.scrollTop - el.clientHeight > 100), 'Reading history must not be interrupted by a new report');
  assert(Math.abs(await scroll.evaluate(el => el.scrollTop) - readingTop) < 5, 'A new report must preserve the exact reading position');
  await page.getByRole('button', { name: 'Cuộn đến tin nhắn mới nhất', exact: true }).waitFor();
  assert.deepEqual(errors, []);
  console.log(JSON.stringify({ checks: ['Live report reconciles with real QA API facts', 'Interactive chart and expandable table',
    '320/390/520px in light and dark', 'Scrollable inventory table', 'Zero-data report'], errors }, null, 2));
})().catch(async error => {
  console.error(error);
  if (page) await page.screenshot({ path: path.join(output, 'failure.png') });
  process.exitCode = 1;
}).finally(async () => browser?.close());
