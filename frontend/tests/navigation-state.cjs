// Component-level render counts and native animation lifecycle; no API calls.
const {test}=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const qa=name=>require(process.env.QA_NODE_MODULES?path.join(process.env.QA_NODE_MODULES,name):name);
const React=qa('react'),{create,act}=qa('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT=true;
function compile(file,modules){
 const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../src',file),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,jsx:ts.JsxEmit.ReactJSX}}).outputText;
 const result={exports:{}};
 vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{setTimeout,clearTimeout})(name=>{
  if(name==='react')return React;if(name==='react/jsx-runtime')return qa('react/jsx-runtime');
  if(!(name in modules))throw Error('Unexpected dependency '+name);return modules[name];
 },result,result.exports);return result.exports;
}
const flatten=style=>Array.isArray(style)?Object.assign({},...style.map(flatten)):style;

test('tab roots switch without an opacity/translation queue; unrelated tabs and glass do not rerender on dashboard updates',async()=>{
 const renders={dashboard:0,assistant:0,products:0,orders:0,settings:0,dock:0},mounts={assistant:0};
 let dashboard={days:1,selectedDate:null,data:{tasks:{},order_count:1},loading:false,refreshing:false,error:'',onDate(){},onDays(){},refresh(){},pullRefresh(){}};
 const ui={outer:{},app:{},host:{},scene:{position:'absolute'},header:{}};
 function Dashboard(){renders.dashboard++;return React.createElement('Dashboard');}
 const Assistant=React.forwardRef(function Assistant(props,ref){
  renders.assistant++;const [draft,setDraft]=React.useState('');
  React.useEffect(()=>{mounts.assistant++;},[]);
  React.useImperativeHandle(ref,()=>({ask:setDraft}));
  return React.createElement('Chat',{draft,setDraft,active:props.active});
 });
 function Panel({route}){renders[route.kind]++;return React.createElement('Panel',{kind:route.kind});}
 const Dock=React.memo(function Dock(props){renders.dock++;return React.createElement('Dock',props);});
 const {AppShell}=compile('app/AppShell.tsx',{
  'expo-status-bar':{StatusBar:'StatusBar'},
  'react-native':{View:'View',Text:'Text',KeyboardAvoidingView:'KeyboardView',Platform:{OS:'ios'},Keyboard:{dismiss(){},addListener:()=>({remove(){}})}},
  'react-native-safe-area-context':{useSafeAreaInsets:()=>({top:44,bottom:34})},
  '../api/client':{STORE_URL:'https://store.example.test'},'../features/dashboard/useManagement':{useManagement:()=>dashboard},
  './navigation':{initialTab:()=> 'home'},'../components/layout/TopBar':{TopBar:'TopBar'},
  '../components/layout/BottomNav':{BottomNav:Dock},'../features/dashboard/DashboardScreen':{DashboardScreen:Dashboard},
  '../features/dashboard/ManagementSheet':{ManagementSheet:Panel},'../features/assistant/AssistantChat':{AssistantChat:Assistant},
  '../theme/ThemeProvider':{useTheme:()=>({ui})},'../integrations/extension':{inExtension:()=>false},
  '../integrations/ExtensionBar':{},'../components/layout/useReducedMotion':{useReducedMotion:()=>false},
 });
 const props={darkMode:false,onDarkModeChange(){}};let root;
 await act(async()=>{root=create(React.createElement(AppShell,props));});
 const select=tab=>act(async()=>root.root.findByType('Dock').props.onTab(tab));
 try{
  const warm={...renders};
  for(const tab of ['products','orders','shop'])await select(tab);
  assert.equal(renders.dashboard,warm.dashboard);assert.equal(renders.assistant,warm.assistant,'A hidden conversation must not be parsed again for every unrelated tab switch');
  await select('assistant');
  await act(async()=>root.root.findByType('Chat').props.setDraft('Giữ bản nháp này'));
  const before={...renders};
  dashboard={...dashboard,data:{tasks:{},order_count:2}};
  await act(async()=>root.update(React.createElement(AppShell,props)));
  assert.equal(renders.assistant,before.assistant);assert.equal(renders.products,before.products);assert.equal(renders.orders,before.orders);assert.equal(renders.dock,before.dock,'Do not reconfigure the glass during dashboard polling');
  assert.equal(renders.dashboard,before.dashboard+1);
  await select('home');await select('assistant');
  assert.equal(root.root.findByType('Chat').props.draft,'Giữ bản nháp này');assert.equal(mounts.assistant,1);
  for(const tab of ['products','orders','assistant','shop','home']){
   await select(tab);
   for(const key of ['home','products','orders','assistant','shop']){
    const scene=root.root.findByProps({testID:'tab-scene-'+key}),style=flatten(scene.props.style);
    assert.equal(style.display,key===tab?'flex':'none');assert.equal(scene.props.pointerEvents,key===tab?'auto':'none');
    assert.equal(scene.props['aria-hidden'],key!==tab);assert(!('opacity' in style)&&!('transform' in style));
   }
  }
 }finally{await act(async()=>root.unmount());}
});

