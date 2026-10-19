// Run with React 19.2.3 + react-test-renderer 19.2.3 in QA_NODE_MODULES,
// or install the renderer locally. No real API or seller database is used.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const qa = name => require(process.env.QA_NODE_MODULES ? path.join(process.env.QA_NODE_MODULES, name) : name);
const React = qa('react'), { create, act } = qa('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

async function mount(live = false) {
  const calls = [], listeners = [], timers = [];
  const app = { currentState: 'active', addEventListener: (_, fn) => {
    listeners.push(fn); return { remove() { listeners.splice(listeners.indexOf(fn), 1); } };
  } };
  const filename = path.resolve(__dirname, '../src/features/dashboard/useManagement.ts');
  const code = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  class ApiError extends Error {}
  const modules = {
    react: React, 'react-native': { AppState: app }, '../../api/client': { ApiError },
    '../../api/sellerPilot': { getManagement: (days, signal) => new Promise((resolve, reject) => {
      calls.push({ days, signal, resolve, reject });
    }) },
  };
  const loaded = { exports: {} };
  vm.runInNewContext('(function(require,module,exports){' + code + '\n})', {
    AbortController, Date, Map, JSON, Error,
    setInterval(fn) { timers.push(fn); return fn; },
    clearInterval(fn) { timers.splice(timers.indexOf(fn), 1); },
  })(name => { if (!modules[name]) throw Error('Unexpected import ' + name); return modules[name]; }, loaded, loaded.exports);
  let state, root;
  function Probe() { state = loaded.exports.useManagement(live); return null; }
  await act(async () => { root = create(React.createElement(Probe)); });
  return {
    get state() { return state; }, calls, app,
    do: fn => act(async () => { void fn(state); }),
    reply: (index, overrides = {}) => act(async () => {
      calls[index].resolve({ data: { days: calls[index].days, order_count: 12, updated_at: 'now', ...overrides } });
    }),
    fail: index => act(async () => { calls[index].reject(new ApiError('Mạng tạm gián đoạn')); }),
    poll: () => act(async () => { timers.forEach(fn => fn()); }),
    close: () => act(async () => { root.unmount(); }),
  };
}

test('period changes, cached snapshots and programmatic sync never start native pull-to-refresh', async () => {
  const h = await mount();
  try {
    assert.equal(h.state.refreshing, false);
    await h.reply(0);
    await h.do(s => s.onDays(7));
    assert.equal(h.state.loading, true); assert.equal(h.state.refreshing, false);
    assert.equal(h.state.days, 7); assert.equal(h.state.data.days, 1);
    await h.reply(1);
    await h.do(s => s.onDays(1));
    assert.equal(h.calls.length, 2); assert.equal(h.state.loading, false);
    await h.do(s => s.refresh());
    assert.equal(h.state.loading, true); assert.equal(h.state.refreshing, false);
    await h.reply(2);
    await h.do(s => s.pullRefresh());
    assert.equal(h.state.refreshing, true);
    await h.fail(3);
    assert.equal(h.state.refreshing, false); assert.equal(h.state.loading, false);
    assert.equal(h.state.data.order_count, 12);
    assert.equal(h.state.error, 'Mạng tạm gián đoạn');
  } finally { await h.close(); }
});

test('rapid switching cancels pull and ignores late or mismatched responses', async () => {
  const h = await mount();
  try {
    await h.reply(0);
    await h.do(s => s.pullRefresh());
    await h.do(s => s.onDays(7));
    assert.equal(h.calls[1].signal.aborted, true); assert.equal(h.state.refreshing, false);
    await h.do(s => s.onDays(30));
    await h.reply(3, { order_count: 300 });
    await h.reply(2, { order_count: 70 }); await h.reply(1, { order_count: 1 });
    assert.equal(h.state.days, 30); assert.equal(h.state.data.order_count, 300);
    await h.do(s => s.onDays(7));
    await h.reply(4, { days: 30 });
    assert.equal(h.state.days, 7); assert.match(h.state.error, /không khớp/);
    assert.equal(h.state.data.days, 30); assert.equal(h.state.loading, false);
    await h.do(s => s.refresh()); await h.reply(5, { order_count: 70 });
    assert.equal(h.state.data.days, 7); assert.equal(h.state.error, '');
  } finally { await h.close(); }
});

test('background reads preserve unchanged render, recover errors and release requests on unmount', async () => {
  const h = await mount(true);
  await h.reply(0);
  const before = h.state;
  await h.poll(); await h.reply(1, { updated_at: 'later' });
  assert.equal(h.state.data, before.data, 'Unchanged polling must preserve the displayed snapshot');
  h.app.currentState = 'background'; await h.poll(); assert.equal(h.calls.length, 2);
  h.app.currentState = 'active'; await h.poll(); await h.fail(2);
  assert.equal(h.state.data.order_count, 12); assert.equal(h.state.refreshing, false);
  await h.poll(); await h.reply(3, { order_count: 13 });
  assert.equal(h.state.data.order_count, 13); assert.equal(h.state.error, '');
  await h.poll(); await h.close(); assert.equal(h.calls[4].signal.aborted, true);
});
