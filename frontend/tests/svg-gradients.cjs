// Run the installed native gradient extractor: web accepts ".55", native does not.
const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');

test('dock and chart gradient values survive the native SVG parser without warnings', () => {
  const warnings = [];
  const filename = path.join(path.dirname(require.resolve('react-native-svg/package.json')), 'src/lib/extract/extractGradient.ts');
  const compiled = ts.transpileModule(fs.readFileSync(filename, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, esModuleInterop: true },
  }).outputText;
  const nativeModule = { exports: {} };
  vm.runInNewContext(compiled, {
    module: nativeModule, exports: nativeModule.exports,
    console: { warn: message => warnings.push(message) },
    // Only platform color/transform helpers are stubbed. Offset parsing is real.
    require(name) {
      if (name === 'react') return React;
      if (name === 'react-native') return { processColor: () => 0xffffffff };
      if (name === './extractOpacity') return value => value === undefined ? 1 : Number(value);
      if (name === './extractTransform') return () => null;
      if (name === '../units') return { objectBoundingBox: 0 };
      throw Error('Unexpected dependency: ' + name);
    },
  }, { filename });
  const extract = nativeModule.exports.default;
  const nativeOffsets = offsets => Array.from(extract({ id: 'qa', children: offsets.map(offset => React.createElement('stop', { offset, stopColor: '#FFF' })) }, null).gradient).filter((_, i) => i % 2 === 0);
  // Prove that this regression would catch the original input, unlike a web test.
  assert.deepEqual(nativeOffsets(['.55']), [0]);
  assert.equal(warnings.length, 1);
  warnings.length = 0;

  const offsets = [];
  for (const file of ['components/layout/BottomNav.tsx', 'features/dashboard/ManagementCharts.tsx']) {
    const source = ts.createSourceFile(file, fs.readFileSync(path.join(__dirname, '../src', file), 'utf8'), ts.ScriptTarget.Latest, true, ts.ScriptKind.TSX);
    function visit(node) {
      if ((ts.isJsxSelfClosingElement(node) || ts.isJsxOpeningElement(node)) && ['Stop', 'LinearGradient'].includes(node.tagName.getText(source))) {
        for (const attr of node.attributes.properties) {
          if (!ts.isJsxAttribute(attr) || !['offset', 'x1', 'x2', 'y1', 'y2', 'stopOpacity'].includes(attr.name.getText(source))) continue;
          const init = attr.initializer;
          if (init && ts.isStringLiteral(init)) {
            assert.match(init.text, /^[+-]?\d+(?:\.\d+)?%?$/, file + ': invalid SVG string');
          }
          if (attr.name.getText(source) === 'offset') {
            assert(init && ts.isJsxExpression(init) && init.expression && ts.isNumericLiteral(init.expression), 'Use numeric offsets for consistent native/web behavior');
            offsets.push(Number(init.expression.text));
          }
        }
      }
      ts.forEachChild(node, visit);
    }
    visit(source);
  }
  assert.equal(offsets.length, 5);
  assert(offsets.includes(0.55));
  assert.deepEqual(nativeOffsets(offsets), [...offsets].sort((a, b) => a - b));
  assert.deepEqual(warnings, []);
});