test('typing loops pause in hidden tabs and never hold native list-render interactions',async()=>{
 const loops=[],timings=[];let onReduce,root;
 class Value{setValue(){}interpolate(){return 0;}}
 const {TypingIndicator}=compile('features/assistant/TypingIndicator.tsx',{
  'react-native':{View:'View',Text:'Text',Platform:{OS:'ios'},AccessibilityInfo:{isReduceMotionEnabled:async()=>false,addEventListener:(_,fn)=>{onReduce=fn;return{remove(){}};}},
   Animated:{Value,View:'AnimatedView',timing:(_,config)=>{timings.push(config);return{};},delay:()=>({}),sequence:()=>({}),loop:()=>{const loop={active:false,start(){this.active=true;},stop(){this.active=false;}};loops.push(loop);return loop;}},Easing:{inOut:v=>v,quad:v=>v}},
  '../../components/ui/BrandLogo':{BrandLogo:'Logo'},'../../theme/ThemeProvider':{useTheme:()=>({IOS:{secondary:'#666'},isDark:false})},
 });
 const render=active=>React.createElement(TypingIndicator,{active});
 await act(async()=>{root=create(render(true));});
 try{
  assert.equal(loops.filter(l=>l.active).length,3);assert(timings.every(t=>t.isInteraction===false&&t.useNativeDriver===true));
  await act(async()=>root.update(render(false)));assert.equal(loops.filter(l=>l.active).length,0);
  await act(async()=>root.update(render(true)));assert.equal(loops.filter(l=>l.active).length,3);
  await act(async()=>onReduce(true));assert.equal(loops.filter(l=>l.active).length,0);
 }finally{await act(async()=>root.unmount());}
 assert.equal(loops.filter(l=>l.active).length,0);
});

test('chat controls and tabs use SF Symbols on iOS, with bundled fallback glyphs on web/Android',()=>{
 const ios=compile('components/ui/NativeSymbol.ios.tsx',{'expo-symbols':{SymbolView:'Symbol'}});
 const fallback=compile('components/ui/NativeSymbol.tsx',{});
 for(const native of [ios,fallback]){
  const modules={'./NativeSymbol':native,'@expo/vector-icons':{Ionicons:'Glyph'},'react-native-svg':{__esModule:true,default:'Svg',Path:'Path',Rect:'Rect'}};
  const {SystemIcon}=compile('components/ui/SystemIcon.tsx',modules),{InterfaceIcon}=compile('components/ui/InterfaceIcon.tsx',modules);
  for(const [name,symbol] of Object.entries({'create-outline':'square.and.pencil','copy-outline':'doc.on.doc','share-outline':'square.and.arrow.up',add:'plus',stop:'stop.fill'})){
   const icon=SystemIcon({name,size:22,color:'#eee'}),result=icon.type(icon.props);
   if(native===ios){assert.equal(result.type,'Symbol');assert.equal(result.props.name,symbol);assert.equal(result.props.tintColor,'#eee');assert.equal(result.props.size,22);}
   else assert.equal(result.props.children.type,'Glyph');
  }
  const tab=InterfaceIcon({name:'products',color:'#123'}),result=tab.type(tab.props);
  if(native===ios)assert.equal(result.props.name,'cube');else assert.equal(result.props.children.type,'Svg');
 }
});

