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
   './dockAppearance':recipe,'./dockGeometry':{DOCK_RADIUS:33},
  });
  const result=DockMaterial({dark,opaque:false}),[effect,overlay]=result.props.children;
  assert.equal(effect.type,os==='ios'&&available?'GlassView':'BlurView');
  assert.equal(overlay.props.testID,'dock-material');
  const colour=flatten(overlay.props.style).backgroundColor;
  assert.equal(colour,recipe.dockAppearance(dark).frost);
  assert(parseInt(colour.slice(-2),16)/255>=.9);
  if(effect.type==='GlassView')assert.equal(effect.props.colorScheme,dark?'dark':'light');
 }
});

test('Reduce Transparency uses a solid surface without constructing glass or blur',()=>{
 const recipe=compile('components/layout/dockAppearance.ts',{});
 const {DockMaterial}=compile('components/layout/DockMaterial.tsx',{
  'react-native':{Platform:{OS:'ios'},View:'View',StyleSheet:{absoluteFill:{position:'absolute'}}},'expo-blur':{BlurView:'BlurView'},
  'expo-glass-effect':{GlassView:'GlassView',isGlassEffectAPIAvailable:()=>{throw Error('Must skip native effect');}},'./dockAppearance':recipe,'./dockGeometry':{DOCK_RADIUS:33},
 });
 for(const dark of [true,false]){
  const result=DockMaterial({dark,opaque:true});assert.equal(result.type,'View');
  assert.equal(flatten(result.props.style).backgroundColor,recipe.dockAppearance(dark).solid);
 }
});

test('compact dock uses iPhone home-indicator clearance and keeps Android navigation safe',()=>{
 for(const os of ['ios','android','web']){
  const geometry=compile('components/layout/dockGeometry.ts',{'react-native':{Platform:{OS:os}}});
  for(const safe of [0,20,24,34,50]){
   const bottom=geometry.dockBottomInset(safe);
   if(os==='ios'&&safe>=30){assert(bottom<safe);assert(bottom>=safe-18);assert(bottom>=12);}
   else assert(bottom>=safe);
   assert(bottom>=8);
   assert.equal(geometry.dockContentInset(safe)-geometry.DOCK_HEIGHT-bottom,12,'Composer and lists reserve exactly the dock footprint plus a gap');
  }
  assert(geometry.DOCK_HEIGHT<=88,'The entire dock must be compact, including the raised logo');
  assert(geometry.DOCK_HEIGHT-geometry.DOCK_BAR_TOP>=44,'Tab touch targets remain usable');
  assert(geometry.ASSISTANT_BUTTON_SIZE>=44&&geometry.ASSISTANT_BUTTON_SIZE<=64);
 }
});

test('the raised logo and selection are positioned before the first native layout, including remount and resize',async()=>{
 const viewport={width:390};
 class Value{
  constructor(value){this.value=value;}
  setValue(value){this.value=value;}
  stopAnimation(){}
 }
 const animate=(value,{toValue})=>({start(){value.setValue(toValue);},stop(){}});
 const native={Platform:{OS:'ios',select:styles=>styles.ios||styles.default},StyleSheet:{create:v=>v,absoluteFill:{},hairlineWidth:.5},
  View:'View',Text:'Text',Image:'Image',Pressable:({children,...props})=>React.createElement('Pressable',props,typeof children==='function'?children({pressed:false}):children),useWindowDimensions:()=>viewport,
  AccessibilityInfo:{isReduceTransparencyEnabled:async()=>false,addEventListener:()=>({remove(){}})},
  Animated:{Value,View:'AnimatedView',timing:animate,spring:animate},Easing:{out:v=>v,cubic:v=>v}};
 const geometry=compile('components/layout/dockGeometry.ts',{'react-native':native});
 const tokens=compile('theme/tokens.ts',{});
 const {createMobileStyles}=compile('theme/mobileStyles.ts',{'react-native':native,'./tokens':tokens,'../components/layout/dockGeometry':geometry});
 const ui=createMobileStyles(tokens.LIGHT_IOS,false,tokens.BRAND);
 const {BottomNav}=compile('components/layout/BottomNav.tsx',{
  'react-native':native,'expo-haptics':{selectionAsync:async()=>{}},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({bottom:34})},
  '../../theme/ThemeProvider':{useTheme:()=>({ui,isDark:false,BRAND:tokens.BRAND})},
  '../ui/InterfaceIcon':{InterfaceIcon:'Icon'},
  'react-native-svg':{__esModule:true,default:'Svg',Defs:'Defs',LinearGradient:'Gradient',Path:'Path',Stop:'Stop'},
  './DockMask':{DockMask:({children})=>React.createElement('Mask',null,children)},
  './DockMaterial':{DockMaterial:'Material'},'./dockAppearance':compile('components/layout/dockAppearance.ts',{}),
  './dockGeometry':geometry,'../../../assets/sellerpilot-tab-logo.png':1,
 });
 let root;const selected=[];
 const render=tab=>React.createElement(BottomNav,{tab,onTab:next=>selected.push(next),reduceMotion:true});
 await act(async()=>{root=create(render('orders'));});
 try{
  const verify=index=>{
   const dock=flatten(root.root.findByProps({testID:'bottom-dock'}).props.style);
   const assistant=root.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='SellerPilot');
   assert.equal(flatten(assistant.props.style).left,(dock.width-geometry.ASSISTANT_BUTTON_SIZE)/2,'Centered immediately, without sending any onLayout event');
   assert.equal(dock.bottom,16);
   const lens=flatten(root.root.findByProps({testID:'dock-selection'}).props.style);
   assert(Math.abs(lens.transform[0].translateX.value-index*(dock.width-10)/5)<.01,'No lens sliding in from the wrong tab on mount/resize');
  };
  verify(3);
  viewport.width=320;await act(async()=>root.update(render('orders')));verify(3);
  await act(async()=>root.update(render('home')));verify(0);
  await act(async()=>root.root.findAllByType('Pressable').find(node=>node.props.accessibilityLabel==='SellerPilot').props.onPress());
  assert.deepEqual(selected,['assistant']);
 }finally{await act(async()=>root.unmount());}
});
