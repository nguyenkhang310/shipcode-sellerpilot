// Requires chat_reliability_server.py; reads only its disposable legacy order #3.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {useQaServer}=require('./qa-server.cjs');
const output=path.resolve(__dirname,'../../docs/evaluations/order-chat');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 page=await browser.newPage({viewport:{width:390,height:844}});
 assert.equal((await (await page.request.get('http://127.0.0.1:8123/qa/identity')).json()).temporary_shop,true);
 await useQaServer(page);
 const errors=[],requests=[];let popups=0;
 page.on('pageerror',e=>errors.push(e.message));page.on('popup',()=>popups++);
 page.on('request',r=>{if(r.method()==='PATCH')requests.push(r.url());});
 await page.goto('http://127.0.0.1:5174');
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();
 await page.getByRole('textbox',{name:'Nhắn cho SellerPilot'}).fill('Đơn #3 sao rồi?');
 await page.getByRole('button',{name:'Gửi tin nhắn',exact:true}).click();
 const open=page.getByRole('button',{name:'Mở chi tiết đơn #3',exact:true});
 await open.waitFor();await open.click();
 const tracking=page.getByTestId('order-tracking');await tracking.waitFor();
 assert.match(await tracking.innerText(),/Đã giao/);
 assert.match(await tracking.innerText(),/Trạng thái hiện tại/);
 const events=await page.request.get('http://127.0.0.1:8123/api/v1/management/orders/3');
 assert.deepEqual((await events.json()).data.events,[]);
 for(const width of [320,390,520]){
  await page.setViewportSize({width,height:width===320?640:844});
  await page.emulateMedia({colorScheme:width===390?'dark':'light',reducedMotion:'reduce'});
  await page.waitForTimeout(350);
  await tracking.getByText('Trạng thái hiện tại. Chưa có thời điểm cập nhật.',{exact:true}).scrollIntoViewIfNeeded();
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.screenshot({path:path.join(output,`legacy-${width}.png`)});
 }
 await page.getByRole('button',{name:'Đóng chi tiết đơn hàng',exact:true}).click();
 await page.getByRole('textbox',{name:'Nhắn cho SellerPilot'}).fill('Còn mã vận đơn?');
 await page.getByRole('button',{name:'Gửi tin nhắn',exact:true}).click();
 await page.waitForFunction(()=>document.querySelectorAll('[aria-label="Mở chi tiết đơn #3"]').length===2);
 assert.deepEqual(requests,[]);assert.equal(popups,0);assert.deepEqual(errors,[]);
 const report={checks:['Chat resolves a current seller order, opens detail in-app and remembers its reference','Legacy delivered status appears in history without invented timestamps at 320/390/520px'],mutations:requests.length,popups,errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(async error=>{console.error(error);if(page)await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}).finally(async()=>browser?.close());
