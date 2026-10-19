#!/usr/bin/env node
// No installs or process kills. The build reuses the Expo app instead of copying its UI.
const fs = require('node:fs');
const path = require('node:path');
const {randomBytes} = require('node:crypto');
const {spawnSync} = require('node:child_process');
const {prepareExpoAssets, validatePackagePaths} = require('./extension-package.cjs');
const root = path.resolve(__dirname, '..');
const source = path.join(root, 'extensions/shopee-connector');
const configFile = path.join(source, 'connection.local.json');
const command = process.argv[2];
if (command === 'setup') {
  const envFile = path.join(root, '.env');
  const env = fs.existsSync(envFile) ? fs.readFileSync(envFile, 'utf8') : '';
  const existing = env.match(/^BROWSER_CONNECTOR_TOKEN=([a-f0-9]{64})$/m)?.[1];
  const token = existing || randomBytes(32).toString('hex');
  const next = env.replace(/^BROWSER_CONNECTOR_TOKEN=.*\r?\n?/gm, '');
  fs.writeFileSync(envFile, next + (next.endsWith('\n') || !next ? '' : '\n') + 'BROWSER_CONNECTOR_TOKEN=' + token + '\n', {mode: 0o600});
  fs.writeFileSync(configFile, JSON.stringify({token}, null, 2) + '\n', {mode: 0o600});
  console.log('Đã tạo khóa ghép nối local; không in khóa ra terminal. Khởi động lại backend sau khi setup lần đầu.');
} else if (command === 'build') {
  if (!fs.existsSync(configFile)) throw Error('Chạy npm run extension:setup trước.');
  const built = spawnSync(process.platform === 'win32' ? 'npm.cmd' : 'npm', ['run', 'build', '--workspace', 'frontend'], {
    cwd: root, stdio: 'inherit', env: {...process.env, EXPO_PUBLIC_API_URL: 'http://127.0.0.1:8000/api/v1', EXPO_PUBLIC_STORE_URL: 'http://127.0.0.1:5011'},
  });
  if (built.status !== 0) process.exit(built.status || 1);
  const output = path.join(source, 'dist');
  fs.rmSync(output, {recursive: true, force: true});
  fs.cpSync(path.join(root, 'frontend/dist/web'), output, {recursive: true});
  prepareExpoAssets(output);
  for (const name of ['manifest.json', 'service-worker.js', 'state.js', 'api.js', 'bootstrap.js', 'content', 'connection.local.json']) fs.cpSync(path.join(source, name), path.join(output, name), {recursive: true});
  fs.copyFileSync(path.join(root, 'frontend/assets/shipcode-logo-app.png'), path.join(output, 'icon.png'));
  const indexFile = path.join(output, 'index.html');
  let index = fs.readFileSync(indexFile, 'utf8').replace('<html lang="en">', '<html lang="vi">');
  const scripts = [];
  index = index.replace(/<script\b[^>]*\bsrc="([^"]+)"[^>]*>\s*<\/script>/gi, (_tag, src) => {scripts.push(src); return '';});
  if (!scripts.length || /<script\b/i.test(index)) throw Error('Expo HTML thay đổi: cần kiểm tra script trước khi đóng gói CSP.');
  if (scripts.some(src => !src.startsWith('/') || src.startsWith('//'))) throw Error('Bundle phải là tài nguyên local.');
  fs.writeFileSync(path.join(output, 'bundles.js'), 'globalThis.SELLERPILOT_BUNDLES=' + JSON.stringify(scripts) + ';\n');
  index = index.replace('</body>', '<script src="/bundles.js"></script><script src="/bootstrap.js"></script></body>');
  fs.writeFileSync(indexFile, index);
  const checked = validatePackagePaths(output);
  console.log(`Đã kiểm tra ${checked.bundles} bundle và ${checked.assets} đường dẫn ảnh/font trong gói.`);
  console.log('\nLoad unpacked: ' + output + '\nGói build có khóa ghép nối local; không upload hoặc chia sẻ thư mục dist. Mỗi thành viên tự chạy setup.');
} else {
  console.error('Dùng npm run extension:setup hoặc npm run extension:build.'); process.exitCode = 1;
}
