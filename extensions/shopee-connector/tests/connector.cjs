const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
let saved = {}, calls = [];
global.chrome = {
  storage: {local: {get: async key => structuredClone(key === null ? saved : {[key]: saved[key]}), set: async value => {Object.assign(saved, structuredClone(value));}, remove: async key => {delete saved[key];}}},
  tabs: {get: async id => ({id, active: true, url: 'https://banhang.shopee.vn/'}),
    query: async () => [{id: 7, active: true, url: 'https://banhang.shopee.vn/'}],
    sendMessage: async (_id, message) => ({ok: true, data: message.kind === 'read' ? {
      document_id: 'fixture-doc', snapshot: {url: 'https://banhang.shopee.vn/', title: 'Fixture', text: '2 đơn', scope: 'visible_page', captured_at: new Date().toISOString()}
    } : message.kind === 'target_status' ? {target_matches: true} : {report: ['name', 'description', 'price_vnd', 'stock'].map(field => ({field, status: 'filled'})), submitted: false}})},
  scripting: {executeScript: async () => {}}, runtime: {getURL: value => 'chrome-extension://fixture/' + value},
};
global.fetch = async (url, options) => {
  calls.push({url, options});
  if (url.endsWith('connection.local.json')) return {json: async () => ({token: 'test-token-only'})};
  return {ok: true, json: async () => ({data: {status: 'ok'}})};
};
const load = () => Promise.all([import('../state.js'), import('../api.js')]);

test('Shopee source never falls through to the local shop API', async () => {
  const [state, api] = await load(); saved = {}; calls = [];
  await state.bindCurrentTab('shopee');
  await assert.rejects(api.handleApi('/management/dashboard?days=1', 'GET', null), /Chưa xác minh/);
  await assert.rejects(api.handleApi('/proposals/1/confirm', 'POST', '{}'), /chưa được nối/);
  assert.deepEqual(calls, []);
  assert.equal(state.isSellerUrl('https://banhang.shopee.vn.evil.example/'), false);
  assert.equal(state.isSellerUrl('http://banhang.shopee.vn/'), false);
});

test('gallery replay, pinning and deletion preserve scope without duplicating images', async () => {
  const [state, api] = await load(); saved = {};
  await state.bindCurrentTab('shopee');
  await state.mutate(connection => {connection.target = {label: 'fixture-shop'};});
  const payload = JSON.stringify({conversation_id: crypto.randomUUID(), request_id: crypto.randomUUID(), images_base64: ['YWJjZA==']});
  const first = await api.handleApi('/product-drafts/images-data', 'POST', payload);
  const second = await api.handleApi('/product-drafts/images-data', 'POST', payload);
  assert.equal(first.data.product_draft.id, second.data.product_draft.id);
  let stored = await state.state();
  const id = first.data.conversation_id;
  assert.equal(Object.keys(stored.drafts).length, 1);
  assert.equal(stored.conversations[id].turns.length, 1);
  assert.equal(stored.conversations[id].turns[0].response.product_draft.preview_urls, undefined);
  const restored = await api.handleApi('/conversations/' + id, 'GET', null);
  assert.equal(restored.data.turns[0].response.product_draft.preview_urls.length, 1);
  await api.handleApi('/conversations/' + id, 'PATCH', JSON.stringify({is_pinned: true}));
  assert.equal((await api.handleApi('/conversations', 'GET', null)).data.items[0].is_pinned, true);
  const previous = stored.id;
  await state.bindCurrentTab('local');
  assert.equal((await state.state()).mode, 'local');
  assert.equal((await state.listScopes())[0].id, previous);
  await state.restoreScope(previous);
  await api.handleApi('/conversations/' + id, 'DELETE', null);
  stored = await state.state();
  assert.equal(Object.keys(stored.drafts).length, 0);
  assert.equal(Object.keys(stored.conversations).length, 0);
  assert.equal(JSON.stringify(stored).includes('YWJjZA=='), false);
});

test('explicit local mode forwards only the fixed local API allowlist', async () => {
  const [state, api] = await load(); saved = {}; calls = [];
  await state.bindCurrentTab('local');
  await api.handleApi('/management/dashboard?days=1', 'GET', null);
  assert.equal(calls[0].url, 'http://127.0.0.1:8000/api/v1/management/dashboard?days=1');
  await assert.rejects(api.handleApi('https://evil.example/collect', 'POST', '{}'), /không được phép/);
  await assert.rejects(api.handleApi('/../../private', 'GET', null), /không được phép/);
  assert.equal(calls.length, 1);
});

test('image uploads require the selected account to still match the live tab', async () => {
  const [state, api] = await load(); saved = {};
  await state.bindCurrentTab('shopee');
  const payload = JSON.stringify({images_base64: ['YWJjZA=='], conversation_id: crypto.randomUUID(), request_id: crypto.randomUUID()});
  await assert.rejects(api.handleApi('/product-drafts/images-data', 'POST', payload), /Chọn tài khoản/);
  await state.mutate(value => {value.target = {label: 'fixture-shop'};});
  const original = chrome.tabs.sendMessage;
  try {
    chrome.tabs.sendMessage = async () => ({ok: true, data: {target_matches: false}});
    await assert.rejects(api.handleApi('/product-drafts/images-data', 'POST', payload), /không còn khớp/);
    assert.equal((await state.connectionStatus()).target_matches, false);
    assert.deepEqual((await state.state()).drafts, {});
  } finally {chrome.tabs.sendMessage = original;}
});

