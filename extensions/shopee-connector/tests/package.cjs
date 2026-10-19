const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const {prepareExpoAssets, validatePackagePaths} = require('../../../scripts/extension-package.cjs');

function fixture(t) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), 'sellerpilot-extension-package-'));
  t.after(() => fs.rmSync(directory, {recursive: true, force: true}));
  const write = (file, content) => {const target = path.join(directory, file); fs.mkdirSync(path.dirname(target), {recursive: true}); fs.writeFileSync(target, content);};
  write('_expo/static/js/web/index.js', 'globalThis.font="/assets/_node_modules/icons/Ionicons.ttf"; globalThis.image="/assets/logo.png"; globalThis.marker="__expo_module_name__";');
  write('assets/_node_modules/icons/Ionicons.ttf', Buffer.from([0, 1, 2, 255]));
  write('assets/logo.png', Buffer.from([137, 80, 78, 71]));
  write('index.html', '<script src="/_expo/static/js/web/index.js"></script>');
  write('bundles.js', 'globalThis.SELLERPILOT_BUNDLES=["/_expo/static/js/web/index.js"];\n');
  return {directory, write};
}

test('Expo bundle and icon fonts load from Chrome-safe paths after packaging', t => {
  const {directory} = fixture(t);
  const oldFont = fs.readFileSync(path.join(directory, 'assets/_node_modules/icons/Ionicons.ttf'));
  prepareExpoAssets(directory);
  assert.equal(fs.existsSync(path.join(directory, '_expo')), false);
  assert.equal(fs.existsSync(path.join(directory, 'assets/_node_modules')), false);
  assert.match(fs.readFileSync(path.join(directory, 'index.html'), 'utf8'), /src="\/expo\/static/);
  const bundle = fs.readFileSync(path.join(directory, 'expo/static/js/web/index.js'), 'utf8');
  assert(bundle.includes('/assets/vendor/icons/Ionicons.ttf'));
  assert(bundle.includes('__expo_module_name__'), 'Expo runtime identifiers must remain unchanged');
  assert.deepEqual(fs.readFileSync(path.join(directory, 'assets/vendor/icons/Ionicons.ttf')), oldFont);
  assert.deepEqual(validatePackagePaths(directory), {bundles: 1, assets: 2});
  prepareExpoAssets(directory); // Repackaging must not corrupt paths or binary assets.
  assert.deepEqual(validatePackagePaths(directory), {bundles: 1, assets: 2});
});

test('packaging rejects reserved filenames and missing bundle/font references', t => {
  const {directory, write} = fixture(t);
  assert.throws(() => validatePackagePaths(directory), /dành riêng/);
  prepareExpoAssets(directory);
  fs.unlinkSync(path.join(directory, 'assets/vendor/icons/Ionicons.ttf'));
  assert.throws(() => validatePackagePaths(directory), /Không tìm thấy tài nguyên/);
  write('assets/vendor/icons/Ionicons.ttf', 'fixture');
  fs.unlinkSync(path.join(directory, 'expo/static/js/web/index.js'));
  assert.throws(() => validatePackagePaths(directory), /Không tìm thấy tài nguyên/);
});
