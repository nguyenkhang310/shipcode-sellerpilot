// Synthetic API + intercepted snapshots; no connected seller data is modified.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { snapshot, mockApi } = require('./management-fixture.cjs');
let browser, page;
(async () => {
  browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  page = await browser.newPage({ viewport: { width: 390, height: 844 } });
  const errors = [], requests = [];
  let added = 0, fail = false;
  page.on('pageerror', error => errors.push(error.message));
  await mockApi(page, async (route, days, headers) => {
    requests.push(days);
    if (fail) return route.fulfill({ status: 503, headers, json: { detail: 'Tạm mất kết nối kiểm thử' } });
    const data = snapshot(days);
    data.order_count = 10 + added;
    data.order_value_vnd = 10000000 + added * 1000000;
    await route.fulfill({ status: 200, headers, json: { data } });
  });
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174', { waitUntil: 'networkidle' });
  const counter = page.getByTestId('dashboard-order-count'), summary = page.getByTestId('period-summary');
  await counter.filter({ hasText: /^10$/ }).waitFor();
  const before = await summary.boundingBox();
  added = 2;
  await counter.filter({ hasText: /^12$/ }).waitFor({ timeout: 8000 });
  assert.match(await summary.innerText(), /12\.000\.000/);
  const after = await summary.boundingBox();
  assert(Math.abs(before.height - after.height) <= 2 && Math.abs(before.y - after.y) <= 2);
  assert.equal(await page.getByText('Đang lấy số liệu từ shop…', { exact: true }).count(), 0);
  // Stop polling outside Quản lý; returning to it refreshes immediately.
  await page.getByRole('tab', { name: 'SellerPilot', exact: true }).click();
  await page.waitForTimeout(300); const calls = requests.length;
  added = 3; await page.waitForTimeout(5400); assert.equal(requests.length, calls);
  await page.getByRole('tab', { name: 'Quản lý', exact: true }).click();
  await counter.filter({ hasText: /^13$/ }).waitFor({ timeout: 2500 });
  fail = true;
  await page.getByTestId('management-scroll').getByText('Tạm mất kết nối kiểm thử', { exact: true }).waitFor({ timeout: 8000 });
  assert.equal(await counter.innerText(), '13', 'Transient background failure must retain last known count');
  fail = false; added = 4;
  await counter.filter({ hasText: /^14$/ }).waitFor({ timeout: 8000 });
  assert.deepEqual(errors, []);
  console.log('PASS: live count/revenue, stable layout, pause outside dashboard, immediate resume, recovery after background error');
  await browser.close();
})().catch(async error => { console.error(error); if (page) console.error((await page.locator('body').innerText()).slice(0, 2500)); if (browser) await browser.close(); process.exit(1); });
