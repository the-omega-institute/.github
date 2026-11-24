// Public reader smoke test. No sign-in, persistent profile, or write requests.
const fs = require('node:fs');
const { chromium } = require(process.env.MONITOR_BROWSER_MODULE);

async function inspect(config) {
  const browser = await chromium.launch({ executablePath: '/opt/google/chrome/chrome', headless: true });
  const observations = [];
  try {
    for (const check of config.browser || []) {
      const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
      const errors = [];
      page.on('pageerror', error => errors.push(error.message.slice(0, 300)));
      await page.route('**/*', route => ['GET', 'HEAD'].includes(route.request().method()) ? route.continue() : route.abort());
      try {
        const response = await page.goto(check.url, { waitUntil: 'domcontentloaded', timeout: 30000 });
        if (!response || response.status() !== 200) throw new Error('Reader HTTP status is not 200');
        await page.locator(check.selector || 'body').waitFor({ state: 'visible', timeout: 15000 });
        await page.waitForFunction(() => document.body.innerText.trim().length >= 80, null, { timeout: 15000 });
        await page.waitForLoadState('networkidle', { timeout: 10000 }).catch(() => {});
        if (errors.length) throw new Error(errors.join('; '));
        observations.push({ id: check.id, url: check.url, owner: check.owner, state: 'healthy' });
      } catch (error) {
        observations.push({ id: check.id, url: check.url, owner: check.owner, state: 'failed', reason: error.message.slice(0, 500) });
      } finally {
        await page.close();
      }
    }
  } finally {
    await browser.close();
  }
  return observations;
}

if (require.main === module) {
  inspect(JSON.parse(fs.readFileSync(process.argv[2], 'utf8')))
    .then(value => fs.writeFileSync(process.argv[3], JSON.stringify(value)))
    .catch(error => { console.error(error.message); process.exitCode = 1; });
}
module.exports = { inspect };
