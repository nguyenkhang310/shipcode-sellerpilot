import {state, connectionStatus, bindCurrentTab, pageMessage, listScopes, restoreScope, selectTarget, completeTarget, autoConnectShopee, SOURCE} from './state.js';
import {handleApi, backend} from './api.js';
import {syncShopeeData, getCachedPage, getSyncStatus, cancelSync} from './shopee-sync.js';
const active = new Map();
const chatJobs = new Map();
chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true}).catch(() => {});
chrome.runtime.onInstalled.addListener(() => {void chrome.sidePanel.setPanelBehavior({openPanelOnActionClick: true});});
chrome.runtime.onMessage.addListener((message, sender, reply) => {
  if (message?.kind === 'target_selected' && sender.id === chrome.runtime.id && sender.tab) {
    Promise.resolve().then(async () => {
      if (active.size) throw Error('Dừng yêu cầu AI trước khi đổi tài khoản.');
      const res = await completeTarget(message, sender);
      void syncShopeeData(res.id).catch(() => {});
      return res;
    }).then(data => reply({ok: true, data}), error => reply({ok: false, error: error.message}));
    return true;
  }
  // Only the packaged UI may call the backend or mutate the connection.
  if (sender.id !== chrome.runtime.id || sender.tab || !sender.url?.startsWith(chrome.runtime.getURL(''))) return;
  Promise.resolve().then(async () => {
    if (message.kind === 'connection') {const value = await state(); return {id: value.id, mode: value.mode, tab_id: value.tab_id};}
    if (message.kind === 'connection_status') return connectionStatus();
    if (message.kind === 'auto_connect') {
      const res = await autoConnectShopee();
      if (res?.id) void syncShopeeData(res.id).catch(() => {});
      return res;
    }
    if (message.kind === 'sync_now') {
      const value = await state();
      return syncShopeeData(value.id, message.resources);
    }
    if (message.kind === 'sync_cancel') {
      cancelSync((await state()).id); return {};
    }
    if (message.kind === 'sync_status') {
      const value = await state();
      return getSyncStatus(value.id);
    }
    if (message.kind === 'get_cached_page') {
      const value = await state();
      return getCachedPage(message.page_key, value.id);
    }
    if (message.kind === 'select_target') {
      if (active.size) throw Error('Dừng yêu cầu AI trước khi đổi tài khoản.');
      return selectTarget();
    }
    if (message.kind === 'bind_tab') {
      if (active.size) throw Error('Dừng yêu cầu đang chạy trước khi đổi kết nối.');
      return bindCurrentTab(message.mode);
    }
    if (message.kind === 'list_scopes') return listScopes();
    if (message.kind === 'restore_scope') {
      if (active.size) throw Error('Dừng yêu cầu đang chạy trước khi đổi kết nối.');
      return restoreScope(message.scope_id);
    }
    if (message.kind === 'scan') {
      const conn = await state();
      // A one-page read must not overwrite a complete paginated resource.
      return pageMessage(conn, {kind: 'read'});
    }
    if (message.kind === 'bind_field') return pageMessage(await state(), {kind: 'bind', field: message.field});
    if (message.kind === 'backend_health') return backend('/health');
    if (message.kind === 'open_store') {
      const value = await state();
      const path = typeof message.path === 'string' && /^\/(?!\/)/.test(message.path) ? message.path : '/seller';
      if (value.mode === 'shopee' && path !== '/seller') throw Error('Chưa ánh xạ đường dẫn local này sang Shopee thật. Mở từ Kênh Người Bán.');
      await chrome.tabs.create({url: value.mode === 'local' ? 'http://127.0.0.1:5011' + path : SOURCE + '/?is_from_login=true'}); return {};
    }
    if (message.kind === 'cancel') {active.get(message.id)?.abort(); return {};}
    if (message.kind !== 'api') throw Error('Thao tác không hỗ trợ.');
    if (!/^[a-z0-9-]{36}$/i.test(message.id || '') || !['GET', 'POST', 'PATCH', 'DELETE'].includes(message.method)
        || typeof message.path !== 'string' || message.path.length > 2000
        || (message.body !== null && (typeof message.body !== 'string' || message.body.length > 7000000))) throw Error('Yêu cầu không hợp lệ.');
    const value = await state();
    if (value.id !== message.connection_id) throw Error('Kết nối đã thay đổi. Mở lại app.');
    const controller = new AbortController();
    const cancellation = message.path.match(/^\/chat\/requests\/([a-z0-9-]+)\/cancel$/i);
    if (cancellation) chatJobs.get(value.id + ':' + cancellation[1])?.controller.abort();
    let chatKey;
    if (message.path === '/chat') {
      const body = JSON.parse(message.body || '{}');
      if (!body.request_id) throw Error('Thiếu mã tin nhắn.');
      chatKey = value.id + ':' + body.request_id;
      const existing = chatJobs.get(chatKey);
      if (existing) {
        if (value.mode === 'local' && existing.authorization !== message.authorization) throw Object.assign(Error('Vui lòng đăng nhập lại.'), {status: 401});
        if (existing.body !== message.body) throw Error('Mã tin nhắn đã dùng cho nội dung khác.');
        return existing.promise;
      }
    }
    active.set(message.id, controller);
    const promise = handleApi(message.path, message.method, message.body, controller.signal, message.authorization);
    if (chatKey) chatJobs.set(chatKey, {body: message.body, controller, promise, authorization: message.authorization});
    try {return await promise;}
    finally {active.delete(message.id); if (chatKey) chatJobs.delete(chatKey);}
  }).then(data => reply({ok: true, data}), error => reply({ok: false, status: error.status || 503, error: error.message}));
  return true;
});
