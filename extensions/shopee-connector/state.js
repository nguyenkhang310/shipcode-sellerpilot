export const SOURCE = 'https://banhang.shopee.vn';
export const API = 'http://127.0.0.1:8000/api/v1';
export const isSellerUrl = value => { try { return new URL(value).origin === SOURCE; } catch { return false; } };
let gate = Promise.resolve();
export async function mutate(update) {
  const next = gate.then(async () => {
    const {sellerpilot = {id: crypto.randomUUID(), mode: 'shopee', tab_id: null, conversations: {}, drafts: {}}} = await chrome.storage.local.get('sellerpilot');
    const result = await update(sellerpilot);
    try {await chrome.storage.local.set({sellerpilot}); await chrome.storage.local.remove('scope:' + sellerpilot.id);}
    catch {throw Error('Bộ nhớ extension đã đầy hoặc không lưu được. Xóa lịch sử/ảnh cũ rồi thử lại.');}
    return result;
  });
  gate = next.catch(() => {}); return next;
}
export async function state() {
  await gate;
  const {sellerpilot} = await chrome.storage.local.get('sellerpilot');
  return sellerpilot ? structuredClone(sellerpilot) : mutate(value => structuredClone(value));
}
export async function connectionStatus() {
  const connection = await state();
  const result = {id: connection.id, mode: connection.mode, tab_id: connection.tab_id, target: connection.target || null,
    target_selection_pending: Boolean(connection.target_selection?.expires > Date.now())};
  if (connection.mode === 'local') return {...result, tab_status: 'local'};
  if (!connection.tab_id) return {...result, tab_status: 'unlinked'};
  const tab = await chrome.tabs.get(connection.tab_id).catch(() => null);
  if (tab && isSellerUrl(tab.url) && tab.active && connection.target) {
    try {return {...result, tab_status: 'linked', ...await pageMessage(connection, {kind: 'target_status'})};}
    catch {return {...result, tab_status: 'linked', target_matches: false};}
  }
  return {...result, tab_status: !tab ? 'closed' : isSellerUrl(tab.url) && tab.active ? 'linked' : 'wrong_tab'};
}
export async function boundTab(connection) {
  if (!connection.tab_id) throw Error('Mở Kênh Người Bán Shopee rồi bấm Liên kết tab.');
  const tab = await chrome.tabs.get(connection.tab_id).catch(() => null);
  if (!tab || !isSellerUrl(tab.url) || !tab.active) throw Error('Quay lại đúng tab Shopee đã liên kết, hoặc liên kết tab mới.');
  return tab;
}
export async function pageMessage(connection, message) {
  const tab = await boundTab(connection);
  if (['read', 'fill'].includes(message.kind) && !connection.target?.label)
    throw Error('Chọn tài khoản Shopee để bắt đầu. Mở Kết nối → Chọn tài khoản trên trang.');
  await chrome.scripting.executeScript({target: {tabId: tab.id}, files: ['content/shopee.js']});
  const result = await chrome.tabs.sendMessage(tab.id, {...message, target: connection.target || null});
  if (!result?.ok) throw Error(result?.error || 'Chưa đọc được trang Shopee.');
  return result.data;
}
export async function selectTarget() {
  const connection = await state();
  if (connection.mode !== 'shopee') throw Error('Chuyển sang Shopee trước khi chọn tài khoản.');
  await boundTab(connection);
  const nonce = crypto.randomUUID();
  await mutate(value => {
    if (value.id !== connection.id) throw Error('Kết nối đã đổi. Thử lại.');
    value.target_selection = {nonce, expires: Date.now() + 30000};
  });
  return pageMessage(connection, {kind: 'select_target', nonce});
}
export async function completeTarget(message, sender) {
  return mutate(async value => {
    const pending = value.target_selection;
    if (value.mode !== 'shopee' || sender.tab?.id !== value.tab_id || sender.frameId !== 0
      || !isSellerUrl(sender.url) || !pending || pending.nonce !== message.nonce || pending.expires <= Date.now())
      throw Error('Yêu cầu liên kết tài khoản đã hết hạn hoặc không đúng tab.');
    if (typeof message.label !== 'string' || !message.label.trim() || message.label.length > 80 || /[\r\n\x00-\x1f]/.test(message.label))
      throw Error('Tên tài khoản không hợp lệ.');
    const label = message.label.normalize('NFC').trim();
    // Recheck the selected label in the live document before changing scopes.
    const page = await pageMessage({...value, target: {label}}, {kind: 'read'});
    if (page.document_id !== message.document_id) throw Error('Trang đã đổi. Chọn lại tài khoản.');
    if (value.target?.label !== label) {
      if (Object.keys(value.conversations).length) {
        const archived = structuredClone(value); delete archived.target_selection;
        await chrome.storage.local.set({['scope:' + value.id]: archived});
      }
      value.id = crypto.randomUUID(); value.conversations = {}; value.drafts = {}; value.results = {};
      value.deleted_conversations = []; value.image_requests = {}; value.created_at = new Date().toISOString();
    }
    value.target = {label, verification: 'browser_label', selected_at: new Date().toISOString()};
    delete value.target_selection;
    return {id: value.id, target: value.target};
  });
}
export async function bindCurrentTab(mode) {
  if (!['local', 'shopee'].includes(mode)) throw Error('Nguồn không hợp lệ.');
  const [tab] = await chrome.tabs.query({active: true, lastFocusedWindow: true});
  if (mode === 'shopee' && !isSellerUrl(tab?.url)) throw Error('Bạn mở https://banhang.shopee.vn/ rồi thử lại.');
  const next = gate.then(async () => {
    const {sellerpilot} = await chrome.storage.local.get('sellerpilot');
    const fresh = {id: crypto.randomUUID(), mode, tab_id: mode === 'shopee' ? tab.id : null,
      conversations: {}, drafts: {}, results: {}, deleted_conversations: [], image_requests: {}, created_at: new Date().toISOString()};
    const writes = {sellerpilot: fresh};
    if (sellerpilot && Object.keys(sellerpilot.conversations).length) writes['scope:' + sellerpilot.id] = sellerpilot;
    await chrome.storage.local.set(writes); // Atomic archive + source change; no silent history deletion.
    return {id: fresh.id, mode};
  });
  gate = next.catch(() => {}); return next;
}
export async function listScopes() {
  const all = await chrome.storage.local.get(null);
  return Object.entries(all).filter(([key, value]) => key.startsWith('scope:') && value.id !== all.sellerpilot?.id).map(([, value]) =>
    ({id: value.id, mode: value.mode, target: value.target || null, created_at: value.created_at, turns: Object.keys(value.conversations).length}));
}
export async function restoreScope(id) {
  if (!/^[a-z0-9-]{36}$/i.test(id || '')) throw Error('Phiên không hợp lệ.');
  const next = gate.then(async () => {
    const values = await chrome.storage.local.get(null), old = values.sellerpilot, saved = values['scope:' + id];
    if (!saved) throw Error('Không tìm thấy phiên.');
    if (saved.mode === 'shopee') {await boundTab(saved); await pageMessage(saved, {kind: 'read'});}
    const writes = {sellerpilot: saved};
    if (old && Object.keys(old.conversations).length) writes['scope:' + old.id] = old;
    await chrome.storage.local.set(writes);
    await chrome.storage.local.remove('scope:' + id);
    return {id: saved.id, mode: saved.mode};
  });
  gate = next.catch(() => {}); return next;
}
