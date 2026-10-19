// These UI tests must use chat_reliability_server.py, never the connected shop.
const origin = process.env.QA_API_ORIGIN || 'http://127.0.0.1:8123';
function qaFetch(route) {
  const url = new URL(route.request().url());
  return route.fetch({ url: origin + url.pathname + url.search });
}
async function useQaServer(page) {
  const forward = async route => route.fulfill({ response: await qaFetch(route) });
  await page.route('**/api/v1/**', forward);
  await page.route('**/store-static/**', forward);
}
module.exports = { qaFetch, useQaServer };
