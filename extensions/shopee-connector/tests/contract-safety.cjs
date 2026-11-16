const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

// Ensure global.chrome is mocked if running standalone
let saved = {};
if (typeof global.chrome === 'undefined') {
  global.chrome = {
    storage: {
      local: {
        get: async key => structuredClone(key === null ? saved : {[key]: saved[key]}),
        set: async value => { Object.assign(saved, structuredClone(value)); },
        remove: async key => { delete saved[key]; }
      }
    },
    tabs: {
      get: async id => ({id, active: true, url: 'https://banhang.shopee.vn/'}),
      query: async () => [{id: 7, active: true, url: 'https://banhang.shopee.vn/'}],
      sendMessage: async () => ({ok: true, data: {}})
    },
    scripting: {executeScript: async () => {}},
    runtime: {getURL: value => 'chrome-extension://fixture/' + value}
  };
}

test('PII Allowlist strictly rejects sensitive customer data headers', async () => {
  const {COLUMN, inventoryRows} = await import('../shop-data.js');

  // Verify column regex definitions
  assert.equal(COLUMN.name.test('Sản phẩm'), true);
  assert.equal(COLUMN.name.test('Tên sản phẩm'), true);
  assert.equal(COLUMN.name.test('Product Name'), true);

  // Negative test cases: Noisy customer PII headers must NOT match any COLUMN regex
  const sensitiveHeaders = [
    'Tên người nhận',
    'Tên khách hàng',
    'Người mua',
    'Customer Name',
    'Buyer',
    'Số điện thoại',
    'SĐT',
    'Phone Number',
    'Địa chỉ',
    'Địa chỉ giao hàng',
    'Shipping Address',
    'Email',
    'Ghi chú người mua',
    'Customer Note'
  ];

  for (const header of sensitiveHeaders) {
    for (const [key, regex] of Object.entries(COLUMN)) {
      assert.equal(
        regex.test(header),
        false,
        `Header nhạy cảm "${header}" không được khớp với cột "${key}"`
      );
    }
  }

  // Test with a mock table containing both product data and customer PII
  const mockTable = [
    ['Sản phẩm', 'SKU', 'Tồn kho', 'Tên người nhận', 'Số điện thoại', 'Địa chỉ giao hàng'],
    ['Áo thun cotton', 'AT-01', '100', 'Nguyễn Văn A', '0901234567', '123 Đường Lê Lợi, Q1, TP.HCM'],
    ['Quần jeans', 'QJ-02', '50', 'Trần Thị B', '0912345678', '456 Đường CMT8, Q3, TP.HCM']
  ];

  const rows = inventoryRows({tables: [mockTable]});
  assert.equal(rows.length, 2);
  for (const row of rows) {
    assert.equal(typeof row.name, 'string');
    assert.equal(typeof row.sku, 'string');
    assert.equal(typeof row.stock, 'number');
    // Ensure no PII values leaked into the extracted row object
    const serialized = JSON.stringify(row);
    assert.equal(serialized.includes('Nguyễn Văn A'), false);
    assert.equal(serialized.includes('0901234567'), false);
    assert.equal(serialized.includes('Lê Lợi'), false);
    assert.equal(serialized.includes('Trần Thị B'), false);
    assert.equal(serialized.includes('0912345678'), false);
    assert.equal(serialized.includes('CMT8'), false);
  }
});

test('shopee-schema.json has valid structure, feature flags and fallback precedence', async () => {
  const schemaPath = path.resolve(__dirname, '../shopee-schema.json');
  assert.equal(fs.existsSync(schemaPath), true);

  const raw = fs.readFileSync(schemaPath, 'utf8');
  const schema = JSON.parse(raw);

  assert.equal(schema.version, '1.0.0');
  assert.equal(typeof schema.featureFlags, 'object');
  assert.equal(typeof schema.featureFlags.useInternalApi, 'boolean');
  assert.equal(typeof schema.featureFlags.autoNavigate, 'boolean');
  assert.equal(schema.featureFlags.enableUnlist, false, 'enableUnlist must default to false before live verification');

  assert.equal(typeof schema.selectors, 'object');
  for (const field of ['product_name', 'price', 'stock', 'description']) {
    assert(Array.isArray(schema.selectors[field].primary), `primary selectors for ${field} must be an array`);
    assert(Array.isArray(schema.selectors[field].fallback), `fallback selectors for ${field} must be an array`);
    assert(schema.selectors[field].primary.length > 0, `primary selectors for ${field} cannot be empty`);
  }
  assert(schema.selectors.variation_table, 'variation_table selector must be defined');

  // Test schema loader override mechanism
  const {loadSchema, validateSchema, getSelectorGroup} = await import('../schema-loader.js');
  assert.equal(validateSchema(schema), true);
  assert.equal(validateSchema({}), false);
  assert.equal(validateSchema(null), false);

  const nameGroup = await getSelectorGroup('product_name');
  assert(nameGroup.primary.length > 0);
  assert(nameGroup.fallback.length > 0);
});

test('Safety gate: handleApi rejects any destructive delete tool or untrusted publication claims', async () => {
  const api = await import('../api.js');
  // Confirm handleApi does not allow arbitrary destructive DELETE commands on shopee
  const invalidPaths = [
    '/products/1/delete',
    '/products/delete',
    '/product-drafts/1/destroy',
    '/shopee/delete-product'
  ];

  for (const p of invalidPaths) {
    await assert.rejects(
      api.handleApi(p, 'DELETE', '{}'),
      /không được phép|không tìm thấy|không hợp lệ|chưa được nối và kiểm chứng/i
    );
  }
});
