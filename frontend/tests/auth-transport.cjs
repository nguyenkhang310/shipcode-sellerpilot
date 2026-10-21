const {test}=require('node:test');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),ts=require('typescript');
function client(fetch,extension){
 const modules={'expo-constants':{__esModule:true,default:{}},'react-native':{Platform:{OS:'web'}},'./urls':{resolveApiUrls:()=>({api:'https://qa.example.test/api/v1',origin:'https://qa.example.test',store:'https://shop.example.test'})},
 '../integrations/extension':{inExtension:()=>Boolean(extension),extensionRequest:extension}};
 const code=ts.transpileModule(fs.readFileSync(path.resolve(__dirname,'../src/api/client.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
 const loaded={exports:{}};
 vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{process:{env:{}},__DEV__:false,Headers,AbortController,setTimeout,clearTimeout,fetch,Error})(name=>modules[name],loaded,loaded.exports);
 return loaded.exports;
}
const unauthorized=()=>new Response(JSON.stringify({detail:{message:'expired'}}),{status:401});
test('API and private media send Bearer only to this backend',async()=>{
 let header;const api=client(async(_,options)=>{header=options.headers.get('Authorization');return new Response('{"data":{}}');});
 api.setAccessToken('private-token');await api.apiRequest('/management/orders');assert.equal(header,'Bearer private-token');
 assert.equal(api.privateMediaHeaders(api.API_URL+'/product-drafts/1/image').Authorization,'Bearer private-token');
 assert.equal(Object.keys(api.privateMediaHeaders('https://another.example.test/product-drafts/1/image')).length,0);
 api.setAccessToken(null);await api.apiRequest('/auth/login');assert.equal(header,null);
});
test('401 locks the current session; wrong passwords do not expire a session',async()=>{
 const api=client(async()=>unauthorized());let count=0;api.onUnauthorized(()=>count++);api.setAccessToken('current');
 await assert.rejects(api.apiRequest('/auth/login'));assert.equal(count,0);
 await assert.rejects(api.apiRequest('/management/orders'));assert.equal(count,1);
});
test('a stale 401 cannot clear a new login',async()=>{
 let complete;const api=client(()=>new Promise(resolve=>complete=resolve));let count=0;api.onUnauthorized(()=>count++);
 api.setAccessToken('old');const request=api.apiRequest('/management/orders');api.setAccessToken('new');complete(unauthorized());
 await assert.rejects(request);assert.equal(count,0);
});
test('local extension RPC forwards authentication without persisting it',async()=>{
 let options;const api=client(null,async(_,value)=>{options=value;return {data:{}};});api.setAccessToken('private');
 await api.apiRequest('/management/products');assert.equal(options.headers.Authorization,'Bearer private');
});
