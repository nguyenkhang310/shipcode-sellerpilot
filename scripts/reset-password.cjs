#!/usr/bin/env node
const { spawnSync } = require('node:child_process');
const { existsSync } = require('node:fs');
const path = require('node:path');
const backend = path.resolve(__dirname, '../backend');
const python = path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python)) {
  console.error('Chưa cài môi trường backend. Làm theo README trước khi đặt lại mật khẩu.');
  process.exitCode = 1;
} else {
  const result = spawnSync(python, ['-m', 'app.scripts.reset_password'], { cwd: backend, stdio: 'inherit', env: process.env });
  if (result.error) console.error('Chưa chạy được lệnh đặt lại mật khẩu:', result.error.message);
  process.exitCode = result.status ?? 1;
}
