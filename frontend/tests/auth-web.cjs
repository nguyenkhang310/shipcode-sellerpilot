// Run on the web development server so React's development-only SVG warnings
// are visible. All auth/shop requests go to the disposable auth QA server.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const app=process.env.QA_APP_URL||'http://127.0.0.1:8081',api=process.env.QA_API_ORIGIN||'http://127.0.0.1:8124';
const output=path.resolve(__dirname,'../../docs/evaluations/auth-web');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 const identity=await fetch(api+'/qa/identity').then(r=>r.json());assert(identity.temporary_shop&&identity.real_auth,'Use auth_ui_server.py, never a seller account');
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 const checks=[],errors=[],requests=[];
 for(const reduced of [false,true]){
  page=await browser.newPage({viewport:reduced?{width:1280,height:900}:{width:390,height:844},reducedMotion:reduced?'reduce':'no-preference'});
  page.on('pageerror',e=>errors.push(e.message));
  page.on('console',m=>{if(m.type()==='error')errors.push(m.text());});
  const proxy=async route=>{
   const url=new URL(route.request().url());
   if(url.origin===api)return route.continue();
   requests.push({method:route.request().method(),path:url.pathname});
   const response=await route.fetch({url:api+url.pathname+url.search});
   return route.fulfill({response});
  };
  await page.route('**/api/v1/**',proxy);await page.route('**/store-static/**',proxy);
  await page.addInitScript(()=>{
   window.introFrames=[];
   let seen=false;
   const sample=()=>{
    const root=document.querySelector('[data-testid="auth-brand-intro"]');
    if(root){seen=true;const paths=[...root.querySelectorAll('[data-testid^="logo-outline-"]')],colour=root.querySelector('[data-testid="logo-colour"]'),wordmark=root.querySelector('[data-testid="intro-wordmark"]');
     window.introFrames.push({offsets:paths.map(p=>parseFloat(getComputedStyle(p).strokeDashoffset)),code:paths.filter(p=>p.dataset.testid.startsWith('logo-outline-code-')).length,colour:colour?+getComputedStyle(colour).opacity:0,wordmark:wordmark?+getComputedStyle(wordmark).opacity:0});
    }
    if(!seen||root)requestAnimationFrame(sample);
   };requestAnimationFrame(sample);
  });
  await page.goto(app,{waitUntil:'domcontentloaded'});
  if(!reduced){
   await page.waitForFunction(()=>window.introFrames.some(f=>f.offsets.some(n=>n>0)&&f.colour===0));
   await page.screenshot({path:path.join(output,'drawing.png')});
  }
  await page.getByTestId('auth-brand-intro').waitFor({state:'detached'});
  if(!reduced){
   const frames=await page.evaluate(()=>window.introFrames);
   assert(frames.some(f=>f.code===6&&f.offsets.every(v=>v===0)&&f.colour===0));
   assert(frames.some(f=>f.code===6&&f.offsets.every(v=>v===0)&&f.colour>=.99));
   assert(frames.every(f=>f.wordmark===1));
   checks.push('SHIP/CODE outlines finish before the original colour logo; SellerPilot appears throughout the drawing');
  }
  await page.getByTestId('login-screen').waitFor();
  if(!reduced){
   // This request bypasses the proxy above: the browser performs a real CORS
   // preflight against the real-auth fixture before submitting synthetic data.
   const status=await page.evaluate(async api=>{
    const response=await fetch(api+'/api/v1/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login_id:'qa-seller',password:'SellerPilot-QA!2026'})});
    const body=await response.json();
    if(response.status===200)await fetch(api+'/api/v1/auth/logout',{method:'POST',headers:{Authorization:'Bearer '+body.data.token}});
    return response.status;
   },api);
   assert.equal(status,200,'Browser preflight must permit the JSON login request');
   checks.push('Real browser CORS preflight, login and logout pass against a disposable authenticated backend');
  }
  await page.getByRole('textbox',{name:'Email hoặc tên đăng nhập'}).fill('qa-seller');
  await page.getByLabel('Mật khẩu',{exact:true}).fill('SellerPilot-QA!2026');
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByTestId('auth-login-scene').waitFor({state:'detached'});
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('[data-testid="auth-protected-scene"]')).opacity==='1');
  assert.equal(await page.getByRole('tab',{name:'Quản lý',exact:true}).getAttribute('aria-selected'),'true');
  await page.getByRole('tab',{name:'Shop',exact:true}).click();
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();await page.getByRole('button',{name:'Xác nhận đăng xuất',exact:true}).click();
  await page.getByTestId('login-screen').waitFor();assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
  assert.equal(await page.getByTestId('auth-brand-intro').count(),0,'Logout must return directly to login without replaying the intro');
  await page.waitForFunction(()=>{
   const hero=document.querySelector('[data-testid="login-screen"] [role="heading"]')?.parentElement;
   return hero&&getComputedStyle(hero).opacity==='1';
  });
  await page.screenshot({path:path.join(output,reduced?'reduced-motion.png':'normal-motion.png')});
  checks.push(reduced?'Desktop and reduced motion: login/logout work without replaying the intro':'Mobile web: login opens Management; logout clears protected content');
  await page.close();page=null;
 }
 assert.deepEqual(errors,[],'No React/SVG console errors or unhandled page errors');
 const result={checks,errors,requests};fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result,null,2));
})().catch(async e=>{console.error(e);if(page){await page.screenshot({path:path.join(output,'failure.png')});console.error((await page.locator('body').innerText()).slice(-1500));}process.exitCode=1;}).finally(async()=>browser?.close());
