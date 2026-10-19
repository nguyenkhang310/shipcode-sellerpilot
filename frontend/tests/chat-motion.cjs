const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { useQaServer } = require('./qa-server.cjs');
const output = path.resolve(__dirname, '../../docs/evaluations/chat-motion');
fs.mkdirSync(output, { recursive: true });
let browser, page;
(async () => {
  browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  await useQaServer(page);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  const checks = [], errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  for (const name of ['Sản phẩm', 'Đơn hàng', 'Shop', 'Quản lý', 'SellerPilot', 'Quản lý', 'SellerPilot']) {
    const tab = page.getByRole('tab', { name, exact: true });
    await tab.click(); assert.equal(await tab.getAttribute('aria-selected'), 'true');
  }
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
  console.error(error);
  if (page) { console.error((await page.locator('body').innerText()).slice(-2000)); await page.screenshot({ path: path.join(output, 'failure.png') }); }
  if (browser) await browser.close(); process.exit(1);
});
