// Synthetic records only. Keep API calls intercepted so QA cannot touch a shop.
const snapshot = days => ({
  shop: { name: 'UTech Official', slug: 'utech-official', rating: 4.8, followers: 1280, location: 'TP. Hồ Chí Minh', vacation_mode: false },
  days, from_date: days === 1 ? '2026-10-19' : days === 7 ? '2026-10-13' : '2026-09-20', to_date: '2026-10-19', updated_at: '2026-10-19T10:00:00+07:00', timezone: 'Asia/Ho_Chi_Minh',
  order_value_vnd: days * 1000000, order_count: days * 12, delivered_value_vnd: days * 800000,
  average_order_vnd: 83333, cancelled_count: 2, previous_value_vnd: days * 900000, change_percent: days === 30 ? null : 11.1,
  series: Array.from({ length: days === 1 ? 12 : days }, (_, i) => ({
    date: days === 1 ? `2026-10-19T${String(i).padStart(2, '0')}:00` : `2026-10-${String(i % 19 + 1).padStart(2, '0')}`,
    value: [0, 400000, 150000, 600000][i % 4],
  })),
  order_status_counts: { pending: 3, paid: 2, shipped: days, delivered: days * 10, cancelled: 1, returned: 1 },
  tasks: { pending_orders: 3, packing_orders: 2, shipping_orders: 12, low_stock_products: 4, unanswered_reviews: 2 },
  active_products: 270,
  top_products: [{ id: 1, name: 'Bàn phím không dây màu trắng', sku: 'QA-001', price_vnd: 500000, stock: 30, sold_count: 128, image_url: null, rating: 4.8, status: 'active' }],
  integration_mode: 'local_store',
});
const headers = { 'Access-Control-Allow-Origin': '*', 'Access-Control-Allow-Headers': '*', 'Access-Control-Allow-Methods': 'GET,POST,OPTIONS' };
async function mockApi(page, dashboard) {
  await page.route('**/api/v1/**', async route => {
    if (route.request().method() === 'OPTIONS') return route.fulfill({ status: 204, headers });
    const url = new URL(route.request().url());
    if (url.pathname.endsWith('/management/dashboard')) return dashboard(route, Number(url.searchParams.get('days')), headers);
    const data = url.pathname.endsWith('/health') ? { status: 'ok', database: 'ok', shop_database: 'ok', provider: 'gemini', ai_availability: 'available', model: 'qa', model_available: true, demo_mode: true, integration_mode: 'local_store' }
      : { items: [], total: 0, limit: 20, offset: 0 };
    await route.fulfill({ status: 200, headers, json: { data } });
  });
}
module.exports = { snapshot, mockApi };
