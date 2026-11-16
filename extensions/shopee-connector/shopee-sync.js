// Zero New Tabs: Read-only in-tab DOM extraction and Data Bridge in MAIN world. No background tabs.
import {state, boundTab, pageMessage, SOURCE, isSellerUrl, contentScriptForUrl} from './state.js';
import {TTL_MS, inventoryRows, summarizeInventory, pageFingerprint, resourcePresent} from './shop-data.js';
import {loadSchema} from './schema-loader.js';

const jobs = new Map();
const KEYS = ['products', 'dashboard', 'orders'];
const JOB_MS = 180000;
let cacheGate = Promise.resolve();
const storageKey = id => 'shopee_sync:' + id;

async function current(id) {
  const connection = await state();
  if (connection.id !== id || connection.mode !== 'shopee' || !connection.target?.label) throw Error('Kết nối shop đã đổi. Đã dừng đồng bộ.');
  return connection;
}

async function cache(id) {
  return (await chrome.storage.local.get(storageKey(id)))[storageKey(id)] || {connection_id: id, pages: {}};
}

function update(id, action) {
  const result = cacheGate.then(async () => {
    await current(id);
    const data = await cache(id);
    await action(data);
    await chrome.storage.local.set({[storageKey(id)]: data});
    return data;
  });
  cacheGate = result.catch(() => {});
  return result;
}

export async function saveCachedPage(key, id, page) {
  if (!KEYS.includes(key)) throw Error('Nguồn đồng bộ không hỗ trợ.');
  const connection = await current(id);
  if (page.target?.label !== connection.target.label) throw Error('Dữ liệu không thuộc shop đang liên kết.');
  return update(id, data => {
    data.account_label = connection.target.label;
    data.pages[key] = key === 'products' ? {...page, inventory_summary: summarizeInventory(inventoryRows(page))} : page;
    data.synced_at = Date.now();
  });
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
  return {
    synced: Boolean(fresh.length),
    syncing: Boolean(active),
    status: active ? 'running' : job.status === 'running' ? 'interrupted' : job.status || 'idle',
    resource: job.resource || null,
    pages_read: job.pages_read || 0,
    records_read: job.records_read || 0,
    resources: Object.fromEntries(KEYS.map(key => [key, data.pages?.[key]?.coverage || job.errors?.[key] || null])),
    synced_at: data.synced_at || null,
    account_label: data.account_label || null
  };
}

