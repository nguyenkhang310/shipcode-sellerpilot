const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function storage({os='ios',expoGo=false}={}){
 const values=new Map(),calls=[];let failedDelete=false,cancelled=false;
 const secure={WHEN_UNLOCKED_THIS_DEVICE_ONLY:6,canUseBiometricAuthentication:()=>true,
  async getItemAsync(key,options){calls.push(['get',key,options]);if(cancelled&&options?.requireAuthentication)throw Error('cancel');return values.get(key)??null;},
  async setItemAsync(key,value,options){calls.push(['set',key,options]);values.set(key,value);},
  async deleteItemAsync(key,options){calls.push(['delete',key,options]);if(failedDelete)throw Error('keychain unavailable');values.delete(key);}};
 const modules={'expo-constants':{__esModule:true,default:{executionEnvironment:expoGo?'store':'standalone'},ExecutionEnvironment:{StoreClient:'store'}},
  'expo-secure-store':secure,'expo-local-authentication':{supportedAuthenticationTypesAsync:async()=>[2],AuthenticationType:{FACIAL_RECOGNITION:2},hasHardwareAsync:async()=>true,isEnrolledAsync:async()=>true},
  'react-native':{Platform:{OS:os}},'../../api/client':{API_URL:'https://qa.example.test/api/v1'}};
 const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../src/features/auth/sessionStorage.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const loaded={exports:{}};vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{})(name=>modules[name],loaded,loaded.exports);
 return {api:loaded.exports,values,calls,failDelete:()=>failedDelete=true,cancel:()=>cancelled=true};
}
test('web never persists a session, even when a storage function is called',async()=>{
 const {api,calls}=storage({os:'web'});
 await api.savePasswordSession('private');await api.protectSession('private');await api.unprotectSession();await api.clearCredentials();
 assert.equal(await api.savedToken(false),null);assert.equal(await api.biometricEnabled(),false);assert.equal(calls.length,0);
 assert.equal((await api.biometricCapability()).reason,'web');
});
test('Expo Go does not advertise Face ID; a native build checks enrollment',async()=>{
 assert.equal((await storage({expoGo:true}).api.biometricCapability()).available,false);
 const result=await storage().api.biometricCapability();assert.equal(result.available,true);assert.equal(result.label,'Face ID');
});
test('Face ID stores the token with authentication required and removes plain session',async()=>{
 const {api,values,calls}=storage();await api.savePasswordSession('private');await api.protectSession('private');
 assert.equal(await api.savedToken(false),null);assert.equal(await api.biometricEnabled(),true);
 assert.equal(await api.savedToken(true),'private');
 const protectedRead=calls.find(([action,key])=>action==='get'&&key.endsWith('.protected'));
 assert.equal(protectedRead[2].requireAuthentication,true);assert.equal(protectedRead[2].keychainAccessible,6);
 assert(![...values.keys()].some(key=>key.endsWith('.session')));
});
test('cancelling Face ID cannot release the saved token',async()=>{
 const {api,cancel}=storage();await api.savePasswordSession('private');await api.protectSession('private');cancel();
 await assert.rejects(api.savedToken(true),/cancel/);assert.equal(await api.savedToken(false),null);
});
test('logout remains durable if Keychain deletion fails',async()=>{
 const {api,failDelete}=storage();await api.savePasswordSession('private');await api.protectSession('private');failDelete();
 await assert.rejects(api.clearCredentials());assert.equal(await api.savedToken(true),null);assert.equal(await api.biometricEnabled(),false);
});
test('serialized writes prevent a delayed enable from restoring a logged-out session',async()=>{
 const {api}=storage();await api.savePasswordSession('private');
 await Promise.all([api.protectSession('private'),api.clearCredentials()]);
 assert.equal(await api.savedToken(false),null);assert.equal(await api.savedToken(true),null);assert.equal(await api.biometricEnabled(),false);
});
test('disabling biometrics authenticates first; failed migration blocks automatic restore',async()=>{
 const {api,failDelete}=storage();await api.savePasswordSession('private');await api.protectSession('private');
 await api.unprotectSession();assert.equal(await api.savedToken(false),'private');assert.equal(await api.biometricEnabled(),false);
 await api.protectSession('private');failDelete();await assert.rejects(api.unprotectSession());
 assert.equal(await api.savedToken(false),null);assert.equal(await api.savedToken(true),null);
});
