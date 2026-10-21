#!/usr/bin/env node
// One terminal owns the three demo services. No installs, DB seeding or forced port kills.
const {spawn} = require('node:child_process');
const {existsSync} = require('node:fs');
const path = require('node:path');
const net = require('node:net');
const os = require('node:os');

const root = path.resolve(__dirname, '..');
const windows = process.platform === 'win32';
const python = folder => path.join(root, folder, '.venv', windows ? 'Scripts/python.exe' : 'bin/python');
const children = new Set();
let stopping = false;

function lanAddress() {
  const interfaces = Object.entries(os.networkInterfaces());
  const priority = name => /^(en0|eth0|Wi-Fi)$/.test(name) ? 0 : 1;
  interfaces.sort(([first], [second]) => priority(first) - priority(second));
  for (const [name, addresses] of interfaces) {
    if (/^(utun|tun|tap|tailscale|docker|veth|bridge)/i.test(name)) continue;
    const address = addresses?.find(item => item.family === 'IPv4' && !item.internal);
    if (address) return address.address;
  }
  return '127.0.0.1';
}

function portAvailable(port) {
  return new Promise((resolve, reject) => {
    const server = net.createServer();
    server.once('error', () => reject(new Error(`Cổng ${port} đang được sử dụng. Dừng phiên cũ trước khi chạy npm run demo.`)));
    server.listen(port, '0.0.0.0', () => server.close(resolve));
  });
}

function stop(signal = 'SIGTERM') {
  if (stopping) return;
  stopping = true;
  if (!children.size) return;
  console.log('\nĐang dừng SellerPilot, Shopee Demo và Expo…');
  for (const child of children) {
    if (!child.pid) continue;
    if (windows) spawn('taskkill', ['/PID', String(child.pid), '/T', '/F'], {stdio: 'ignore'});
    else {
      try { child.detachedGroup ? process.kill(-child.pid, signal) : child.kill(signal); }
      catch (error) { if (error.code !== 'ESRCH') console.error(error.message); }
    }
  }
  const deadline = setTimeout(() => {
    for (const child of children) {
      if (!windows && child.pid && child.detachedGroup) {
        try { process.kill(-child.pid, 'SIGKILL'); } catch { /* already exited */ }
      } else child.kill('SIGKILL');
    }
  }, 10_000);
  deadline.unref();
}

function launch(label, command, args, cwd, env, interactive = false) {
  if (stopping) throw new Error('Đã dừng khởi động.');
  console.log(`\n[${label}] Đang khởi động…`);
  const child = spawn(command, args, {cwd, env, stdio: interactive ? 'inherit' : ['ignore', 'inherit', 'inherit'], detached: !windows && !interactive});
  child.detachedGroup = !windows && !interactive;
  children.add(child);
  child.on('error', error => { console.error(`[${label}] ${error.message}`); process.exitCode = 1; stop(); });
  child.on('exit', (code, signal) => {
    children.delete(child);
    if (!stopping) {
      // Expo handles Ctrl+C in raw terminal mode, so the parent may receive
      // its clean exit instead of a SIGINT. This is a normal group shutdown.
      if (label === 'Expo' && code === 0) { stop('SIGINT'); return; }
      console.error(`[${label}] Đã thoát (${signal || code}). Dừng các dịch vụ còn lại.`);
      process.exitCode = code || 1;
      stop();
    }
  });
  return child;
}

async function ready(url, timeout = 45_000) {
  const deadline = Date.now() + timeout;
  while (!stopping && Date.now() < deadline) {
    try {
      const response = await fetch(url, {signal: AbortSignal.timeout(1500)});
      if (response.ok) return;
    } catch { /* service is still starting */ }
    await new Promise(resolve => setTimeout(resolve, 350));
  }
  throw new Error(stopping ? 'Đã dừng khởi động.' : `Chưa mở được ${url}. Xem lỗi của dịch vụ ở phía trên.`);
}

async function main() {
  const [major, minor] = process.versions.node.split('.').map(Number);
  if (major < 22 || major === 22 && minor < 13) throw new Error('Cần Node.js 22.13 trở lên.');
  const expo = path.join(root, 'node_modules/expo/bin/cli');
  for (const file of [python('backend'), python('UTE MALL'), expo]) {
    if (!existsSync(file)) throw new Error(`Thiếu ${path.relative(root, file)}. Cài môi trường theo README trước.`);
  }
  if (!existsSync(path.join(root, 'UTE MALL/.env'))) throw new Error('Chưa cấu hình Shopee Demo. Chạy bootstrap_demo.py theo README trước.');
  await new Promise((resolve, reject) => {
    const check = spawn(python('backend'), ['-m', 'app.scripts.check_store'], {cwd: path.join(root, 'backend'), env: process.env, stdio: 'inherit'});
    check.on('error', reject);
    check.on('exit', code => code === 0 ? resolve() : reject(new Error('Chưa khởi động vì nguồn dữ liệu app và Kênh Người Bán không khớp.')));
  });
  // An external STORE_DATABASE_PATH is supported; the store/API startup validates it.
  for (const port of [5011, 8000, 8081]) await portAvailable(port);
  if (process.argv.includes('--check')) { console.log('Môi trường và cổng 5011/8000/8081 sẵn sàng.'); return; }
  process.on('SIGINT', () => stop('SIGINT'));
  process.on('SIGTERM', () => stop());
  const env = {...process.env, HOST: '0.0.0.0', PYTHONUNBUFFERED: '1'};
  const backend = path.join(root, 'backend');
  // Run migrations before API startup, just like backend/run_api.sh.
  await new Promise((resolve, reject) => {
    const child = spawn(python('backend'), ['-m', 'alembic', 'upgrade', 'head'], {cwd: backend, env, stdio: 'inherit'});
    children.add(child);
    child.on('error', reject);
    child.on('exit', code => { children.delete(child); code === 0 ? resolve() : reject(new Error('Migration chưa thành công.')); });
  });
  launch('Shopee Demo', python('UTE MALL'), ['app.py'], path.join(root, 'UTE MALL'), {...env, PORT: '5011', FLASK_DEBUG: '0'});
  const apiMode = process.argv.includes('--no-reload') ? ['--workers', '1']
    : ['--reload', '--reload-dir', path.join(backend, 'app')];
  launch('SellerPilot API', python('backend'), ['-m', 'uvicorn', 'app.main:app', ...apiMode, '--host', '0.0.0.0', '--port', '8000'], backend, env);
  await Promise.all([ready('http://127.0.0.1:5011/'), ready('http://127.0.0.1:8000/api/v1/health', 120_000)]);
  const address = lanAddress();
  const frontendEnv = {...env};
  // Each run uses this computer's current LAN address; shell overrides remain available.
  frontendEnv.EXPO_PUBLIC_API_URL ||= `http://${address}:8000/api/v1`;
  frontendEnv.EXPO_PUBLIC_STORE_URL ||= `http://${address}:5011`;
  launch('Expo', process.execPath, [expo, 'start', '--clear', '--port', '8081'], path.join(root, 'frontend'), frontendEnv, true);
  await ready('http://127.0.0.1:8081/status');
  console.log(`\nSẵn sàng · Shopee Demo http://localhost:5011 · API http://localhost:8000/docs`);
  console.log(`iPhone cùng Wi-Fi: exp://${address}:8081`);
  console.log('Quét QR Expo ở trên. Ctrl+C một lần để dừng cả ba dịch vụ.\n');
}

if (require.main === module) main().catch(error => { if (!stopping) { console.error('\n' + error.message); process.exitCode = 1; stop(); } });
module.exports = {lanAddress, portAvailable};