async function tryDataBridge(tabId, key, targetLabel) {
  try {
    if (typeof chrome?.scripting?.executeScript !== 'function') return null;
    const schema = await loadSchema();
    if (!schema?.featureFlags?.useInternalApi) return null;

    const results = await chrome.scripting.executeScript({
      target: {tabId},
      world: 'MAIN',
      func: async (resKey, expectedLabel) => {
        try {
          if (location.origin !== 'https://banhang.shopee.vn') return null;
          const sleep = ms => new Promise(r => setTimeout(r, ms));
          await sleep(200);

          const cdsMatch = document.cookie.match(/\bSPC_CDS=([a-zA-Z0-9-]+)/);
          const cds = cdsMatch ? cdsMatch[1] : (new URLSearchParams(location.search).get('SPC_CDS') || '');
          const cdsVer = new URLSearchParams(location.search).get('SPC_CDS_VER') || '2';
          const withCds = url => {
            if (!cds) return url;
            const sep = url.includes('?') ? '&' : '?';
            return `${url}${sep}SPC_CDS=${cds}&SPC_CDS_VER=${cdsVer}`;
          };

          if (resKey === 'products') {
            const endpoints = [
              '/api/v3/opt/mpsku/list/v2/search_product_list?page_number=1&page_size=48',
              '/api/v3/opt/mpsku/list/v2/get_product_list?page_number=1&page_size=48',
              '/api/v3/mtsku/get_mtsku_list/?page_number=1&page_size=24'
            ];
            let json = null;
            for (const ep of endpoints) {
              try {
                const res = await window.fetch(withCds(ep), {
                  headers: {'Accept': 'application/json'},
                  credentials: 'include', redirect: 'error', signal: AbortSignal.timeout(5000)
                });
                if (res.ok) {
                  const j = await res.json();
                  if (j.code === 0 && (Array.isArray(j.data?.products) || Array.isArray(j.data?.list) || Array.isArray(j.data?.mpsku_list))) {
                    json = j;
                    break;
                  }
                }
              } catch {}
            }
            if (!json) {
              const domItems = [...document.querySelectorAll('.product-variation-item, [class*="product-variation-item"]')].filter(el => Boolean(el.getClientRects().length));
              if (domItems.length > 0) {
                const domInventory = [];
                const domTableRows = [];
                for (const item of domItems) {
                  const cells = [...item.querySelectorAll('.product-variation-padding, [class*="product-variation-padding"]')];
                  const cList = cells.length >= 3 ? cells : [...item.children];
                  if (cList.length >= 3) {
                    const rawName = (cList[0].innerText || cList[0].textContent || '').trim();
                    const name = rawName.replace(/SKU sản phẩm:.*$/i, '').replace(/ID Sản phẩm:.*$/i, '').trim() || rawName;
                    const sku = rawName.match(/SKU sản phẩm:\s*([^\s-]+)/i)?.[1] || null;
                    const id = rawName.match(/ID Sản phẩm:\s*(\d+)/i)?.[1] || null;
                    const price = (cList[1].innerText || cList[1].textContent || '').trim();
                    const stock = (cList[2].innerText || cList[2].textContent || '').trim();
                    domTableRows.push([name, price, stock]);
                    domInventory.push({
                      key: id ? 'product:' + id : 'unverified:' + name,
                      name, sku: sku || '', stock, identity_verified: Boolean(id || sku)
                    });
                  }
                }
                if (domInventory.length > 0) {
                  return {
                    document_id: 'bridge_products',
                    page_context: 'bridge',
                    target: {label: expectedLabel},
                    snapshot: {url: location.origin + location.pathname, captured_at: new Date().toISOString(), text: '{}'},
                    list_kind: 'products',
                    tables: [[['Tên sản phẩm', 'Giá', 'Kho hàng'], ...domTableRows]],
                    inventory: domInventory,
                    pagination: {recognized: false, current: 1, has_next: null, at_last: false},
                    coverage: {pages_read: 1, pagination_complete: false, scope: 'observed_list', rows_read: domInventory.length}
                  };
                }
              }
            }
            if (json) {
              const rawItems = json.data?.products || json.data?.list || json.data?.mpsku_list || [];
              const inventory = rawItems.map(p => {
                const stock = p.stock_detail?.total_available_stock ?? p.stock_detail?.total_seller_stock ?? p.stock ?? null;
                const sku = p.parent_sku || p.item_sku || p.sku || String(p.id || '');
                return {
                  key: 'product:' + (p.id || p.item_id || p.mtsku_id || sku),
                  name: String(p.name || p.item_name || p.mpsku_name || 'Sản phẩm'),
                  sku: String(sku),
                  stock: stock === null ? null : String(stock),
                  identity_verified: Boolean(p.id || sku)
                };
              });
              const tableRows = rawItems.map(p => {
                const name = String(p.name || p.item_name || p.mpsku_name || 'Sản phẩm');
                const price = String(p.price_detail?.selling_price_min ?? p.price_detail?.price_min ?? p.price ?? '—');
                const stock = String(p.stock_detail?.total_available_stock ?? p.stock_detail?.total_seller_stock ?? p.stock ?? '—');
                return [name, price, stock];
              });
              return {
                document_id: 'bridge_products',
                page_context: 'bridge',
                target: {label: expectedLabel},
                snapshot: {url: location.origin + location.pathname, captured_at: new Date().toISOString(), text: '{}'},
                list_kind: 'products',
                tables: [[['Tên sản phẩm', 'Giá', 'Kho hàng'], ...tableRows]],
                inventory,
                pagination: {recognized: false, current: 1, has_next: null, at_last: false},
                coverage: {pages_read: 1, pagination_complete: false, scope: 'observed_list', rows_read: inventory.length}
              };
            }
          }
          if (resKey === 'orders') {
            const endpoints = [
              '/api/v3/order/search_order_list?page_number=1&page_size=20',
              '/api/v3/order/get_order_list/?page_number=1&page_size=20',
              '/api/v3/order/get_order_list_v2?page_number=1&page_size=20',
              '/api/v3/sale/order/get_order_list?page_number=1&page_size=20',
              '/api/v3/order/get_shipment_list?page_number=1&page_size=20',
              '/api/v3/order/get_todo_list/'
            ];
            let json = null;
            for (const ep of endpoints) {
              try {
                const res = await window.fetch(withCds(ep), {
                  headers: {'Accept': 'application/json'},
                  credentials: 'include', redirect: 'error', signal: AbortSignal.timeout(5000)
                });
                if (res.ok) {
                  const j = await res.json();
                  if (j.code === 0 && (Array.isArray(j.data?.orders) || Array.isArray(j.data?.order_list) || Array.isArray(j.data?.list) || Array.isArray(j.data?.orders_list) || Array.isArray(j.data?.items) || j.data?.total !== undefined)) {
                    json = j;
                    break;
                  }
                }
              } catch {}
            }
            if (json) {
              const rawOrders = json.data?.orders || json.data?.order_list || json.data?.list || json.data?.orders_list || json.data?.items || [];
              const orders = rawOrders.map(o => [
                String(o.order_sn || o.order_id || o.ordersn || 'Đơn hàng'),
                String(o.status_name || o.status_desc || o.status || 'Đang xử lý')
              ]);
              return {
                document_id: 'bridge_orders',
                page_context: 'bridge',
                target: {label: expectedLabel},
                snapshot: {url: location.origin + location.pathname, captured_at: new Date().toISOString(), text: '{}'},
                list_kind: 'orders',
                empty_confirmed: orders.length === 0 && (json.data?.total === 0 || json.data?.total_count === 0),
                tables: [[['Mã đơn hàng', 'Trạng thái'], ...orders]],
                pagination: {recognized: false, current: 1, has_next: null, at_last: false},
                coverage: {pages_read: 1, pagination_complete: false, scope: 'observed_list', rows_read: orders.length}
              };
            }
          }
        } catch {
          return null;
        }
        return null;
      },
      args: [key, targetLabel]
    });
    return results?.[0]?.result || null;
  } catch {
    return null;
  }
}

