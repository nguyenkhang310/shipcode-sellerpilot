// Pure helpers: observed rows are data, never instructions or local-shop records.
export const TTL_MS = 5 * 60 * 1000;
export const normalize = value => String(value || '').normalize('NFC').trim().replace(/\s+/g, ' ').toLowerCase();
export const COLUMN = {
  name: /^(?:sản phẩm|tên sản phẩm|thông tin sản phẩm|product|product name|product information)$/i,
  sku: /^(?:sku|mã sku|sku sản phẩm|sku phân loại|sku biến thể|seller sku)$/i,
  stock: /^(?:tồn kho|kho hàng|kho|stock|inventory|số lượng tồn|available stock)$/i,
  price: /^(?:giá|giá bán|price)$/i,
  sold: /^(?:đã bán|sold|sales)$/i,
  order: /^(?:mã đơn(?: hàng)?|order id|order number)$/i,
  status: /^(?:trạng thái|status)$/i,
  total: /^(?:tổng tiền|tổng đơn hàng|total)$/i,
};
export function integer(value) {
  const clean = String(value ?? '').trim();
  if (!/^(?:\d+|\d{1,3}(?:[.,\s]\d{3})+)$/.test(clean)) return null;
  const number = Number(clean.replace(/[.,\s]/g, ''));
  return Number.isSafeInteger(number) && number >= 0 && number <= 1000000000 ? number : null;
}
export function inventoryRows(page) {
  if (Array.isArray(page.inventory)) return page.inventory;
  return (page.tables || []).flatMap(table => {
    const headers = table[0] || [];
    const index = Object.fromEntries(Object.entries(COLUMN).map(([key, pattern]) => [key, headers.findIndex(h => pattern.test(normalize(h)))]));
    if (index.name < 0 || index.stock < 0) return [];
    return table.slice(1).map(row => {
      const name = row[index.name]?.trim().slice(0, 200) || '';
      const sku = index.sku >= 0 ? row[index.sku]?.trim().slice(0, 100) || null : null;
      return {key: sku ? 'sku:' + sku : 'unverified:' + JSON.stringify(row), identity_verified: Boolean(sku), name, sku, stock: integer(row[index.stock])};
    }).filter(row => row.name);
  });
}
export function summarizeInventory(rows, threshold = 5) {
  const unique = new Map(), conflicts = new Set();
  for (const raw of rows) {
    const row = {...raw, stock: integer(raw.stock)};
    if (!row.key || !row.name) continue;
    if (conflicts.has(row.key)) continue;
    const previous = unique.get(row.key);
    if (previous && (previous.stock !== row.stock || previous.name !== row.name)) {
      conflicts.add(row.key); unique.delete(row.key); continue;
    }
    unique.set(row.key, row);
  }
  const items = [...unique.values()];
  const known = items.filter(row => row.stock !== null);
  const low = known.filter(row => row.stock > 0 && row.stock <= threshold).sort((a, b) => a.stock - b.stock || a.name.localeCompare(b.name));
  const out = known.filter(row => row.stock === 0).sort((a, b) => a.name.localeCompare(b.name));
  return {records_count: items.length + conflicts.size, quantities_known: known.length,
    quantities_unknown: items.length - known.length + conflicts.size, conflicting_records: conflicts.size,
    unverified_identities: items.filter(row => !row.identity_verified).length,
    total_units: known.reduce((sum, row) => sum + row.stock, 0), threshold,
    low_stock_count: low.length, out_of_stock_count: out.length,
    low_stock_items: low.slice(0, 40).map(row => ({key: row.key.slice(0, 200), name: row.name, sku: row.sku || null, stock: row.stock})),
    out_of_stock_items: out.slice(0, 20).map(row => ({key: row.key.slice(0, 200), name: row.name, sku: row.sku || null, stock: row.stock})),
    omitted_low_stock_count: Math.max(0, low.length - 40), omitted_out_of_stock_count: Math.max(0, out.length - 20)};
}
export function pageFingerprint(page) {
  return JSON.stringify({tables: page.tables, inventory: page.inventory, metrics: page.metrics,
    empty: page.empty_confirmed});
}
export function resourcePresent(page, key) {
  if (page.loading) return false;
  if (key === 'dashboard') return Boolean(page.metrics?.length);
  if (key === 'products') return Boolean(inventoryRows(page).length || page.empty_confirmed && page.list_kind === 'products');
  return Boolean(page.tables?.some(table => table[0]?.some(h => COLUMN.order.test(normalize(h)))) || page.empty_confirmed && page.list_kind === 'orders');
}
export function resourceContext(page, key) {
  if (!page) return null;
  const coverage = page.coverage || {};
  const base = {source_url: page.snapshot.url, observed_at: page.snapshot.captured_at,
    pages_read: coverage.pages_read || 1, complete: Boolean(coverage.pagination_complete),
    scope: coverage.scope || 'current_page', reason: coverage.reason ? String(coverage.reason).slice(0, 500) : null};
  if (key === 'products') return {...base, ...summarizeInventory(inventoryRows(page))};
  // Limit prompt size; data omitted from the context remains in the extension cache.
  const tables = (page.tables || []).slice(0, 3).map(table => table.slice(0, 16));
  const sampled = tables.reduce((sum, table) => sum + Math.max(0, table.length - 1), 0);
  const rows = coverage.rows_read ?? (page.tables || []).reduce((sum, table) => sum + Math.max(0, table.length - 1), 0);
  return {...base, metrics: (page.metrics || []).slice(0, 20), tables, rows_read: rows, sampled_rows: sampled, sample_truncated: rows > sampled};
}
