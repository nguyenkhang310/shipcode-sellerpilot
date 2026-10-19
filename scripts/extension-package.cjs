const fs = require('node:fs');
const path = require('node:path');

const RELOCATIONS = [['_expo', 'expo'], ['assets/_node_modules', 'assets/vendor']];

function files(directory) {
  return fs.readdirSync(directory, {withFileTypes: true}).flatMap(entry => {
    const filename = path.join(directory, entry.name);
    if (entry.isSymbolicLink()) throw Error('Extension không được chứa symlink: ' + filename);
    return entry.isDirectory() ? files(filename) : [filename];
  });
}

function prepareExpoAssets(directory) {
  // Chrome reserves underscore-prefixed names. Relocate only the copied export;
  // the ordinary Expo web build keeps its original paths.
  for (const [from, to] of RELOCATIONS) {
    const oldPath = path.join(directory, from), newPath = path.join(directory, to);
    if (!fs.existsSync(oldPath)) continue;
    if (fs.existsSync(newPath)) throw Error('Đường dẫn đóng gói bị trùng: ' + to);
    fs.renameSync(oldPath, newPath);
  }
  for (const filename of files(directory)) {
    if (!/\.(?:html|js|css|json|map)$/.test(filename)) continue;
    const original = fs.readFileSync(filename, 'utf8');
    let rewritten = original;
    for (const [from, to] of RELOCATIONS) rewritten = rewritten.replaceAll(from + '/', to + '/');
    if (rewritten !== original) fs.writeFileSync(filename, rewritten);
  }
}

function validatePackagePaths(directory) {
  function checkNames(current) {
    for (const entry of fs.readdirSync(current, {withFileTypes: true})) {
      if (entry.name.startsWith('_')) throw Error('Tên file/thư mục dành riêng của Chrome: ' + path.relative(directory, path.join(current, entry.name)));
      if (entry.isDirectory()) checkNames(path.join(current, entry.name));
    }
  }
  checkNames(directory);
  const listFile = fs.readFileSync(path.join(directory, 'bundles.js'), 'utf8');
  const scripts = JSON.parse(listFile.trim().replace(/^globalThis\.SELLERPILOT_BUNDLES=/, '').replace(/;$/, ''));
  if (!Array.isArray(scripts) || !scripts.length) throw Error('Gói extension thiếu bundle.');
  function resource(url) {
    if (typeof url !== 'string' || !url.startsWith('/') || url.startsWith('//')) throw Error('Tài nguyên phải nằm trong extension.');
    const filename = path.resolve(directory, '.' + url);
    if (!filename.startsWith(path.resolve(directory) + path.sep) || !fs.statSync(filename, {throwIfNoEntry: false})?.isFile()) throw Error('Không tìm thấy tài nguyên: ' + url);
    return filename;
  }
  let assetCount = 0;
  for (const script of scripts) {
    const contents = fs.readFileSync(resource(script), 'utf8');
    for (const match of contents.matchAll(/["'](\/assets\/[^"'\s]+)["']/g)) {
      resource(match[1]); assetCount++;
    }
  }
  return {bundles: scripts.length, assets: assetCount};
}

module.exports = {prepareExpoAssets, validatePackagePaths};
