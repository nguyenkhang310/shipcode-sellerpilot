const sellerPassword = process.env.QA_SELLER_PASSWORD;
if (!sellerPassword) throw new Error('Set QA_SELLER_PASSWORD for your local QA seller account.');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const BASE = process.env.STORE_URL || 'http://127.0.0.1:5011';
const CHROME = process.env.CHROME_EXECUTABLE || undefined;

async function inspect(page, path, viewport) {
  await page.setViewportSize(viewport);
  const response = await page.goto(BASE + path, { waitUntil: 'networkidle' });
  if (!response || response.status() >= 400) throw new Error(`${path}: HTTP ${response && response.status()}`);
  const result = await page.evaluate(() => {
    const visible = el => {
      const style = getComputedStyle(el);
      const box = el.getBoundingClientRect();
      return style.display !== 'none' && style.visibility !== 'hidden' && box.width > 0 && box.height > 0;
    };
    const controls = [...document.querySelectorAll('button,input:not([type=hidden]):not([type=checkbox]):not([type=radio]),select,textarea')]
      .filter(visible)
      .map(el => ({ tag: el.tagName, label: el.getAttribute('aria-label') || el.textContent.trim() || el.placeholder || el.name, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height }))
      .filter(item => item.width < 34 || item.height < 34);
    const tinyText = [...document.querySelectorAll('p,a,span,label,td,th,button')]
      .filter(el => visible(el) && el.children.length === 0 && el.textContent.trim().length > 2 && !el.classList.contains('material-symbols-outlined'))
      .map(el => ({ text: el.textContent.trim().slice(0, 45), size: parseFloat(getComputedStyle(el).fontSize) }))
      .filter(item => item.size < 11);
    const overflowing = [...document.querySelectorAll('body *')]
      .filter(visible)
      .map(el => { const box = el.getBoundingClientRect(); return { tag: el.tagName, cls: el.className && String(el.className).slice(0, 70), text: el.textContent.trim().slice(0, 50), left: box.left, right: box.right, width: box.width }; })
      .filter(item => item.right > innerWidth + 1 || item.left < -1)
      .slice(0, 8);
    return {
      innerWidth,
      scrollWidth: document.documentElement.scrollWidth,
      controls,
      tinyText,
      overflowing,
    };
  });
  if (result.scrollWidth > result.innerWidth + 1) throw new Error(`${path}: horizontal overflow ${result.scrollWidth}/${result.innerWidth} ${JSON.stringify(result.overflowing)}`);
  if (result.controls.length) throw new Error(`${path}: controls too small ${JSON.stringify(result.controls.slice(0, 4))}`);
  if (result.tinyText.length) throw new Error(`${path}: text below 11px ${JSON.stringify(result.tinyText.slice(0, 4))}`);
  return result;
}

(async () => {
  const browser = await chromium.launch({ headless: true, executablePath: CHROME });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();
  await page.route('**/*', route => ['image', 'media'].includes(route.request().resourceType()) ? route.abort() : route.continue());
  const failures = [];
  page.on('pageerror', error => failures.push(`JS: ${error.message}`));
  page.on('response', response => { if (response.status() >= 500) failures.push(`HTTP ${response.status()}: ${response.url()}`); });

  const publicPaths = ['/', '/products', '/shop/utech-official', '/product/384', '/cart', '/login', '/register', '/forgot-password', '/vouchers', '/order/lookup', '/policy', '/contact'];
  for (const path of publicPaths) {
    await inspect(page, path, { width: 1440, height: 1000 });
    await inspect(page, path, { width: 390, height: 844 });
  }

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto(BASE + '/', { waitUntil: 'networkidle' });
  await page.locator('.daily-head').scrollIntoViewIfNeeded();
  const sticky = await page.locator('.daily-head').evaluate(el => ({ position: getComputedStyle(el).position, top: getComputedStyle(el).top, background: getComputedStyle(el).backgroundColor }));
  if (sticky.position === 'sticky' || sticky.background === 'rgba(0, 0, 0, 0)') throw new Error(`daily heading overlay: ${JSON.stringify(sticky)}`);
  await page.screenshot({ path: '/tmp/ute-scroll-fixed.png', fullPage: false });

  await page.goto(BASE + '/login?next=/seller/', { waitUntil: 'networkidle' });
  const loginText = await page.locator('body').innerText();
  if (loginText.includes(sellerPassword) || loginText.includes('Tài khoản chủ shop cho bản trình diễn')) throw new Error('Demo password is visible on login page');
  await page.getByRole('textbox', { name: 'Email hoặc tên đăng nhập' }).fill('utech');
  await page.getByRole('textbox', { name: 'Mật khẩu', exact: true }).fill(sellerPassword);
  await page.getByRole('button', { name: 'ĐĂNG NHẬP', exact: true }).click();
  await page.waitForURL('**/seller/');
  const sellerLinks = await page.locator('.seller-sidebar .nav-group a').evaluateAll(links => [...new Set(links.map(link => link.getAttribute('href'))) ]);
  for (const path of sellerLinks) {
    await inspect(page, path, { width: 1440, height: 1000 });
    await inspect(page, path, { width: 390, height: 844 });
  }

  if (failures.length) throw new Error(failures.join('\n'));
  console.log(JSON.stringify({ publicScreens: publicPaths.length * 2, sellerScreens: sellerLinks.length * 2, sticky, errors: 0 }));
  await browser.close();
})().catch(error => { console.error(error); process.exit(1); });
