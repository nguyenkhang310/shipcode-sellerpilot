const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs'), os = require('node:os'), path = require('node:path');
const {checkFrontend} = require('../demo.cjs');

function fixture(run) {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'sellerpilot-sdk-')));
  const write = (name, data) => {const file = path.join(root, name); fs.mkdirSync(path.dirname(file), {recursive: true}); fs.writeFileSync(file, JSON.stringify(data));};
  const dependencies = {expo: '~58.0.26', react: '19.3.0'};
  write('frontend/package.json', {dependencies});
  write('frontend/app.json', {expo: {}});
  write('package-lock.json', {packages: {frontend: {dependencies}, 'node_modules/expo': {version: '58.0.26'}, 'node_modules/react': {version: '19.3.0'}}});
  write('node_modules/expo/package.json', {version: '58.0.26'});
  write('node_modules/react/package.json', {version: '19.3.0'});
  try {run(root, write);} finally {fs.rmSync(root, {recursive: true, force: true});}
}

test('startup resolves the installed SDK and accepts matching locked dependencies', () => fixture(root => {
  const result = checkFrontend(root);
  assert.equal(result.version, '58.0.26'); assert.equal(result.cli, path.join(root, 'node_modules/expo/bin/cli'));
}));
test('stale SDK 57 installation is rejected with an npm ci instruction before starting Metro', () => fixture((root, write) => {
  write('node_modules/expo/package.json', {version: '57.0.0'});
  assert.throws(() => checkFrontend(root), /expo.*57\.0\.0.*npm ci/);
}));
test('incomplete dependencies and a mixed manifest/lockfile cannot start', () => fixture((root, write) => {
  fs.rmSync(path.join(root, 'node_modules/react'), {recursive: true});
  assert.throws(() => checkFrontend(root), /Thiếu thư viện react.*npm ci/);
  write('frontend/package.json', {dependencies: {expo: '~57.0.0'}});
  assert.throws(() => checkFrontend(root), /package-lock.json không cùng bản/);
}));
test('an app.json SDK override cannot disagree with the installed SDK', () => fixture((root, write) => {
  write('frontend/app.json', {expo: {sdkVersion: '57.0.0'}});
  assert.throws(() => checkFrontend(root), /sdkVersion/);
}));
