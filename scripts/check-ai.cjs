#!/usr/bin/env node
// Use the same Python and working directory as the API; no global Python needed.
const {spawn} = require('node:child_process');
const {existsSync} = require('node:fs');
const path = require('node:path');
const backend = path.resolve(__dirname, '../backend');
const python = path.join(backend, '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python');
if (!existsSync(python)) {
  console.error('Chưa có backend/.venv. Cài môi trường theo README trước.');
  process.exitCode = 1;
} else {
  const args = process.argv.includes('--benchmark') ? ['-u', 'tests/benchmark_ai.py'] : ['-u', '-m', 'app.scripts.check_ai'];
  const child = spawn(python, args, {cwd: backend, stdio: 'inherit'});
  child.on('error', error => { console.error(error.message); process.exitCode = 1; });
  child.on('exit', (code, signal) => { process.exitCode = signal ? 1 : code ?? 1; });
}
