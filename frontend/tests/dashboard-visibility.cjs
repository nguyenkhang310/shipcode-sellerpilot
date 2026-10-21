// All APIs are intercepted fixtures. Never uses a real account or seller data.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {snapshot,mockApi,enterApp}=require('./management-fixture.cjs');
const output=path.resolve(__dirname,'../../docs/evaluations/dashboard-visibility');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 page=await browser.newPage({viewport:{width:390,height:844}});
 let value=12345678;const errors=[],assets=[],measurements=[];
 page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(/shipcode-(mark|intro|logo-transparent)/.test(r.url()))assets.push(r.url());});
 await mockApi(page,(route,days,headers)=>{
  const data=snapshot(days);data.order_value_vnd=value;data.delivered_value_vnd=Math.round(value*.8);
  data.average_order_vnd=Math.round(value/data.order_count);data.change_percent=-65.8;
  return route.fulfill({headers,json:{data}});
 });
 await page.goto(process.env.QA_APP_URL||'http://127.0.0.1:5174');await enterApp(page);
 const amount=page.getByTestId('dashboard-order-value');await amount.filter({hasText:'12.345.678'}).waitFor();
 const logoLoaded=async()=>page.waitForFunction(()=>{
  const images=[...document.querySelectorAll('[aria-label="ShipCode"] img')].filter(i=>i.closest('[aria-hidden="true"]')===null&&i.getClientRects().length);
  return images.length>0&&images.every(i=>i.complete&&i.naturalWidth===192);
 });
 await logoLoaded();
 assert(assets.some(u=>u.includes('shipcode-mark')));assert(!assets.some(u=>u.includes('shipcode-logo-transparent')));
 for(const dark of [false,true]){
  await page.getByRole('tab',{name:'Shop',exact:true}).click();
  const toggle=page.getByRole('switch',{name:'Giao diện tối',exact:true});
  if(await toggle.isChecked()!==dark)await toggle.click();
  await page.getByRole('tab',{name:'Quản lý',exact:true}).click();
  for(const width of [320,390,430,520]){
   await page.setViewportSize({width,height:844});
   for(const next of [0,12345678,Number.MAX_SAFE_INTEGER]){
    value=next;await page.getByRole('button',{name:'Đồng bộ số liệu',exact:true}).click();
    await amount.filter({hasText:next.toLocaleString('vi-VN')}).waitFor();
    const box=await amount.evaluate(e=>{
     const rect=e.getBoundingClientRect(),range=document.createRange();range.selectNodeContents(e);
     return {width:rect.width,height:rect.height,ink:range.getBoundingClientRect().width,font:+parseFloat(getComputedStyle(e).fontSize)};
    });
    assert(box.font>=20&&box.height>=50,'The amount must not collapse to tiny native text');
    assert(box.ink<=box.width+1,'All digits and currency must fit: '+JSON.stringify({width,next,box}));
    for(const id of ['dashboard-average-order','dashboard-delivered-value']){
     const metric=page.getByTestId(id);
     const geometry=await metric.evaluate(e=>{
      const range=document.createRange();range.selectNodeContents(e);
      return {text:e.textContent,ink:range.getBoundingClientRect().width,width:e.getBoundingClientRect().width,font:parseFloat(getComputedStyle(e).fontSize)};
     });
     assert(geometry.font>=14&&geometry.ink<=geometry.width+1,'Secondary amount must stay readable without ellipsis: '+JSON.stringify({id,width,next,geometry}));
     assert(!geometry.text.includes('…'));
    }
    measurements.push({dark,width,value:next,...box});
   }
   value=12345678;await page.getByRole('button',{name:'Đồng bộ số liệu',exact:true}).click();await amount.filter({hasText:'12.345.678'}).waitFor();
   await page.getByTestId('period-summary').screenshot({path:path.join(output,`value-${dark?'dark':'light'}-${width}.png`)});
   const material=await page.getByTestId('dock-material').evaluate(e=>getComputedStyle(e).backgroundColor);
   assert(+material.match(/,\s*([\d.]+)\)$/)[1]>=.85);
   await page.getByTestId('bottom-dock').screenshot({path:path.join(output,`dock-${dark?'dark':'light'}-${width}.png`)});
  }
 }
 // Opening Assistant and returning to login must reuse the warmed small mark.
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();await logoLoaded();
 await page.getByRole('tab',{name:'Shop',exact:true}).click();
 await page.getByRole('button',{name:'Đăng xuất',exact:true}).click();
 await page.getByRole('button',{name:'Xác nhận đăng xuất',exact:true}).click();
 await page.getByTestId('login-screen').waitFor();await logoLoaded();
 assert.deepEqual(errors,[]);
 const result={checks:['Readable complete amounts including zero and MAX_SAFE_INTEGER at 320/390/430/520px in both themes','Dock has a consistent 85% tint over its blur','Assistant and logout login use the warmed 192px mark; no original 1.2MB logo request'],measurements,errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify({checks:result.checks,errors},null,2));
})().catch(async e=>{console.error(e);if(page)await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}).finally(async()=>browser?.close());
