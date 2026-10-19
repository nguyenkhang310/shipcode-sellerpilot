// Read-only navigation in owned background tabs. No cookies/private API requests.
import {state, boundTab, pageMessage, SOURCE, isSellerUrl} from './state.js';
import {TTL_MS, inventoryRows, summarizeInventory, pageFingerprint, resourcePresent} from './shop-data.js';
const jobs = new Map();
const KEYS = ['products', 'dashboard', 'orders'];
const MAX_PAGES = 100, JOB_MS = 180000, PAGE_MS = 20000;
let cacheGate = Promise.resolve();
const storageKey = id => 'shopee_sync:' + id;
const delay = (ms, signal) => new Promise((resolve, reject) => {
  if (signal?.aborted) return reject(signal.reason || Error('Đã dừng đồng bộ.'));
  const abort = () => {clearTimeout(timer); reject(signal.reason || Error('Đã dừng đồng bộ.'));};
  const timer = setTimeout(() => {signal?.removeEventListener('abort', abort); resolve();}, ms);
  signal?.addEventListener('abort', abort, {once: true});
});
async function current(id) {
  const connection = await state();
  if (connection.id !== id || connection.mode !== 'shopee' || !connection.target?.label) throw Error('Kết nối shop đã đổi. Đã dừng đồng bộ.');
  return connection;
}
async function cache(id) {return (await chrome.storage.local.get(storageKey(id)))[storageKey(id)] || {connection_id: id, pages: {}};}
function update(id, action) {
  const result = cacheGate.then(async () => {
    await current(id);
    const data = await cache(id); await action(data);
    await chrome.storage.local.set({[storageKey(id)]: data});
    return data;
  });
  cacheGate = result.catch(() => {}); return result;
}
export async function saveCachedPage(key, id, page) {
  if (!KEYS.includes(key)) throw Error('Nguồn đồng bộ không hỗ trợ.');
  const connection = await current(id);
  if (page.target?.label !== connection.target.label) throw Error('Dữ liệu không thuộc shop đang liên kết.');
  return update(id, data => {data.account_label = connection.target.label;
    data.pages[key] = key === 'products' ? {...page, inventory_summary: summarizeInventory(inventoryRows(page))} : page;
    data.synced_at = Date.now();});
}
export async function getCachedPage(key, id) {
  if (!KEYS.includes(key)) return null;
  const connection = await current(id), data = await cache(id), page = data.pages?.[key];
  if (!page || data.account_label !== connection.target.label || page.target?.label !== connection.target.label) return null;
  const age = Date.now() - Date.parse(page.snapshot?.captured_at);
  if (!Number.isFinite(age) || age < -30000 || age > TTL_MS) return null;
  return structuredClone(page);
}
export async function getSyncStatus(id) {
  const data = await cache(id), active = jobs.get(id);
  const connection = await current(id);
  const fresh = Object.values(data.pages || {}).filter(page => {
    const age = Date.now() - Date.parse(page.snapshot?.captured_at);
    return data.account_label === connection.target.label && page.target?.label === connection.target.label
      && Number.isFinite(age) && age >= -30000 && age <= TTL_MS;
  });
  const job = data.job || {};
  if (!active && job.status === 'running' && job.owned_tab_id) {
    const tab = await chrome.tabs.get(job.owned_tab_id).catch(() => null);
    if (tab && !tab.active && tab.openerTabId === job.opener_tab_id && isSellerUrl(tab.url))
      await chrome.tabs.remove(tab.id).catch(() => {});
    await update(id, value => {value.job = {...value.job, status: 'interrupted', owned_tab_id: null};}).catch(() => {});
  }
  return {synced: Boolean(fresh.length), syncing: Boolean(active),
    status: active ? 'running' : job.status === 'running' ? 'interrupted' : job.status || 'idle',
    resource: job.resource || null, pages_read: job.pages_read || 0, records_read: job.records_read || 0,
    resources: Object.fromEntries(KEYS.map(key => [key, data.pages?.[key]?.coverage || job.errors?.[key] || null])),
    synced_at: data.synced_at || null, account_label: data.account_label || null};
}
async function readTab(tabId, connection, message = {kind: 'read'}) {
  await current(connection.id);
  const tab = await chrome.tabs.get(tabId);
  if (!isSellerUrl(tab.url)) throw Error('Trang yêu cầu đăng nhập hoặc đã rời Kênh Người Bán.');
  if (tabId !== connection.tab_id && tab.active) throw Error('Tab đọc dữ liệu đang được bạn sử dụng. Đã dừng thao tác tự động trên tab này.');
  await chrome.scripting.executeScript({target: {tabId}, files: ['content/shopee.js']});
  const result = await chrome.tabs.sendMessage(tabId, {...message, target: connection.target});
  if (!result?.ok) throw Error(result?.error || 'Chưa đọc được trang Shopee.');
  return result.data;
}
async function waitStable(tabId, connection, key, signal, previous, expectedPage) {
  const deadline = Date.now() + PAGE_MS;
  let fingerprint, stable = 0, lastError;
  while (Date.now() < deadline) {
    signal.throwIfAborted(); await current(connection.id);
    const tab = await chrome.tabs.get(tabId);
    if (!isSellerUrl(tab.url)) throw Error('Shopee yêu cầu đăng nhập lại hoặc chuyển sang trang khác.');
    if (tab.status === 'complete') {
      try {
        const page = await readTab(tabId, connection);
        const next = pageFingerprint(page);
        const advanced = !previous || (next !== pageFingerprint(previous)
          && (expectedPage ? page.pagination?.current === expectedPage
            : previous.pagination?.current == null || page.pagination?.current === previous.pagination.current + 1));
        if (resourcePresent(page, key) && advanced) {
          stable = next === fingerprint ? stable + 1 : 1; fingerprint = next;
          if (stable >= 3) return page;
        } else {stable = 0;}
      } catch (error) {
        lastError = error;
        if (/tài khoản|đăng nhập|kết nối shop|đang được bạn sử dụng/i.test(error.message)) throw error;
      }
    }
    await delay(400, signal);
  }
  throw Error(lastError?.message || 'Không đọc được danh sách ổn định hoặc trang tiếp theo chưa chuyển.');
}
async function collect(connection, key, seed, signal, progress, openReader) {
  // Only URLs observed in this shop's navigation may be opened.
  const url = seed.navigation?.[key] || seed.snapshot.url;
  if (!isSellerUrl(url)) throw Error('Đường dẫn không thuộc Kênh Người Bán.');
  const created = await openReader(url);
  if (!seed.navigation?.[key] && !resourcePresent(seed, key)) {
    // Wait for the account/header to appear, then use an exact menu label.
    const deadline = Date.now() + PAGE_MS;
    let navigated = false;
    while (Date.now() < deadline && !navigated) {
      signal.throwIfAborted();
      try {await readTab(created.id, connection, {kind: 'navigate_section', resource: key}); navigated = true;}
      catch {await delay(500, signal);}
    }
    if (!navigated) throw Error('Chưa nhận diện được mục ' + ({products: 'Sản phẩm', dashboard: 'Tổng quan', orders: 'Đơn hàng'}[key]) + ' trong menu Shopee.');
  }
  let page = await waitStable(created.id, connection, key, signal), pages = 0;
  if (key !== 'dashboard' && page.pagination?.current > 1) {
    await readTab(created.id, connection, {kind: 'first_page', document_id: page.document_id, page_context: page.page_context});
    page = await waitStable(created.id, connection, key, signal, page, 1);
  }
  const seen = new Set(), tables = [], records = [];
  let reason = null, complete = false;
  while (pages < MAX_PAGES) {
    signal.throwIfAborted(); await current(connection.id);
    const fingerprint = pageFingerprint(page);
    if (seen.has(fingerprint)) {reason = 'repeated_page'; break;}
    seen.add(fingerprint); pages++;
    tables.push(...(page.tables || [])); records.push(...inventoryRows(page));
    await progress(pages, key === 'products' ? records.length : tables.reduce((sum, t) => sum + Math.max(0, t.length - 1), 0));
    if (records.length > 50000) {records.length = 50000; reason = 'record_limit'; break;}
    if (page.rows_truncated) {reason = 'row_limit'; break;}
    if (key === 'dashboard') {complete = true; break;}
    if (page.filtered) {reason = 'active_filters'; break;}
    if (page.empty_confirmed) {complete = pages === 1; break;}
    if (page.pagination?.at_last && page.pagination.current === pages) {complete = true; break;}
    if (!page.pagination?.recognized || page.pagination.current !== pages) {reason = 'pagination_unverified'; break;}
    if (!page.pagination.has_next) {reason = 'pagination_unverified'; break;}
    if (pages === MAX_PAGES) {reason = 'page_limit'; break;}
    try {
      await readTab(created.id, connection, {kind: 'next_page', document_id: page.document_id, page_context: page.page_context});
      page = await waitStable(created.id, connection, key, signal, page);
    } catch (error) {signal.throwIfAborted(); reason = error.message; break;}
  }
  const result = {...page, tables, inventory: records, coverage: {pages_read: pages, pagination_complete: complete,
    scope: key === 'dashboard' ? 'dashboard_period_unverified' : 'observed_list', reason,
    rows_read: key === 'products' ? records.length : tables.reduce((sum, t) => sum + Math.max(0, t.length - 1), 0)}};
  // Keep actual observation time, not cache lookup time; never make old facts look fresh.
  return result;
}
async function run(connection, resources, controller) {
  const errors = {}, completed = [];
  let reader = null, opener = null;
  const openReader = async url => {
    controller.signal.throwIfAborted();
    await current(connection.id);
    if (reader) {
      const tab = await chrome.tabs.get(reader.id);
      if (tab.active || tab.openerTabId !== opener.id || !isSellerUrl(tab.url))
        throw Error('Tab đọc dữ liệu đã được bạn sử dụng hoặc đổi trang. Đã dừng đồng bộ.');
      return chrome.tabs.update(reader.id, {url});
    }
    opener = await boundTab(connection);
    reader = await chrome.tabs.create({url, active: false, openerTabId: opener.id, ...(opener.windowId ? {windowId: opener.windowId} : {})});
    if (!reader?.id || reader.id === opener.id) throw Error('Chưa mở được tab đọc dữ liệu riêng.');
    await update(connection.id, data => {data.job = {...data.job, owned_tab_id: reader.id, opener_tab_id: opener.id};});
    return reader;
  };
  const timer = setTimeout(() => controller.abort(Error('Đồng bộ đã đạt giới hạn thời gian.')), JOB_MS);
  try {
    const seed = await pageMessage(connection, {kind: 'read'});
    if (seed.metrics?.length && !seed.list_kind) await saveCachedPage('dashboard', connection.id, {...seed,
      coverage: {pages_read: 1, pagination_complete: true, scope: 'dashboard_period_unverified', rows_read: 0}});
    for (const key of resources) {
      controller.signal.throwIfAborted();
      await update(connection.id, data => {data.job = {...data.job, status: 'running', resource: key, pages_read: 0, records_read: 0};});
      try {
        const page = key === 'dashboard' && seed.metrics?.length && !seed.list_kind ? seed
          : await collect(connection, key, seed, controller.signal, (pages, records) => update(connection.id, data => {
            data.job = {...data.job, resource: key, pages_read: pages, records_read: records};
          }), openReader);
        if (!page.coverage) page.coverage = {pages_read: 1, pagination_complete: true, scope: 'dashboard_period_unverified', rows_read: 0};
        await saveCachedPage(key, connection.id, page); completed.push(key);
        if (!page.coverage.pagination_complete) errors[key] = {error: page.coverage.reason || 'Danh sách chưa được đọc hết.'};
      } catch (error) {controller.signal.throwIfAborted(); errors[key] = {error: error.message};}
    }
    await update(connection.id, data => {data.job = {...data.job, status: Object.keys(errors).length ? 'partial' : 'completed', errors};});
    return {status: Object.keys(errors).length ? 'partial' : 'completed', pages: completed, errors};
  } catch (error) {
    await update(connection.id, data => {data.job = {...data.job, status: controller.signal.aborted ? 'cancelled' : 'failed', errors: {...errors, sync: {error: error.message}}};}).catch(() => {});
    return {status: controller.signal.aborted ? 'cancelled' : 'failed', error: error.message};
  } finally {
    clearTimeout(timer);
    if (reader?.id && reader.id !== opener?.id) {
      const tab = await chrome.tabs.get(reader.id).catch(() => null);
      if (tab && !tab.active && tab.openerTabId === opener?.id && isSellerUrl(tab.url))
        await chrome.tabs.remove(reader.id).catch(() => {});
    }
    await update(connection.id, data => {data.job = {...data.job, owned_tab_id: null};}).catch(() => {});
    jobs.delete(connection.id);
  }
}
export async function syncShopeeData(id, resources = KEYS) {
  const connection = await current(id);
  if (jobs.has(id)) return {status: 'already_running'};
  if (!Array.isArray(resources) || !resources.length || resources.some(key => !KEYS.includes(key))) throw Error('Nguồn đồng bộ không hợp lệ.');
  const controller = new AbortController();
  // Reserve the job before any asynchronous page read; concurrent requests join it.
  const job = {controller, promise: null}; jobs.set(id, job);
  job.promise = (async () => {
    try {
      await update(id, data => {data.job = {status: 'running', resource: resources[0], pages_read: 0, records_read: 0};});
      return await run(connection, resources, controller);
    } catch (error) {jobs.delete(id); return {status: 'failed', error: error.message};}
  })();
  return {status: 'started'};
}
export function cancelSync(id) {jobs.get(id)?.controller.abort(Error('Đã dừng đồng bộ theo yêu cầu.'));}
