const {test} = require('node:test');
const assert = require('node:assert/strict');
let saved = {}, tabs = new Map(), created = [], removed = [], nextId = 20, pageIndex = 0, readCount = 0;
let wrongAccount = false;
const origin = 'https://banhang.shopee.vn';
const id = '12345678-1234-1234-1234-123456789abc';
const connection = () => ({id, mode: 'shopee', tab_id: 7, target: {label: 'shop-a'}, conversations: {}, drafts: {}});
const rows = [
  [['Sản phẩm', 'SKU', 'Tồn kho'], ['Bàn phím', 'K1', '3'], ['Chuột', 'M1', '0']],
  [['Sản phẩm', 'SKU', 'Tồn kho'], ['Tai nghe', 'H1', '10'], ['Bàn phím', 'K1', '3']],
];
function page(product = false) {
  return {document_id: product ? 'products' : 'dashboard', page_context: String(pageIndex), target: {label: 'shop-a'},
    snapshot: {url: origin + (product ? '/observed-products' : '/'), captured_at: new Date().toISOString(), text: '{}'},
    metrics: product ? [] : [{label: 'Doanh số', value: '2.000.000đ'}],
    tables: product ? [rows[pageIndex]] : [], inventory: undefined, list_kind: product ? 'products' : null,
    pagination: {recognized: product, current: pageIndex + 1, has_next: pageIndex === 0, at_last: pageIndex === 1},
    navigation: {products: origin + '/observed-products', orders: origin + '/observed-orders'}, filtered: false};
}
global.chrome = {
  storage: {local: {get: async key => structuredClone(key === null ? saved : {[key]: saved[key]}),
    set: async value => Object.assign(saved, structuredClone(value)), remove: async key => {delete saved[key];}}},
  tabs: {
    get: async tabId => {if (!tabs.has(tabId)) throw Error('closed'); return structuredClone(tabs.get(tabId));},
    create: async value => {const tab = {...value, id: ++nextId, status: 'complete'}; tabs.set(tab.id, tab); created.push(tab); pageIndex = 0; return tab;},
    update: async (tabId, value) => {Object.assign(tabs.get(tabId), value); pageIndex = 0; return structuredClone(tabs.get(tabId));},
    remove: async tabId => {removed.push(tabId); tabs.delete(tabId);},
    sendMessage: async (tabId, message) => {
      readCount++;
      if (wrongAccount && tabId !== 7) return {ok: false, error: 'Không xác nhận được tài khoản'};
      if (message.kind === 'next_page') {pageIndex++; return {ok: true, data: {navigated: true}};}
      if (tabs.get(tabId).url.endsWith('/observed-orders')) return {ok: true, data: {...page(), metrics: [],
        list_kind: 'orders', tables: [[['Mã đơn hàng', 'Trạng thái'], ['ORDER-1', 'Chờ lấy hàng']]],
        pagination: {recognized: true, current: 1, has_next: false, at_last: true}}};
      return {ok: true, data: page(tabId !== 7)};
    },
  }, scripting: {executeScript: async () => {}},
};
function reset() {
  saved = {sellerpilot: connection()}; created = []; removed = []; pageIndex = 0; readCount = 0; wrongAccount = false;
  tabs = new Map([[7, {id: 7, url: origin + '/', active: true, status: 'complete'}]]);
}
const modules = () => Promise.all([import('../shopee-sync.js'), import('../shop-data.js'), import('../state.js')]);
async function finishSync(sync) {
  const deadline = Date.now() + 8000;
  while ((await sync.getSyncStatus(id)).syncing) {
    assert(Date.now() < deadline, 'sync exceeded fixture deadline');
    await new Promise(resolve => setTimeout(resolve, 5));
  }
}

test('inventory counts preserve zero/unknown, deduplicate SKU, reject conflicts and group thousands', async () => {
  const [, data] = await modules();
  assert.equal(data.integer('5'), 5); assert.equal(data.integer('1.500'), 1500);
  assert.equal(data.integer('1,5'), null); assert.equal(data.integer(''), null); assert.equal(data.integer('-1'), null);
  const records = [
    {key: 'a', name: 'A', sku: 'A', stock: 3, identity_verified: true},
    {key: 'a', name: 'A', sku: 'A', stock: 3, identity_verified: true},
    {key: 'b', name: 'B', sku: 'B', stock: 0, identity_verified: true},
    {key: 'c', name: 'C', stock: 'không rõ', identity_verified: false},
    {key: 'd', name: 'D', stock: 10, identity_verified: true},
    {key: 'd', name: 'D', stock: 20, identity_verified: true},
  ];
  const summary = data.summarizeInventory(records);
  assert.equal(summary.records_count, 4); assert.equal(summary.total_units, 3);
  assert.equal(summary.low_stock_count, 1); assert.equal(summary.out_of_stock_count, 1);
  assert.equal(summary.quantities_unknown, 2); assert.equal(summary.conflicting_records, 1);
});

