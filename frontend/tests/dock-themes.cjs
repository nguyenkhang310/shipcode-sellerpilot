// Theme regressions use an isolated browser and intercepted synthetic APIs.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {snapshot,mockApi}=require('./management-fixture.cjs');
const output=path.resolve(__dirname,'../../docs/evaluations/dock-themes');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[],measurements=[];page.on('pageerror',e=>errors.push(e.message));
 await mockApi(page,(r,d,h)=>r.fulfill({headers:h,json:{data:snapshot(d)}}));
 await page.goto(process.env.QA_APP_URL||'http://127.0.0.1:5174');
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();
 const input=page.getByRole('textbox',{name:'Nhắn cho SellerPilot',exact:true});await input.fill('Bản nháp giữ qua nhiều lần đổi giao diện');
 for(const width of [320,390,430,520]){
  await page.setViewportSize({width,height:844});
  for(const dark of [false,true,false,true]){
   await page.getByRole('tab',{name:'Shop',exact:true}).click();
   const toggle=page.getByRole('switch',{name:'Giao diện tối',exact:true});
   if((await toggle.isChecked())!==dark)await toggle.click();
   assert.equal(await toggle.isChecked(),dark);
   assert.equal(await page.getByRole('tab',{name:'Shop',exact:true}).getAttribute('aria-selected'),'true');
   await page.getByRole('tab',{name:'Quản lý',exact:true}).click();
   await page.waitForFunction(()=>[...document.querySelectorAll('[role="heading"]')].filter(e=>e.getClientRects().length).every(e=>{for(let p=e;p;p=p.parentElement)if(+getComputedStyle(p).opacity<.99)return false;return true;}));
   await page.getByTestId('management-scroll').evaluate(e=>e.scrollTop=0);
   await page.getByTestId('period-summary').screenshot({path:path.join(output,`performance-${dark?'dark':'light'}-${width}.png`)});
   await page.getByTestId('management-scroll').evaluate(e=>e.scrollTop=e.scrollHeight);
   const surface=await page.getByTestId('dock-material').evaluate(e=>{
    const color=getComputedStyle(e).backgroundColor;
    for(let p=e;p;p=p.parentElement){const blur=getComputedStyle(p).backdropFilter;if(blur&&blur!=='none')return{color,blur};}
    return{color,blur:null};
   });
   const alpha=Number(surface.color.match(/,\s*([\d.]+)\)$/)?.[1]||1);
   assert.equal(surface.color.startsWith('rgba(37, 45, 58,'),dark,'Material must match the selected theme, including repeated toggles');
   assert(alpha>=.7&&alpha<.9,'Material stays frosted and readable rather than clear or opaque: '+JSON.stringify(surface));
   assert.match(surface.blur||'',/blur\(/,'Backdrop survives theme changes');
   const edge=await page.getByTestId('dock-contour').getAttribute('stroke');
   assert(edge&&!/^#fff(?:fff)?$/i.test(edge),'Visible contour must not be white on white');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   measurements.push({width,dark,...surface,edge});
   await page.screenshot({path:path.join(output,`${dark?'dark':'light'}-${width}.png`)});
   await page.getByTestId('bottom-dock').screenshot({path:path.join(output,`dock-${dark?'dark':'light'}-${width}.png`)});
  }
 }
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();
 assert.equal(await input.inputValue(),'Bản nháp giữ qua nhiều lần đổi giao diện');
 await page.reload();
 await page.getByRole('tab',{name:'Shop',exact:true}).click();
 assert.equal(await page.getByRole('switch',{name:'Giao diện tối',exact:true}).isChecked(),true,'Saved appearance must survive reloading');
 assert.deepEqual(errors,[]);const report={checks:['16 light/dark switches at 320/390/430/520px preserve readable frost, visible edge, backdrop and selected tab','Theme changes preserve the unsent chat draft','Saved appearance survives reloading'],measurements,errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(async e=>{console.error(e);if(page)await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}).finally(async()=>browser?.close());
