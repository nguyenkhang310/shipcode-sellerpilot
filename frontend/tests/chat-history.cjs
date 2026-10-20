// Run only against tests/chat_reliability_server.py (synthetic shop + AI).
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { randomUUID } = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { useQaServer } = require('./qa-server.cjs');
const api = process.env.QA_API_ORIGIN || 'http://127.0.0.1:8123';
const output = path.resolve(__dirname, '../../docs/evaluations/chat-history');
fs.mkdirSync(output, { recursive: true });
let browser, page;
(async () => {
  browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  await useQaServer(page);
  const errors = [], checks = [];
  page.on('pageerror', error => errors.push(error.message));
  const create = async message => {
    const id = randomUUID();
    const response = await page.request.post(api + '/api/v1/chat', { data: { message, conversation_id: id, request_id: randomUUID() } });
    assert.equal(response.status(), 200, await response.text()); return id;
  };
  const suffix = randomUUID().slice(0, 6);
  const firstTitle = 'Tư vấn bán hàng ' + suffix, secondTitle = 'Chiến lược cho sinh viên ' + suffix;
  const first = await create(firstTitle), second = await create(secondTitle);
  const row = id => page.getByTestId('history-row-' + id);
  const openHistory = () => page.getByRole('button', { name: 'Lịch sử trò chuyện', exact: true }).click();
  const openActions = title => page.getByRole('button', { name: 'Thao tác: ' + title, exact: true }).click();
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  await openHistory(); await row(first).waitFor();
  await row(first).scrollIntoViewIfNeeded(); // Wait for the drawer slide before starting a separate swipe.
  // Touch events exercise PanResponder's mobile gesture path.
  const box = await row(first).boundingBox();
  const cdp = await page.context().newCDPSession(page);
  const start = box.x + box.width - 50, y = box.y + box.height / 2;
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchStart', touchPoints: [{ x: start, y }] });
  for (let step = 1; step <= 12; step++) {
    await cdp.send('Input.dispatchTouchEvent', { type: 'touchMove', touchPoints: [{ x: start - step * 12, y }] });
    await page.waitForTimeout(16);
  }
  await cdp.send('Input.dispatchTouchEvent', { type: 'touchEnd', touchPoints: [] });
  await row(first).getByRole('button', { name: 'Ghim cuộc trò chuyện', exact: true }).click();
  await page.getByText('Đã ghim', { exact: true }).waitFor();
  assert((await row(first).boundingBox()).y < (await row(second).boundingBox()).y);
  checks.push('Vuốt trái mở Ghim/Xóa; ghim đưa hội thoại lên đầu');
  await page.reload({ waitUntil: 'networkidle' });
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  await openHistory(); await page.getByText('Đã ghim', { exact: true }).waitFor();
  await openActions(firstTitle);
  await row(first).getByRole('button', { name: 'Bỏ ghim cuộc trò chuyện', exact: true }).click();
  await page.getByText('Đã ghim', { exact: true }).waitFor({ state: 'hidden' });
  assert((await row(second).boundingBox()).y < (await row(first).boundingBox()).y);
  checks.push('Ghim tồn tại sau reload; bỏ ghim khôi phục thứ tự gần đây');
  // Open the first conversation, then delete it from history.
  await row(first).getByRole('button', { name: firstTitle, exact: true }).click();
  await page.getByRole('textbox', { name: 'Nhắn cho SellerPilot', exact: true }).waitFor();
  await openHistory(); await openActions(firstTitle);
  page.once('dialog', dialog => dialog.dismiss());
  await row(first).getByRole('button', { name: 'Xóa cuộc trò chuyện', exact: true }).click();
  assert.equal(await row(first).count(), 1);
  page.once('dialog', dialog => dialog.accept());
  await row(first).getByRole('button', { name: 'Xóa cuộc trò chuyện', exact: true }).click();
  await row(first).waitFor({ state: 'hidden' });
  assert.equal((await page.request.get(api + '/api/v1/conversations/' + first)).status(), 410);
  await page.getByRole('button', { name: 'Đóng lịch sử trò chuyện', exact: true }).click();
  await page.getByText('Mình giúp gì', { exact: false }).waitFor();
  checks.push('Hủy giữ nguyên lịch sử; xác nhận xóa hội thoại đang mở trả về màn hình chat mới');
  await page.setViewportSize({ width: 320, height: 700 });
  await openHistory(); await openActions(secondTitle);
  await page.waitForTimeout(500); // Modal fade and the swipe spring must finish before visual QA.
  const pin = await row(second).getByRole('button', { name: 'Ghim cuộc trò chuyện', exact: true }).boundingBox();
  const trash = await row(second).getByRole('button', { name: 'Xóa cuộc trò chuyện', exact: true }).boundingBox();
  assert(pin.width >= 44 && trash.width >= 44 && pin.x + pin.width <= trash.x + 1);
  assert(trash.x + trash.width <= 320 && pin.x >= 0);
  await page.screenshot({ path: path.join(output, 'swipe-320.png') });
  page.once('dialog', dialog => dialog.accept());
  await row(second).getByRole('button', { name: 'Xóa cuộc trò chuyện', exact: true }).click();
  await row(second).waitFor({ state: 'hidden' });
  checks.push('Nút ghim/xóa đủ vùng chạm ở màn hình 320px, không chồng nhau');
  assert.deepEqual(errors, []);
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify({ checks, errors }, null, 2));
  console.log(JSON.stringify({ checks, errors }, null, 2));
  await browser.close();
})().catch(async error => {
  console.error(error);
  if (page) { console.error((await page.locator('body').innerText()).slice(0, 3000)); await page.screenshot({ path: path.join(output, 'failure.png') }); }
  if (browser) await browser.close(); process.exit(1);
});
