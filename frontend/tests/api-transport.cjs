const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function loadApi(request) {
  class ApiError extends Error {
    constructor(status, message, code) { super(message); this.status = status; this.code = code; }
  }
  const modules = {'./client': {apiRequest: request, ApiError, API_URL: 'http://test/api/v1'},
    'react-native': {Platform: {OS: 'ios'}}};
  function load(name) {
    if (modules[name]) return modules[name];
    const filename = path.resolve(__dirname, '../src/api/' + name.replace('./', '') + '.ts');
    const output = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
      compilerOptions: {module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022},
    }).outputText;
    const module = {exports: {}};
    vm.runInNewContext('(function(require,module,exports){' + output + '\n})', {URL, Math})(load, module, module.exports);
    modules[name] = module.exports;
    return module.exports;
  }
  return {load, ApiError};
}

test('explicit API address wins over Metro; LAN, IPv6 and tunnel fallbacks are predictable', () => {
  const {resolveApiUrls} = loadApi().load('./urls');
  const base = {nativeDevelopment: true, android: false, metroHost: '192.168.1.5:8081'};
  const explicit = resolveApiUrls({...base, configuredApi: ' https://api.example.test/api/v1/ ', configuredStore: 'https://shop.example.test/'});
  assert.equal(explicit.api, 'https://api.example.test/api/v1');
  assert.equal(explicit.origin, 'https://api.example.test');
  assert.equal(explicit.store, 'https://shop.example.test');
  assert.equal(resolveApiUrls(base).api, 'http://192.168.1.5:8000/api/v1');
  assert.equal(resolveApiUrls({...base, metroHost: '[::1]:8081'}).api, 'http://[::1]:8000/api/v1');
  assert.equal(resolveApiUrls({...base, metroHost: 'abcd.exp.direct:8081'}).api, 'http://127.0.0.1:8000/api/v1');
  assert.equal(resolveApiUrls({...base, nativeDevelopment: false, android: true}).api, 'http://10.0.2.2:8000/api/v1');
});

test('retry after lost response retrieves saved answer without another POST', async () => {
  const calls = [], answer = {data: {run_id: 7, answer: 'Còn 3 sản phẩm'}};
  const {load} = loadApi(async (url, options) => {
    calls.push([url, options]);
    if (url === '/chat') throw new TypeError('Network request failed');
    return {data: {status: 'completed', response: answer}};
  });
  const {sendSellerMessage} = load('./sellerPilot');
  await assert.rejects(sendSellerMessage('Tồn kho?', undefined, 'conversation', 'stable-id'));
  const recovered = await sendSellerMessage('Tồn kho?', undefined, 'conversation', 'stable-id', true);
  assert.deepEqual(recovered, answer);
  assert.equal(calls.filter(([url]) => url === '/chat').length, 1);
  assert.equal(JSON.parse(calls[0][1].body).request_id, 'stable-id');
});

test('running request is joined with identical identity and conversation', async () => {
  const calls = [];
  const {load} = loadApi(async (url, options) => {
    calls.push([url, options]);
    return url === '/chat' ? {data: {run_id: 1}} : {data: {status: 'running', response: null}};
  });
  await load('./sellerPilot').sendSellerMessage('Chào', undefined, 'conversation', 'stable-id', true);
  assert.equal(calls[0][0], '/chat/requests/stable-id');
  assert.equal(calls[1][0], '/chat');
  assert.equal(JSON.parse(calls[1][1].body).request_id, 'stable-id');
});

test('cancelled or interrupted jobs are never automatically POSTed again', async () => {
  for (const state of [{status: 'cancelled'}, {status: 'failed', error: {
    status: 409, detail: {code: 'chat_interrupted', message: 'Kiểm tra lịch sử trước.'}}}]) {
    const calls = [];
    const {load} = loadApi(async url => {calls.push(url); return {data: state};});
    await assert.rejects(load('./sellerPilot').sendSellerMessage('Chào', undefined, 'c', 'id', true));
    assert.deepEqual(calls, ['/chat/requests/id']);
  }
});

test('cancel uses an independent request and gallery uploads carry a stable ID', async () => {
  const calls = [];
  const {load} = loadApi(async (url, options) => {calls.push([url, options]); return {data: {}};});
  await load('./chatRequests').cancelChatRequest('cancel-id');
  assert.equal(calls[0][0], '/chat/requests/cancel-id/cancel');
  assert.equal(calls[0][1].signal, undefined);
  await load('./sellerPilot').uploadProductImages([{uri:'local', base64:'abcd'}], 'conversation', undefined, 'upload-id');
  assert.equal(JSON.parse(calls[1][1].body).request_id, 'upload-id');
});
