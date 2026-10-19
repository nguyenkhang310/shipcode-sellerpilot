// Read-only visual regression: run against the isolated QA store on port 5012.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const base = process.env.STORE_URL || 'http://127.0.0.1:5012';
const output = path.resolve(__dirname, '../../docs/evaluations/auth-layout');
fs.mkdirSync(output, { recursive: true });

(async () => {
  const browser = await chromium.launch({ executablePath: process.env.CHROME_EXECUTABLE || undefined, headless: true });
  try {
    const results = [];
    for (const fontMode of ['normal', 'delayed', 'blocked']) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
      const page = await context.newPage();
      const errors = [];
      page.on('pageerror', error => errors.push(error.message));
      if (fontMode !== 'normal') {
        await page.route('**/fonts/*.woff2', async route => {
          if (fontMode === 'blocked') return route.abort();
          await new Promise(resolve => setTimeout(resolve, 700));
          await route.continue();
        });
      }
      await page.addInitScript(() => {
        window.authPositions = [];
        function sample() {
          const nodes = ['.auth-heading h1', '#auth-card-title', '#auth-submit'].map(s => document.querySelector(s));
          if (nodes.every(Boolean) && document.readyState !== 'loading') {
            window.authPositions.push(nodes.map(el => {
              const rect = el.getBoundingClientRect();
              return [rect.x, rect.y, rect.width, rect.height];
            }));
          }
          if (window.authPositions.length < 90) requestAnimationFrame(sample);
        }
        requestAnimationFrame(sample);
      });
      await page.goto(base + '/login', { waitUntil: 'networkidle' });
      await page.waitForFunction(() => window.authPositions.length >= 90);
      const positions = await page.evaluate(() => window.authPositions);
      let drift = 0;
      for (const frame of positions) frame.forEach((rect, i) => rect.forEach((value, j) => {
        drift = Math.max(drift, Math.abs(value - positions[0][i][j]));
      }));
      assert(drift <= 1, `${fontMode}: title/button moved by ${drift}px during cold load`);
      assert.equal(await page.locator('link[href*="fonts.googleapis.com"]').count(), 0);
      const submit = page.locator('#auth-submit');
      const before = await submit.boundingBox();
      await page.locator('#auth-login').fill('layout-check');
      await page.locator('#auth-password').fill('not-submitted');
      assert.equal(await submit.isDisabled(), false);
      await submit.hover();
      assert.deepEqual(await submit.boundingBox(), before, 'Button geometry changed when enabled/hovered');
      await page.locator('#auth-password').fill('');
      assert.equal(await submit.isDisabled(), true);
      assert.deepEqual(await submit.boundingBox(), before, 'Button geometry changed when disabled');

      for (const width of [320, 390, 768, 1024, 1440]) {
        await page.setViewportSize({ width, height: 1000 });
        const issues = await page.evaluate(() => {
          const issues = [];
          const bounds = el => el.getBoundingClientRect();
          if (document.documentElement.scrollWidth > innerWidth) issues.push('page overflow');
          for (const tile of document.querySelectorAll('.auth-payment')) {
            const r = bounds(tile), c = bounds(tile.firstElementChild);
            if (c.left < r.left - 1 || c.right > r.right + 1 || c.top < r.top - 1 || c.bottom > r.bottom + 1) issues.push('logo overflow: ' + tile.textContent);
            const range = document.createRange();
            range.selectNodeContents(tile.firstElementChild);
            for (const line of range.getClientRects()) {
              if (line.left < r.left - 1 || line.right > r.right + 1 || line.top < r.top - 1 || line.bottom > r.bottom + 1) issues.push('logo text overflow: ' + tile.textContent);
            }
            if (Math.abs(c.x + c.width / 2 - r.x - r.width / 2) > 1 || Math.abs(c.y + c.height / 2 - r.y - r.height / 2) > 1) issues.push('logo off center: ' + tile.textContent);
          }
          const qr = bounds(document.querySelector('.auth-download>img'));
          const badges = bounds(document.querySelector('.auth-download-links'));
          if (Math.abs(qr.top - badges.top) > 1 || Math.abs(qr.bottom - badges.bottom) > 1) issues.push('download badges not aligned to QR');
          const heading = bounds(document.querySelector('.auth-heading'));
          const help = bounds(document.querySelector('.auth-help-link'));
          if (heading.right > help.left - 6) issues.push('header title overlaps help link');
          return issues;
        });
        assert.deepEqual(issues, [], `${fontMode}, ${width}px`);
        if (fontMode === 'normal') await page.screenshot({ path: path.join(output, `login-${width}.png`), fullPage: true });
      }
      assert.deepEqual(errors, []);
      results.push({ fontMode, maxTitleDrift: drift, widths: [320, 390, 768, 1024, 1440], errors });
      await context.close();
    }
    fs.writeFileSync(path.join(output, 'results.json'), JSON.stringify(results, null, 2));
    console.log(JSON.stringify(results, null, 2));
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
