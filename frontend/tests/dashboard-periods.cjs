// Synthetic API only; run after npm run build and serve frontend/dist/web.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const { snapshot, mockApi } = require('./management-fixture.cjs');
const path = require('node:path');
const fs = require('node:fs');
const output = process.env.QA_OUTPUT || path.resolve(__dirname, '../../docs/evaluations/dashboard-periods');
fs.mkdirSync(output, { recursive: true });
const delay = ms => new Promise(resolve => setTimeout(resolve, ms));
let browser, page;
(async () => {
  browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  page = await browser.newPage({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true });
  const errors = [], requests = [], checks = [], geometry = [];
  page.on('pageerror', e => errors.push(e.message));
  let fail = false, mismatch = false, empty = false;
  await mockApi(page, async (route, days, headers) => {
    requests.push(days);
    const rejected = fail, wrong = mismatch, zero = empty;
    await delay(days === 7 ? 1100 : days === 30 ? 800 : 40);
    const data = snapshot(days);
    if (wrong) data.days = 30;
    if (zero) Object.assign(data, { order_count: 0, order_value_vnd: 0, series: [], order_status_counts: {}, change_percent: null });
    try {
      await route.fulfill({ status: rejected ? 503 : 200, headers, json: rejected ? { detail: 'Kết nối kiểm thử tạm gián đoạn.' } : { data } });
    } catch (e) { if (!/closed|cancel|abort/i.test(e.message)) throw e; }
  });
  await page.goto(process.env.QA_APP_URL || 'http://127.0.0.1:5174');
  const summary = page.getByTestId('period-summary'), scroll = page.getByTestId('management-scroll');
  const ready = days => page.getByTestId('period-summary').and(page.getByLabel(`Số liệu ${days} ngày`, { exact: true })).waitFor();
  const choose = label => page.getByRole('button', { name: label, exact: true }).click();
  const expire = () => page.evaluate(() => { const now = Date.now; Date.now = () => now() + 61000; });
  const measure = () => scroll.evaluate(el => ({ top: el.scrollTop, height: el.scrollHeight, viewport: el.clientHeight,
    summary: el.querySelector('[data-testid="period-summary"]').getBoundingClientRect().height,
    distribution: el.querySelector('[data-testid="order-distribution"]').getBoundingClientRect().height }));
  const stable = (before, after, label) => {
    geometry.push({ label, before, after });
    for (const key of ['top', 'height', 'summary', 'distribution']) assert(Math.abs(before[key] - after[key]) <= 2, label + ': ' + key + ' ' + JSON.stringify({ before, after }));
  };
  await ready(1);
  // Selector remains visible while partly scrolled. Loading must not move it.
  await scroll.evaluate(el => { el.scrollTop = 180; });
  const before = await measure();
  await choose('7 ngày'); await page.getByTestId('period-loading').waitFor();
  stable(before, await measure(), 'slow 7-day pending');
  assert.equal(await summary.getByText('1.000.000', { exact: false }).count(), 0);
  assert.match(await page.getByTestId('order-distribution').innerText(), /—/);
  await page.screenshot({ path: path.join(output, 'loading-390.png') });
  await ready(7); stable(before, await measure(), '7-day resolved');
  await choose('30 ngày'); await page.getByTestId('period-loading').waitFor();
  stable(before, await measure(), '30-day pending');
  await ready(30); stable(before, await measure(), 'null comparison baseline');
  assert.match(await summary.innerText(), /30\.000\.000/);
  checks.push('Scroll position and entire page height stable during delayed 7/30-day loads, including a null comparison baseline');
  // Cached changes must be immediate and not issue duplicate network requests.
  const cachedCalls = requests.length;
  for (const label of ['Hôm nay', '7 ngày', '30 ngày', 'Hôm nay']) await choose(label);
  await ready(1); assert.equal(requests.length, cachedCalls);
  checks.push('Warmed periods reuse their snapshot; no duplicate API calls');
  // First period request is slow; a later response cannot overwrite today.
  await expire();
  await choose('7 ngày'); await page.getByTestId('period-loading').waitFor();
  await choose('30 ngày'); await choose('Hôm nay'); await ready(1); await delay(1200);
  assert.equal(await summary.getAttribute('aria-label'), 'Số liệu 1 ngày');
  assert.match(await summary.innerText(), /1\.000\.000/);
  checks.push('Rapid switching ignores late responses');
  // At the bottom, disappearing distribution used to clamp the scroll offset.
  await scroll.evaluate(el => { el.scrollTop = el.scrollHeight; });
  const bottom = await measure();
  await page.getByRole('button', { name: '7 ngày', exact: true }).evaluate(el => el.click());
  await page.getByTestId('period-loading').waitFor();
  stable(bottom, await measure(), 'bottom during load'); await ready(7);
  stable(bottom, await measure(), 'bottom after load');
  checks.push('Bottom scroll does not clamp while period cards load');
  await scroll.evaluate(el => { el.scrollTop = 180; });
  fail = true; await expire();
  const errorBefore = await measure();
  await choose('30 ngày'); await page.getByText('Kết nối kiểm thử tạm gián đoạn.', { exact: true }).first().waitFor();
  stable(errorBefore, await measure(), 'request failure');
  assert.equal(await summary.getAttribute('aria-label'), 'Chưa có số liệu 30 ngày');
  fail = false;
  await page.getByRole('button', { name: 'Đồng bộ số liệu', exact: true }).evaluate(el => el.click());
  await ready(30); stable(errorBefore, await measure(), 'retry recovery');
  checks.push('Failed load and manual retry retain geometry and do not mislabel stale numbers');
  mismatch = true; await expire(); await choose('7 ngày');
  await page.getByText('Kỳ số liệu trả về không khớp. Vui lòng đồng bộ lại.', { exact: true }).first().waitFor();
  assert.equal(await summary.getAttribute('aria-label'), 'Chưa có số liệu 7 ngày');
  mismatch = false; empty = true;
  await page.getByRole('button', { name: 'Đồng bộ số liệu', exact: true }).evaluate(el => el.click());
  await ready(7); assert.match(await summary.innerText(), /Chưa có dữ liệu kỳ trước/);
  checks.push('Wrong-period response rejected; empty series and zero orders render without crashing');
  // Chart keyboard selection is cleared when the selected range changes.
  empty = false;
  await choose('Hôm nay'); await ready(1);
  await scroll.evaluate(el => { el.scrollTop = 0; });
  await page.getByTestId('sales-chart').click({ position: { x: 160, y: 60 } });
  assert.match(await page.getByTestId('sales-chart').getAttribute('aria-valuetext'), /đ/);
  await choose('30 ngày'); await ready(30);
  assert.equal(await page.getByTestId('sales-chart').getAttribute('aria-valuetext'), 'Chọn mốc để xem giá trị đơn hàng');
  checks.push('Chart point selection does not leak into another period');
  for (const width of [320, 390, 430]) {
    await page.setViewportSize({ width, height: 844 }); await scroll.evaluate(el => { el.scrollTop = 0; });
    const bounds = await scroll.evaluate(el => ({ w: el.clientWidth, content: el.scrollWidth }));
    assert(bounds.content <= bounds.w, 'Horizontal overflow at ' + width);
    await page.screenshot({ path: path.join(output, 'dashboard-' + width + '.png') });
    await page.getByRole('tab', { name: 'Đơn hàng', exact: true }).click();
    await page.getByTestId('order-filters').waitFor();
    await page.getByRole('tab', { name: 'Sản phẩm', exact: true }).click();
    await page.getByRole('textbox', { name: 'Tìm sản phẩm', exact: true }).waitFor();
    await page.getByRole('tab', { name: 'Quản lý', exact: true }).click();
  }
  await page.emulateMedia({ colorScheme: 'dark', reducedMotion: 'reduce' });
  await page.reload(); await ready(1);
  await page.screenshot({ path: path.join(output, 'dark-reduced-motion.png') });
  checks.push('320/390/430 px, dark appearance, reduced motion and management tabs smoke checked');
  assert.deepEqual(errors, []);
  const results = { checks, requests, geometry, errors };
  fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify({ checks, requests, errors }, null, 2));
  await browser.close();
})().catch(async e => {
  console.error(e);
  if (page) { console.error((await page.locator('body').innerText()).slice(0, 2800)); await page.screenshot({ path: path.join(output, 'failure.png') }); }
  if (browser) await browser.close(); process.exit(1);
});