function resourceFromSeed(seed, key) {
  if (!resourcePresent(seed, key)) return null;
  const complete = key !== 'dashboard' && seed.pagination?.recognized === true
    && seed.pagination.current === 1 && seed.pagination.at_last === true && seed.pagination.has_next === false && !seed.filtered;
  return {...seed, coverage: {pages_read: 1, pagination_complete: complete,
    scope: key === 'dashboard' ? 'dashboard_period_unverified' : seed.filtered ? 'filtered_list' : 'observed_list',
    rows_read: key === 'products' ? inventoryRows(seed).length : (seed.tables || []).reduce((n, table) => n + Math.max(0, table.length - 1), 0)}};
}

async function run(connection, resources, controller) {
  const errors = {}, completed = [];
  const timer = setTimeout(() => controller.abort(Error('Đồng bộ đã đạt giới hạn thời gian.')), JOB_MS);
  try {
    const bound = await boundTab(connection);
    if (!bound || !isSellerUrl(bound.url)) throw Error('Tab Kênh Người Bán đã đóng hoặc chuyển sang trang khác.');

    // 1. In-tab read from bound tab
    const seed = await pageMessage(connection, {kind: 'read'});
    if (!seed || seed.target?.label !== connection.target.label) {
      throw Error('Không xác nhận được tài khoản Shopee trên tab này.');
    }

    // Auto-save any resource already observed on current page seed
    for (const key of KEYS) {
      const page = resourceFromSeed(seed, key);
      if (page) {
        await saveCachedPage(key, connection.id, page);
        completed.push(key);
      }
    }

    for (const key of resources) {
      controller.signal.throwIfAborted();
      if (completed.includes(key)) continue;

      await update(connection.id, data => {
        data.job = {...data.job, status: 'running', resource: key, pages_read: 0, records_read: 0};
      });

      // Recheck the same account after the asynchronous bridge read too. A
      // response cannot label itself as belonging to the expected account.
      const before = await pageMessage(connection, {kind: 'target_status'});
      if (!before.target_matches) throw Error('Tài khoản shop đã đổi.');
      let page = await tryDataBridge(connection.tab_id, key, connection.target.label);
      controller.signal.throwIfAborted();
      const after = await pageMessage(connection, {kind: 'target_status'});
      await current(connection.id);
      if (!after.target_matches || before.document_id !== after.document_id || before.page_context !== after.page_context) throw Error('Trang hoặc tài khoản shop đã đổi khi đồng bộ.');
      if (page) {
        if (!resourcePresent(page, key)) continue;
        if (!page.coverage) page.coverage = resourceFromSeed(page, key).coverage;
        await saveCachedPage(key, connection.id, page);
        completed.push(key);
      } else {
        errors[key] = {
          error: 'Mục ' + ({products: 'Sản phẩm', orders: 'Đơn hàng', dashboard: 'Tổng quan'}[key]) + ' chưa được đọc đầy đủ trong phiên này. Dữ liệu hiện có vẫn được giữ; bấm Cập nhật để thử lại.'
        };
      }
    }

    const stored = await cache(connection.id);
    const finalStatus = resources.every(r => completed.includes(r) && stored.pages[r]?.coverage?.pagination_complete) ? 'completed' : 'partial';
    await update(connection.id, data => {
      data.job = {...data.job, status: finalStatus, errors, owned_tab_id: null};
    });
    return {status: finalStatus, pages: completed, errors};
  } catch (error) {
    await update(connection.id, data => {
      data.job = {
        ...data.job,
        status: controller.signal.aborted ? 'cancelled' : 'failed',
        errors: {...errors, sync: {error: error.message}},
        owned_tab_id: null
      };
    }).catch(() => {});
    return {status: controller.signal.aborted ? 'cancelled' : 'failed', error: error.message};
  } finally {
    clearTimeout(timer);
    jobs.delete(connection.id);
  }
}

export async function syncShopeeData(id, resources = KEYS) {
  const connection = await current(id);
  if (jobs.has(id)) return {status: 'already_running'};
  if (!Array.isArray(resources) || !resources.length || resources.some(key => !KEYS.includes(key))) {
    throw Error('Nguồn đồng bộ không hợp lệ.');
  }
  const controller = new AbortController();
  const job = {controller, promise: null};
  jobs.set(id, job);
  job.promise = (async () => {
    try {
      await update(id, data => {
        data.job = {status: 'running', resource: resources[0], pages_read: 0, records_read: 0};
      });
      return await run(connection, resources, controller);
    } catch (error) {
      jobs.delete(id);
      return {status: 'failed', error: error.message};
    }
  })();
  return {status: 'started'};
}

export function cancelSync(id) {
  jobs.get(id)?.controller.abort(Error('Đã dừng đồng bộ theo yêu cầu.'));
}
