// Run against auth_ui_server.py only; all credentials and shop data are QA fixtures.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const {useQaServer,qaFetch}=require('./qa-server.cjs');
const fs=require('node:fs'),path=require('node:path');
const output=path.resolve(__dirname,'../../docs/evaluations/auth-transition');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 const identity=await fetch('http://127.0.0.1:8124/qa/identity').then(r=>r.json());
 assert(identity.temporary_shop&&identity.real_auth);
 const checks=[],errors=[];let motionMetrics;
 for(const reduced of [false,true]){
  page=await browser.newPage({viewport:{width:390,height:844},reducedMotion:reduced?'reduce':'no-preference'});
  page.on('pageerror',error=>errors.push(error.message));
  await useQaServer(page);
  await page.addInitScript(()=>{
   window.authFrames=[];window.brandFrames=[];
   const sample=()=>{
    const scene=document.querySelector('[data-testid="auth-protected-scene"]');
    if(scene){const s=getComputedStyle(scene);window.authFrames.push({opacity:+s.opacity,transform:s.transform,login:!!document.querySelector('[data-testid="auth-login-scene"]')});}
    const intro=document.querySelector('[data-testid="auth-brand-intro"]');
    if(intro){const paths=[...intro.querySelectorAll('path')],image=intro.querySelector('[data-testid="logo-colour"]');
     window.brandFrames.push({time:performance.now(),offsets:paths.map(p=>parseFloat(getComputedStyle(p).strokeDashoffset)),colour:image?+getComputedStyle(image).opacity:0});}
    if(window.authFrames.length<180)requestAnimationFrame(sample);
   };requestAnimationFrame(sample);
  });
  await page.goto('http://127.0.0.1:5174');
  if(!reduced){
   await page.waitForFunction(()=>window.brandFrames.some(f=>f.offsets.some(v=>v>0)&&f.colour===0));
   assert.equal(await page.getByTestId('intro-wordmark').evaluate(e=>getComputedStyle(e).opacity),'1','SellerPilot must already be visible while outlines are drawing');
   const bounds=await page.getByTestId('logo-colour').evaluate(e=>{
    const a=e.getBoundingClientRect(),b=e.parentElement.getBoundingClientRect();
    return {width:a.width,height:a.height,dx:(a.x+a.width/2)-(b.x+b.width/2),dy:(a.y+a.height/2)-(b.y+b.height/2)};
   });
   assert.equal(bounds.width,224);assert.equal(bounds.height,224);assert(Math.abs(bounds.dx)<.1&&Math.abs(bounds.dy)<.1,'Logo must share the outline centre, not spill from a corner');
   assert.equal(await page.locator('[data-testid^="logo-outline-code-"]').count(),6,'All four CODE letters and their counters must be drawn');
   await page.waitForFunction(()=>window.brandFrames.some(f=>f.offsets.length&&f.offsets.every(v=>v===0)&&f.colour===0));
   await page.screenshot({path:path.join(output,'logo-outline.png')});
   await page.waitForFunction(()=>window.brandFrames.some(f=>f.offsets.length&&f.offsets.every(v=>v===0)&&f.colour>=0.99));
   await page.screenshot({path:path.join(output,'logo-full-colour.png')});
  }
  await page.getByTestId('auth-brand-intro').waitFor({state:'detached'});
  if(!reduced){
   const frames=await page.evaluate(()=>window.brandFrames);
   assert(frames.some(f=>f.offsets.every(v=>v===0)&&f.colour>0&&f.colour<1),'Colour must fade in after every outline completes');
   const gaps=frames.slice(1).map((f,i)=>f.time-frames[i].time).sort((a,b)=>a-b);
   motionMetrics={samples:frames.length,medianFrameMs:+gaps[Math.floor(gaps.length/2)].toFixed(2),p95FrameMs:+gaps[Math.floor(gaps.length*.95)].toFixed(2)};
   checks.push('SHIP and CODE outlines finish before colour reveal; the complete logo is shown before the form');
  }
  await page.getByTestId('login-screen').waitFor();
  const login=page.getByRole('textbox',{name:'Email hoặc tên đăng nhập'}),password=page.getByLabel('Mật khẩu',{exact:true});
  await login.fill('qa-seller');await password.fill('SellerPilot-QA!2026');
  let release;
  const hold=new Promise(resolve=>{release=resolve;});
  await page.route('**/api/v1/auth/login',async route=>{await hold;await route.fulfill({response:await qaFetch(route)});});
  await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
  await page.getByTestId('login-progress').waitFor();
  assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
  release();await page.unroute('**/api/v1/auth/login');
  await page.getByTestId('auth-protected-scene').waitFor();
  await page.getByTestId('auth-login-scene').waitFor({state:'detached'});
  await page.waitForFunction(()=>getComputedStyle(document.querySelector('[data-testid="auth-protected-scene"]')).opacity==='1');
  const frames=await page.evaluate(()=>window.authFrames);
  if(!reduced)assert(frames.some(frame=>frame.opacity>0&&frame.opacity<1&&frame.login),'Expected a real crossfade, not an instant screen swap');
  else assert(!frames.some(frame=>frame.opacity>0&&frame.opacity<1),'Reduced motion must skip the crossfade');
  assert.equal(await page.getByRole('tab',{name:'Quản lý',exact:true}).getAttribute('aria-selected'),'true');
  await page.getByRole('tab',{name:'Shop',exact:true}).click();
  await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();
  await page.getByRole('button',{name:'Xác nhận đăng xuất',exact:true}).click();
  await page.getByTestId('login-screen').waitFor();
  assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
  await page.waitForTimeout(650);
  assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
  await page.screenshot({path:path.join(output,reduced?'reduced-motion.png':'normal-motion.png')});
  checks.push(reduced?'Reduced motion skips the crossfade; logout removes the protected scene':'Sign-in waits for authentication, runs a measured crossfade into Management, and logout clears shop UI');
  await page.close();
 }
 page=await browser.newPage({viewport:{width:390,height:844}});await useQaServer(page);
 page.on('pageerror',error=>errors.push(error.message));
 await page.route('**/api/v1/management/**',route=>route.fulfill({status:401,json:{detail:{code:'session_expired',message:'Phiên đăng nhập đã hết hạn.'}}}));
 await page.goto('http://127.0.0.1:5174');
 await page.getByRole('textbox',{name:'Email hoặc tên đăng nhập'}).fill('qa-seller');
 await page.getByLabel('Mật khẩu',{exact:true}).fill('SellerPilot-QA!2026');
 await page.getByRole('button',{name:'Đăng nhập',exact:true}).click();
 await page.getByRole('alert').filter({hasText:/Phiên đăng nhập đã hết hạn/}).waitFor();
 assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
 await page.waitForTimeout(700);
 assert.equal(await page.getByTestId('auth-protected-scene').count(),0);
 checks.push('A 401 during entry cancels the transition and never restores protected content from a late animation callback');
 assert.deepEqual(errors,[]);
 const report={checks,motionMetrics,errors};fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(async error=>{console.error(error);if(page){console.error((await page.locator('body').innerText()).slice(-2000));await page.screenshot({path:path.join(output,'failure.png')});}process.exitCode=1;}).finally(async()=>browser?.close());
