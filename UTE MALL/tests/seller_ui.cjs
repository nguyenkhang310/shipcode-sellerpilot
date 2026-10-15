const sellerPassword = process.env.QA_SELLER_PASSWORD;
if (!sellerPassword) throw new Error('Set QA_SELLER_PASSWORD for your local QA seller account.');
/* Real-browser checks for the seller centre. Read-only against the live store. */
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const BASE = process.env.STORE_URL || 'http://127.0.0.1:5011';
const OUTPUT = process.env.QA_OUTPUT || '/tmp/ute-seller-centre';

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: process.env.CHROME_EXECUTABLE || undefined });
  try {
    fs.mkdirSync(OUTPUT, { recursive: true });
    const page = await browser.newPage({ viewport: { width: 1920, height: 1200 } });
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('response', response => { if (response.status() >= 500) errors.push(response.status() + ' ' + response.url()); });
    await page.goto(BASE + '/login?next=/seller/', { waitUntil: 'networkidle' });
    await page.locator('[name=login_id]').fill('utech');
    await page.locator('[name=password]').fill(sellerPassword);
    await page.getByRole('button', { name: 'ĐĂNG NHẬP', exact: true }).click();
    await page.waitForURL('**/seller/');
    const paths = await page.locator('.nav-items a').evaluateAll(links => [...new Set(links.map(link => link.getAttribute('href')))]);
    assert.equal(paths.length, 14);
    let screens = 0;
    for (const viewport of [{ width: 1920, height: 1200 }, { width: 1440, height: 1000 }, { width: 390, height: 844 }]) {
      await page.setViewportSize(viewport);
      for (const path of paths) {
        const response = await page.goto(BASE + path, { waitUntil: 'networkidle' });
        assert.equal(response.status(), 200, path);
        const problems = await page.evaluate(() => {
          const visible = el => {
            const box = el.getBoundingClientRect(), style = getComputedStyle(el);
            return box.width > 0 && box.height > 0 && style.visibility !== 'hidden' && style.display !== 'none' && el.checkVisibility();
          };
          const controls = [...document.querySelectorAll('button,input:not([type=checkbox]):not([type=hidden]):not([type=radio]),select,textarea')].filter(visible);
          const undersized = controls.filter(el => el.getBoundingClientRect().height < 43 || el.getBoundingClientRect().width < 34).map(el => el.name || el.getAttribute('aria-label') || el.textContent.trim());
          const tiny = [...document.querySelectorAll('p,a,span,label,td,th,small,button')].filter(el => visible(el) && !el.children.length && el.textContent.trim().length > 2 && !el.classList.contains('material-symbols-outlined') && parseFloat(getComputedStyle(el).fontSize) < 12).map(el => el.textContent.trim().slice(0, 60));
          return { overflow: document.documentElement.scrollWidth > innerWidth + 1, undersized, tiny };
        });
        assert.deepEqual(problems, { overflow: false, undersized: [], tiny: [] }, path + ' at ' + viewport.width);
        if (['/seller/', '/seller/products', '/seller/orders', '/seller/reviews', '/seller/marketing'].includes(path)) {
          await page.screenshot({ path: OUTPUT + '/' + (path.split('/').filter(Boolean).pop() || 'dashboard') + '-' + viewport.width + '.png', fullPage: false });
        }
        screens++;
      }
    }
    await page.setViewportSize({ width: 1920, height: 1200 });
    await page.goto(BASE + '/seller/', { waitUntil: 'networkidle' });
    const rightGap = await page.locator('.dashboard-layout').evaluate(el => innerWidth - el.getBoundingClientRect().right);
    assert(rightGap <= 40, 'Dashboard must fill the available desktop width');
    for (const [label, count] of [['Hôm nay', 24], ['7 ngày qua', 7], ['30 ngày qua', 30]]) {
      await page.getByRole('link', { name: label, exact: true }).click();
      assert.equal(await page.locator('.chart-point').count(), count);
    }
    await page.locator('.chart-point').first().focus();
    assert(await page.locator('.chart-tooltip').isVisible());
    await page.locator('.chart-data summary').click();
    assert.equal(await page.locator('.chart-data tbody tr').count(), 30);
    await page.locator('.notification-menu summary').click();
    assert(await page.locator('.notification-menu .popover-panel').isVisible());
    await page.keyboard.press('Escape');
    assert(!(await page.locator('.notification-menu .popover-panel').isVisible()));
    const group = page.locator('.nav-group-title').nth(1);
    await group.click();
    assert.equal(await group.getAttribute('aria-expanded'), 'false');
    await group.click();
    await page.goto(BASE + '/seller/products');
    const firstProduct = page.locator('[data-bulk-item]').first();
    const sku = (await firstProduct.getAttribute('aria-label')).replace('Chọn sản phẩm ', '');
    const bulk = page.locator('#product-bulk');
    assert(await bulk.getByRole('button', { name: 'Áp dụng' }).isDisabled());
    await firstProduct.check();
    assert.equal(await bulk.locator('[data-selection-count]').innerText(), '1');
    assert(await bulk.getByRole('button', { name: 'Áp dụng' }).isEnabled());
    await bulk.locator('[data-select-all]').check();
    assert.equal(Number(await bulk.locator('[data-selection-count]').innerText()), await page.locator('[data-bulk-item]').count());
    await page.getByRole('textbox', { name: 'Tìm sản phẩm trong shop' }).fill(sku);
    await page.getByRole('button', { name: 'Tìm trong shop', exact: true }).click();
    assert.equal(await page.locator('[data-bulk-item]').count(), 1);
    await page.goto(BASE + '/seller/reviews?rating=3&unanswered=1');
    const stars = await page.locator('.review-item').evaluateAll(items => items.map(item => item.dataset.rating));
    assert(stars.length > 0 && stars.every(star => star === '3'));
    await page.goto(BASE + '/seller/marketing?create=1');
    await page.locator('[name=coupon_type]').selectOption('percent');
    assert.equal(await page.locator('[name=value]').getAttribute('max'), '100');
    await page.locator('[name=coupon_type]').selectOption('fixed');
    assert.equal(await page.locator('[name=value]').getAttribute('max'), '10000000');
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(BASE + '/seller/');
    await page.getByRole('button', { name: 'Mở menu quản lý', exact: true }).click();
    assert(await page.locator('.seller-sidebar').isVisible());
    assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'), 'true');
    await page.screenshot({ path: OUTPUT + '/mobile-menu.png' });
    await page.keyboard.press('Escape');
    assert.equal(await page.locator('.menu-toggle').getAttribute('aria-expanded'), 'false');
    assert(!(await page.locator('.seller-sidebar').isVisible()));
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ screens, paths: paths.length, interactions: 'periods, chart values, notifications, navigation, selection, SKU search, ratings, voucher unit, mobile drawer', rightGap, errors, screenshots: OUTPUT }));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exit(1); });
