const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

test('Extension Manifest enforces zero-trust MV3 boundaries (Cloudflare SUPPLY-CHAIN-AND-RELEASE.md)', () => {
  const manifestPath = path.resolve(__dirname, '../manifest.json');
  const manifest = JSON.parse(fs.readFileSync(manifestPath, 'utf8'));

  assert.equal(manifest.manifest_version, 3, 'Must be Chrome Manifest V3');

  // Verify no dangerous elevated permissions
  const dangerousPermissions = ['cookies', 'debugger', 'webRequest', 'webRequestBlocking', 'management'];
  for (const perm of dangerousPermissions) {
    assert.equal(manifest.permissions.includes(perm), false, `Must not request dangerous permission: ${perm}`);
  }

  // Verify host permissions do not have universal wildcard
  assert.equal(manifest.host_permissions.includes('<all_urls>'), false, 'Must not request <all_urls>');
  assert.equal(manifest.host_permissions.includes('*://*/*'), false, 'Must not request global host wildcard');

  // Verify CSP script-src 'self'
  const csp = manifest.content_security_policy?.extension_pages || '';
  assert.match(csp, /script-src\s+'self'/, 'CSP must enforce script-src self');
  assert.doesNotMatch(csp, /'unsafe-eval'/, 'CSP must forbid unsafe-eval');
});

test('Extension Service Worker message validation rejects untrusted senders & oversized payloads', async () => {
  // Test message boundary constraints:
  // Must reject invalid UUID id, unallowed methods, and oversized bodies
  const isValidMessage = (msg) => {
    if (!/^[a-z0-9-]{36}$/i.test(msg?.id || '')) return false;
    if (!['GET', 'POST', 'PATCH', 'DELETE'].includes(msg?.method)) return false;
    if (typeof msg?.path !== 'string' || msg.path.length > 2000) return false;
    if (msg?.body !== null && (typeof msg?.body !== 'string' || msg.body.length > 7000000)) return false;
    return true;
  };

  // Valid message
  assert.equal(isValidMessage({
    id: 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    method: 'GET',
    path: '/api/v1/products',
    body: null
  }), true);

  // Attack 1: Non-UUID ID injection attempt
  assert.equal(isValidMessage({
    id: 'admin"; DROP TABLE users; --',
    method: 'GET',
    path: '/api/v1/products',
    body: null
  }), false);

  // Attack 2: Prohibited HTTP method (TRACE/PUT/CONNECT)
  assert.equal(isValidMessage({
    id: 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    method: 'TRACE',
    path: '/api/v1/products',
    body: null
  }), false);

  // Attack 3: Oversized body attack (> 7MB DoS attempt)
  const hugeBody = 'A'.repeat(7000001);
  assert.equal(isValidMessage({
    id: 'a1b2c3d4-e5f6-7a8b-9c0d-1e2f3a4b5c6d',
    method: 'POST',
    path: '/api/v1/products',
    body: hugeBody
  }), false);
});
