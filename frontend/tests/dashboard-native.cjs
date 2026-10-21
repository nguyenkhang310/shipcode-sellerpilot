// Component regression tests use fake native views; no API or Keychain access.
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const qa=name=>require(process.env.QA_NODE_MODULES?path.join(process.env.QA_NODE_MODULES,name):name);
const React=qa('react'),{create,act}=qa('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
const compile=(file,modules)=>{
 const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const loaded={exports:{}};
 vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{})(name=>{
  if(name==='react')return React;if(name==='react/jsx-runtime')return qa('react/jsx-runtime');
  if(!(name in modules))throw Error('Unexpected import '+name);return modules[name];
 },loaded,loaded.exports);return loaded.exports;
};
const flatten=value=>Array.isArray(value)?Object.assign({},...value.map(flatten)):value;

test('order value stays readable through zero-size first layout, resize and data changes without native auto-fit',async()=>{
 const viewport={width:390,fontScale:1};
 const {OrderValue}=compile('features/dashboard/OrderValue.tsx',{'react-native':{View:'View',Text:'Text',StyleSheet:{create:v=>v},useWindowDimensions:()=>viewport}});
 let root;const render=value=>React.createElement(OrderValue,{value,colour:'#1C1C1E',muted:'#626D7C'});
 await act(async()=>{root=create(render('12.345.678'));});
 try{
  const amount=()=>root.root.findByProps({testID:'dashboard-order-value'});
  const layout=width=>act(async()=>root.root.findByType('View').props.onLayout({nativeEvent:{layout:{width}}}));
  const initial=flatten(amount().props.style).fontSize;
  assert(initial>=30);assert(!amount().props.adjustsFontSizeToFit);
  await layout(0);assert.equal(flatten(amount().props.style).fontSize,initial);
  for(const width of [280,350,390,480]){
   await layout(width);
   for(const value of ['—','0','1.234.567','9.007.199.254.740.991']){
    await act(async()=>root.update(render(value)));
    assert(flatten(amount().props.style).fontSize>=20);assert.equal(flatten(amount().props.style).lineHeight,64);
    assert.equal(amount().props.accessibilityLabel,value+' đồng');assert.equal(amount().props.children[0],value);
   }
  }
  viewport.fontScale=2;
  await act(async()=>root.update(render('9.007.199.254.740.991')));
  assert(flatten(amount().props.style).fontSize*amount().props.maxFontSizeMultiplier>=20);
 }finally{await act(async()=>root.unmount());}
});

test('native glass and blur keep a contrast layer above the effect in both themes',()=>{
 const recipe=compile('components/layout/dockAppearance.ts',{});
 for(const os of ['ios','android'])for(const available of [true,false])for(const dark of [false,true]){
  const {DockMaterial}=compile('components/layout/DockMaterial.tsx',{
   'react-native':{Platform:{OS:os},View:'View',StyleSheet:{absoluteFill:{position:'absolute'}}},
   'expo-blur':{BlurView:'BlurView'},'expo-glass-effect':{GlassView:'GlassView',isGlassEffectAPIAvailable:()=>available,isLiquidGlassAvailable:()=>true},
   './dockAppearance':recipe,
  });
  const result=DockMaterial({dark,opaque:false}),[effect,overlay]=result.props.children;
  assert.equal(effect.type,os==='ios'&&available?'GlassView':'BlurView');
  assert.equal(overlay.props.testID,'dock-material');
  const colour=flatten(overlay.props.style).backgroundColor;
  assert.equal(colour,recipe.dockAppearance(dark).frost);
  assert(parseInt(colour.slice(-2),16)/255>=.85);
  if(effect.type==='GlassView')assert.equal(effect.props.colorScheme,dark?'dark':'light');
 }
});

test('Reduce Transparency uses a solid surface without constructing glass or blur',()=>{
 const recipe=compile('components/layout/dockAppearance.ts',{});
 const {DockMaterial}=compile('components/layout/DockMaterial.tsx',{
  'react-native':{Platform:{OS:'ios'},View:'View',StyleSheet:{absoluteFill:{position:'absolute'}}},'expo-blur':{BlurView:'BlurView'},
  'expo-glass-effect':{GlassView:'GlassView',isGlassEffectAPIAvailable:()=>{throw Error('Must skip native effect');}},'./dockAppearance':recipe,
 });
 for(const dark of [true,false]){
  const result=DockMaterial({dark,opaque:true});assert.equal(result.type,'View');
  assert.equal(flatten(result.props.style).backgroundColor,recipe.dockAppearance(dark).solid);
 }
});