test('background sync discovers actual link, reads all pages, coalesces concurrent calls and leaves original tab intact', async () => {
  reset(); const [sync, data] = await modules();
  await Promise.all([sync.syncShopeeData(id, ['products']), sync.syncShopeeData(id, ['products'])]);
  await finishSync(sync);
  const cached = await sync.getCachedPage('products', id);
  assert(cached, JSON.stringify(await sync.getSyncStatus(id)));
  assert.equal(cached.coverage.pages_read, 2); assert.equal(cached.coverage.pagination_complete, true);
  const summary = data.summarizeInventory(data.inventoryRows(cached));
  assert.equal(summary.records_count, 3); assert.equal(summary.total_units, 13);
  assert.equal(summary.low_stock_items[0].sku, 'K1');
  assert.equal(created.length, 1); assert.equal(created[0].url, origin + '/observed-products');
  assert.deepEqual(removed, [created[0].id]); assert(tabs.has(7));
  const reads = readCount; await sync.getCachedPage('products', id); assert.equal(readCount, reads, 'cache reads never navigate');
  const key = 'shopee_sync:' + id;
  saved[key].pages.products.snapshot.captured_at = new Date(Date.now() - data.TTL_MS - 1).toISOString();
  assert.equal(await sync.getCachedPage('products', id), null, 'expired data must not look fresh');
});

test('cached pages cannot mix accounts or connections; wrong account stops and cleans owned tabs', async () => {
  reset(); const [sync, , state] = await modules();
  await sync.saveCachedPage('products', id, {...page(true), target: {label: 'shop-a'}});
  await assert.rejects(sync.saveCachedPage('products', id, {...page(true), target: {label: 'shop-b'}}), /không thuộc/);
  await state.mutate(value => {value.target.label = 'shop-b';});
  assert.equal(await sync.getCachedPage('products', id), null);
  await state.mutate(value => {value.target.label = 'shop-a';});
  saved['shopee_sync:' + id].pages = {};
  wrongAccount = true;
  await sync.syncShopeeData(id, ['products']);
  await finishSync(sync);
  assert.equal((await sync.getSyncStatus(id)).status, 'partial');
  assert.equal(await sync.getCachedPage('products', id), null);
  assert.equal(removed.length, 1); assert(tabs.has(7));
});

test('cancellation returns promptly and closes only owned tabs, without a success claim', async () => {
  reset(); const [sync] = await modules();
  await sync.syncShopeeData(id, ['products']);
  // Let the job reach a real background-tab polling wait.
  while (!created.length) await new Promise(resolve => setTimeout(resolve, 5));
  sync.cancelSync(id);
  while ((await sync.getSyncStatus(id)).syncing) await new Promise(resolve => setTimeout(resolve, 5));
  assert.equal((await sync.getSyncStatus(id)).status, 'cancelled');
  assert.equal(await sync.getCachedPage('products', id), null);
  assert.deepEqual(removed, [created[0].id]); assert(tabs.has(7));
});

test('an explicit multi-section sync reuses one reader tab and retains both resources', async () => {
  reset(); const [sync] = await modules();
  await sync.syncShopeeData(id, ['products', 'orders']);
  await finishSync(sync);
  assert(await sync.getCachedPage('products', id));
  assert(await sync.getCachedPage('orders', id));
  assert.equal(created.length, 1, 'one temporary tab for the entire sync');
  assert.equal((await sync.getSyncStatus(id)).status, 'completed');
  assert.deepEqual(removed, [created[0].id]); assert(tabs.has(7));
});

test('taking over the reader tab stops further navigation and preserves that tab', async () => {
  reset(); const [sync] = await modules();
  const original = chrome.storage.local.set;
  let takenOver = false;
  chrome.storage.local.set = async value => {
    await original(value);
    if (!takenOver && value['shopee_sync:' + id]?.pages?.products?.coverage?.pagination_complete) {
      takenOver = true; tabs.get(created[0].id).active = true;
    }
  };
  try {
    await sync.syncShopeeData(id, ['products', 'orders']);
    await finishSync(sync);
    assert.equal(created.length, 1);
    assert.equal((await sync.getSyncStatus(id)).status, 'partial');
    assert.equal(await sync.getCachedPage('orders', id), null);
    assert(tabs.has(created[0].id)); assert(tabs.has(7)); assert.deepEqual(removed, []);
    assert.equal(tabs.get(created[0].id).url, origin + '/observed-products');
  } finally {chrome.storage.local.set = original;}
});

test('a service-worker interruption is explicit and recovers only its inactive background tab', async () => {
  reset(); const [sync] = await modules();
  const tab = {id: 42, openerTabId: 7, active: false, url: origin + '/observed-products'};
  tabs.set(42, tab);
  saved['shopee_sync:' + id] = {connection_id: id, pages: {}, job: {status: 'running', owned_tab_id: 42, opener_tab_id: 7}};
  assert.equal((await sync.getSyncStatus(id)).status, 'interrupted');
  assert.deepEqual(removed, [42]); assert(tabs.has(7));
  tabs.set(43, {...tab, id: 43, active: true});
  saved['shopee_sync:' + id].job = {status: 'running', owned_tab_id: 43, opener_tab_id: 7};
  await sync.getSyncStatus(id);
  assert(tabs.has(43), 'an active tab taken over by the user is preserved');
});
