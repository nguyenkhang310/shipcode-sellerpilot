const {test} = require('node:test');
const assert = require('node:assert/strict');
let saved, tabs, active, detected, calls, beforeRead;
const source = 'https://banhang.shopee.vn/';
global.chrome = {
  storage: {local: {
    get: async key => structuredClone({[key]: saved[key]}),
    set: async value => Object.assign(saved, structuredClone(value)),
    remove: async key => {delete saved[key];},
  }},
  tabs: {
    get: async id => {if (!tabs.has(id)) throw Error('closed'); return tabs.get(id);},
    query: async () => active,
    create: async () => assert.fail('Connecting must not open a tab'),
    update: async () => assert.fail('Connecting must not navigate or focus a tab'),
    sendMessage: async (id, message) => {
      calls.push({id, kind: message.kind});
      if (message.kind === 'auto_detect_target') return {ok: true, data: {label: detected}};
      assert.equal(message.kind, 'read');
      assert.equal(message.target.label, detected);
      await beforeRead?.();
      return {ok: true, data: {document_id: 'verified-document'}};
    },
  },
  scripting: {executeScript: async () => {}},
};
function reset() {
  saved = {sellerpilot: {id: crypto.randomUUID(), mode: 'shopee', tab_id: 7,
    target: {label: 'shop-a'}, conversations: {history: {turns: []}}, drafts: {draft: {name: 'Keep me'}}}};
  tabs = new Map(); active = [{id: 8, url: source}]; detected = 'shop-a'; calls = []; beforeRead = null;
}
const load = () => import('../state.js');

test('first connection reads and verifies the active shop before saving it', async () => {
  reset(); const state = await load();
  delete saved.sellerpilot.target; saved.sellerpilot.tab_id = null; tabs.set(8, active[0]);
  const result = await state.autoConnectShopee();
  assert.equal(result.tab_id, 8); assert.equal(result.target.label, 'shop-a');
  assert.deepEqual(calls.map(c => c.kind), ['auto_detect_target', 'read']);
});

test('closed, missing and repurposed tab IDs reconnect the same shop without replacing its scope', async () => {
  for (const old of [null, {id: 7, url: 'https://example.test/'}, {id: 7, url: 'chrome://newtab/'}]) {
    reset(); const state = await load();
    if (old) tabs.set(7, old);
    tabs.set(8, active[0]);
    const original = structuredClone(saved.sellerpilot);
    saved['shopee_sync:' + original.id] = {pages: {products: {fixture: true}}};
    const result = await state.autoConnectShopee();
    assert.equal(result.id, original.id); assert.equal(result.tab_id, 8);
    assert.deepEqual(saved.sellerpilot.conversations, original.conversations);
    assert.deepEqual(saved.sellerpilot.drafts, original.drafts);
    assert(saved['shopee_sync:' + original.id].pages.products.fixture);
    assert.equal(await state.autoConnectShopee(), null, 'Polling must not reconnect or trigger sync again');
  }
});

test('a live linked tab is preserved even when another shop tab is active', async () => {
  reset(); const state = await load(); tabs.set(7, {id: 7, url: source}); detected = 'shop-b';
  assert.equal(await state.autoConnectShopee(), null); assert.deepEqual(calls, []);
});

test('different, ambiguous, malformed or non-seller targets never inherit the old shop', async () => {
  const state = await load();
  for (const label of ['shop-b', null, '', 'bad\nlabel', {bad: true}]) {
    reset(); tabs.set(8, active[0]); detected = label;
    assert.equal(await state.autoConnectShopee(), null); assert.equal(saved.sellerpilot.tab_id, 7);
    assert(!calls.some(c => c.kind === 'read'));
  }
  reset(); active = [{id: 8, url: 'https://banhang.shopee.vn.evil.test/'}];
  assert.equal(await state.autoConnectShopee(), null); assert.deepEqual(calls, []);
});

test('manual target selection and local mode cannot be overridden by auto-connect polling', async () => {
  const state = await load();
  for (const patch of [{mode: 'local'}, {target_selection: {expires: Date.now() + 30000}}]) {
    reset(); Object.assign(saved.sellerpilot, patch);
    assert.equal(await state.autoConnectShopee(), null); assert.deepEqual(calls, []);
  }
});

test('identical account labels on different marketplaces cannot share a recovered connection', async () => {
  reset(); const state = await load();
  active = [{id: 8, url: 'https://seller-vn.tiktok.com/'}]; tabs.set(8, active[0]);
  assert.equal(await state.autoConnectShopee(), null); assert.deepEqual(calls, []);
  saved.sellerpilot.target.origin = 'https://seller-vn.tiktok.com';
  const result = await state.autoConnectShopee();
  assert.equal(result.target.origin, 'https://seller-vn.tiktok.com'); assert.equal(result.tab_id, 8);
});

test('a rejected live read or a concurrent scope change does not bind the candidate tab', async () => {
  reset(); const state = await load(); tabs.set(8, active[0]);
  beforeRead = () => {throw Error('Account no longer matches');};
  await assert.rejects(state.autoConnectShopee(), /no longer matches/);
  assert.equal(saved.sellerpilot.tab_id, 7);
  beforeRead = () => state.mutate(value => {value.id = 'new-scope';});
  assert.equal(await state.autoConnectShopee(), null);
  assert.equal(saved.sellerpilot.id, 'new-scope'); assert.equal(saved.sellerpilot.tab_id, 7);
});

test('worker resumes the verified sender through the current autofill handler and starts auto-connect sync once', async () => {
  const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), ts = require('typescript');
  const worker = path.resolve(__dirname, '../service-worker.js');
  const code = ts.transpileModule(fs.readFileSync(worker, 'utf8'), {compilerOptions: {module: ts.ModuleKind.CommonJS}}).outputText;
  let listener; const resumed = [], synced = [];
  const modules = {
    './state.js': {autoConnectShopee: async () => ({id: 'verified-scope'})},
    './api.js': {continueFormFill: async sender => {resumed.push(sender); return {status: 'waiting'};}},
    './shopee-sync.js': {syncShopeeData: async id => synced.push(id)},
  };
  const chrome = {sidePanel: {setPanelBehavior: async () => {}}, runtime: {
    id: 'fixture', getURL: () => 'chrome-extension://fixture/',
    onInstalled: {addListener() {}}, onMessage: {addListener: value => {listener = value;}},
  }};
  vm.runInNewContext(code, {require: name => modules[name], exports: {}, chrome});
  const sender = {id: 'fixture', frameId: 0, tab: {id: 8}, url: source};
  const response = await new Promise(resolve => listener({kind: 'autofill_continue', scan: {untrusted: true}}, sender, resolve));
  assert.equal(response.ok, true); assert.equal(response.data.status, 'waiting');
  assert.equal(resumed[0], sender, 'Sender verification must use Chrome metadata, never page-supplied scan data');
  assert.equal(listener({kind: 'autofill_continue'}, {...sender, id: 'untrusted'}, () => assert.fail('Untrusted sender')), undefined);
  const auto = await new Promise(resolve => listener({kind: 'auto_connect'}, {id: 'fixture', url: 'chrome-extension://fixture/index.html'}, resolve));
  assert.equal(auto.ok, true); assert.deepEqual(synced, ['verified-scope']);
});