test('form-fill result cannot claim product publication', async () => {
  const [state, api] = await load(); saved = {};
  await state.bindCurrentTab('shopee');
  await state.mutate(connection => {connection.target = {label: 'fixture-shop'};});
  await state.mutate(connection => {connection.drafts[1] = {id: 1, status: 'ready', name: 'Bàn phím', description: 'Màu trắng', price_vnd: 500000, stock: 12};});
  const result = await api.handleApi('/product-drafts/1/publish', 'POST', '{}');
  assert.equal(result.data.status, 'filled');
  assert.notEqual(result.data.status, 'published');
});

test('account binding requires a fresh selection from the bound top-level tab, rotates history and rejects replay', async () => {
  const [state] = await load(); saved = {};
  await state.bindCurrentTab('shopee');
  await assert.rejects(state.pageMessage(await state.state(), {kind: 'read'}), /Chọn tài khoản/);
  await state.selectTarget();
  const pending = (await state.state()).target_selection;
  const message = {nonce: pending.nonce, document_id: 'fixture-doc', label: 'shop-a'};
  const sender = {tab: {id: 7}, frameId: 0, url: 'https://banhang.shopee.vn/'};
  await assert.rejects(state.completeTarget(message, {...sender, tab: {id: 8}}), /không đúng tab/);
  await assert.rejects(state.completeTarget(message, {...sender, frameId: 1}), /không đúng tab/);
  await assert.rejects(state.completeTarget(message, {...sender, url: 'https://evil.example/'}), /không đúng tab/);
  await state.completeTarget(message, sender);
  assert.equal((await state.state()).target.label, 'shop-a');
  await assert.rejects(state.completeTarget(message, sender), /hết hạn/);
  const before = await state.state();
  await state.mutate(value => {value.conversations.test = {turns: [{message: 'shop-a secret'}]};});
  await state.selectTarget();
  const next = await state.state();
  await state.completeTarget({...message, nonce: next.target_selection.nonce, label: 'shop-b'}, sender);
  const after = await state.state();
  assert.notEqual(after.id, before.id);
  assert.deepEqual(after.conversations, {});
  assert.equal(saved['scope:' + before.id].target.label, 'shop-a');
  assert.equal((await state.connectionStatus()).target.label, 'shop-b');
  await state.selectTarget();
  const expired = await state.state();
  await state.mutate(value => {value.target_selection.expires = Date.now() - 1;});
  await assert.rejects(state.completeTarget({...message, nonce: expired.target_selection.nonce}, sender), /hết hạn/);
});

test('manifest has no cookie, debugger, remote-code or all-sites permissions', () => {
  const manifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../manifest.json')));
  assert.equal(manifest.manifest_version, 3);
  for (const permission of ['cookies', 'debugger', 'history', '<all_urls>']) assert(!manifest.permissions.includes(permission));
  assert.deepEqual(manifest.host_permissions, ['https://banhang.shopee.vn/*', 'http://127.0.0.1/*']);
  assert(manifest.content_security_policy.extension_pages.includes("script-src 'self';"));
});

test('saved tab binding stays linked after reopening; wrong or closed tabs are distinct', async () => {
  const [state] = await load(); saved = {};
  assert.equal((await state.connectionStatus()).tab_status, 'unlinked');
  await state.bindCurrentTab('shopee');
  assert.equal((await state.connectionStatus()).tab_status, 'linked');
  const original = chrome.tabs.get;
  try {
    chrome.tabs.get = async id => ({id, active: false, url: 'https://banhang.shopee.vn/'});
    assert.equal((await state.connectionStatus()).tab_status, 'wrong_tab');
    chrome.tabs.get = async () => {throw Error('Closed tab');};
    assert.equal((await state.connectionStatus()).tab_status, 'closed');
  } finally {chrome.tabs.get = original;}
});

test('missing connector routes explain stale backend, while lost jobs and network errors stay distinct', async () => {
  const [, api] = await load();
  const original = global.fetch;
  try {
    global.fetch = async url => url.endsWith('connection.local.json')
      ? {json: async () => ({token: 'test-token-only'})}
      : {ok: false, status: 404, json: async () => ({detail: 'Not Found'})};
    for (const route of ['/health', '/requests']) {
      await assert.rejects(api.backend(route), error => error.status === 404 && /Backend đang chạy bản cũ/.test(error.message));
    }
    await assert.rejects(api.backend('/requests/connection/job'), /Không tìm thấy tác vụ/);
    global.fetch = async () => {throw TypeError('Failed to fetch');};
    await assert.rejects(api.backend('/health'), /127\.0\.0\.1:8000/);
  } finally {global.fetch = original;}
});
