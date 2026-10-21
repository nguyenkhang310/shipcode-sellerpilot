// React hook integration with a fake Keychain/API; never reads seller credentials.
// QA_NODE_MODULES must contain React and react-test-renderer 19.2.3.
const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
const qa=name=>require(process.env.QA_NODE_MODULES?path.join(process.env.QA_NODE_MODULES,name):name);
const React=qa('react'),{act,create}=qa('react-test-renderer');
globalThis.IS_REACT_ACT_ENVIRONMENT=true;

async function harness({saved=null,biometric=false,verify}={}){
 let stored=saved,protectedSession=biometric,clears=0,state,root,accessToken;
 const calls=[],pending=[];
 class ApiError extends Error{constructor(status,message){super(message);this.status=status;}}
 const identity={user:{id:1,username:'qa'},shop:{slug:'qa-shop'},expires_at:'2099-01-01T00:00:00Z'};
 const api={ApiError,setAccessToken:value=>accessToken=value,onUnauthorized:()=>{},apiRequest:async endpoint=>{
  calls.push(endpoint);
  if(endpoint==='/auth/login')return {data:{...identity,token:'new-valid-token'}};
  if(endpoint==='/auth/me'){
   if(verify==='pending')return new Promise((resolve,reject)=>pending.push({resolve,reject}));
   if(verify==='invalid')throw new ApiError(401,'expired');
   if(verify==='offline')throw new Error('offline');
   return {data:identity};
  }
  return {data:{}};
 }};
 const storage={native:true,biometricCapability:async()=>({available:true,label:'Face ID',reason:'enrollment'}),
  biometricEnabled:async()=>protectedSession,savedToken:async()=>stored,
  clearCredentials:async()=>{clears++;stored=null;protectedSession=false;},savePasswordSession:async value=>{stored=value;},
  protectSession:async()=>{},unprotectSession:async()=>{}};
 const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../src/features/auth/AuthProvider.tsx'),'utf8'),{
  compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,jsx:ts.JsxEmit.ReactJSX},
 }).outputText;
 const modules={react:React,'react/jsx-runtime':qa('react/jsx-runtime'),'react-native':{AppState:{addEventListener:()=>({remove(){}})}},
  '../../api/client':api,'./sessionStorage':storage};
 const loaded={exports:{}};vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{})
  (name=>{if(!modules[name])throw Error('Unexpected import '+name);return modules[name];},loaded,loaded.exports);
 function Probe(){state=loaded.exports.useAuth();return null;}
 const mount=()=>act(async()=>{root=create(React.createElement(loaded.exports.AuthProvider,null,React.createElement(Probe)));});
 const close=()=>act(async()=>root.unmount());
 await mount();
 return {get state(){return state;},get stored(){return stored;},get clears(){return clears;},get accessToken(){return accessToken;},calls,
  close,remount:async()=>{await close();await mount();},
  signIn:()=>act(async()=>state.signIn('qa','password')),
  reject:()=>act(async()=>pending.shift().reject(new ApiError(401,'expired'))),
  resolve:()=>act(async()=>pending.shift().resolve({data:identity})),
 };
}

test('a fresh install and a signed-out reload never send an anonymous /auth/me',async()=>{
 const h=await harness();try{
  assert.equal(h.state.phase,'signed_out');assert.equal(h.calls.length,0);
  await h.remount();assert.equal(h.calls.length,0);
 }finally{await h.close();}
});
test('one rejected saved session is cleared and is not retried on the next launch',async()=>{
 const h=await harness({saved:'rejected-token',verify:'invalid'});try{
  assert.equal(h.state.phase,'signed_out');assert.equal(h.clears,1);assert.equal(h.stored,null);
  assert.match(h.state.error,/Phiên đăng nhập đã hết hạn/);
  await h.remount();assert.equal(h.calls.filter(p=>p==='/auth/me').length,1);assert.equal(h.state.error,'');
 }finally{await h.close();}
});
test('a network failure does not destroy a possibly valid saved session',async()=>{
 const h=await harness({saved:'valid-token',verify:'offline'});try{
  assert.equal(h.state.phase,'signed_out');assert.equal(h.clears,0);assert.equal(h.stored,'valid-token');
  assert.match(h.state.error,/Chưa kết nối/);
 }finally{await h.close();}
});
test('a valid saved session is verified once; biometric sessions wait for explicit unlock',async()=>{
 const h=await harness({saved:'valid-token'});try{
  assert.equal(h.state.phase,'signed_in');assert.equal(h.accessToken,'valid-token');assert.equal(h.calls.length,1);
 }finally{await h.close();}
 const locked=await harness({saved:'protected-token',biometric:true});try{
  assert.equal(locked.state.phase,'locked');assert.equal(locked.calls.length,0);
 }finally{await locked.close();}
});
test('a delayed rejection from restoration cannot erase a newer successful login',async()=>{
 const h=await harness({saved:'old-token',verify:'pending'});try{
  await h.signIn();assert.equal(h.state.phase,'signed_in');
  await h.reject();assert.equal(h.state.phase,'signed_in');assert.equal(h.stored,'new-valid-token');assert.equal(h.clears,0);
 }finally{await h.close();}
});
