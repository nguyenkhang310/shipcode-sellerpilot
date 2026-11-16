// Theme regressions use an isolated browser and intercepted synthetic APIs.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const {snapshot,mockApi,enterApp}=require('./management-fixture.cjs');
const output=path.resolve(__dirname,'../../docs/evaluations/dock-themes');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 page=await browser.newPage({viewport:{width:390,height:844}});
 const errors=[],measurements=[];page.on('pageerror',e=>errors.push(e.message));
 await mockApi(page,(r,d,h)=>r.fulfill({headers:h,json:{data:snapshot(d)}}));
 const rows=Array.from({length:4},(_,i)=>({id:i+1,name:'Bàn phím không dây dành cho học tập và làm việc với tên sản phẩm rất dài cần xuống dòng rõ ràng',sku:'QA-LONG-000'+i,price_vnd:9999999999,stock:1000000,sold_count:1999,status:'active',image_url:null}));
 await page.route('**/api/v1/management/products?*',r=>r.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{data:{items:rows,total:rows.length}}}));
 await page.route('**/api/v1/management/orders?*',r=>r.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{data:{items:rows.map(row=>({id:row.id,status:'paid',customer_name:'Người nhận có họ và tên dài cần hiển thị rõ',created_at:'2026-11-12T07:00:00Z',quantity:100000000,total_vnd:row.price_vnd,items:[{id:row.id,name:row.name,quantity:1,price_vnd:row.price_vnd,sku:row.sku,image_url:null}],shipping_fee:0,discount_amount:0})),total:rows.length}}}));
 await page.goto(process.env.QA_APP_URL||'http://127.0.0.1:5174');
 await enterApp(page);
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
   assert.equal(surface.color.startsWith('rgba(36, 36, 40,'),dark,'Material must match the selected theme, including repeated toggles');
   assert(alpha>=.9&&alpha<1,'A strong frost stops chart text showing through: '+JSON.stringify(surface));
   assert.match(surface.blur||'',/blur\(/,'Backdrop survives theme changes');
   const edge=await page.getByTestId('dock-contour').getAttribute('stroke');
   assert(edge&&!/^#fff(?:fff)?$/i.test(edge),'Visible contour must not be white on white');
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   const dock=await page.getByTestId('bottom-dock').boundingBox();
   assert(dock.height<=88&&844-dock.y-dock.height<=12,'Dock stays compact and near the bottom: '+JSON.stringify(dock));
   const raised=await page.getByTestId('assistant-dock-button').boundingBox();
   assert(raised.width>=44&&raised.width<=64&&raised.y<dock.y+5,'Assistant stays raised without dominating the bar');
   for(const name of ['Quản lý','Sản phẩm','Đơn hàng','Shop']){
    const target=page.getByRole('tab',{name,exact:true}),box=await target.boundingBox();
    assert(box.width>=44&&box.height>=44,'Usable target: '+name);
    const label=await target.getByText(name,{exact:true}).evaluate(el=>({font:parseFloat(getComputedStyle(el).fontSize),overflow:el.scrollWidth>el.clientWidth+1}));
    assert(label.font>=12&&!label.overflow,'Legible label: '+name+' at '+width);
   }
   const hit=await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.closest('[role="tab"]')?.getAttribute('aria-label'),{x:raised.x+raised.width/2,y:raised.y+5});
   assert.equal(hit,'SellerPilot','The top edge of the raised assistant is clickable');
   measurements.push({width,dark,...surface,edge});
   await page.screenshot({path:path.join(output,`${dark?'dark':'light'}-${width}.png`)});
   await page.getByTestId('bottom-dock').screenshot({path:path.join(output,`dock-${dark?'dark':'light'}-${width}.png`)});
  }
 }
 // Repeated rapid selection must end with the lens under the selected tab.
 for(const name of ['Shop','Sản phẩm','Đơn hàng','Quản lý'])await page.getByRole('tab',{name,exact:true}).click();
 const target=await page.getByRole('tab',{name:'Quản lý',exact:true}).boundingBox();
 await page.waitForFunction(({x,width})=>{
  const box=document.querySelector('[data-testid="dock-selection"]').getBoundingClientRect();
  return Math.abs(box.x-x)<2&&Math.abs(box.width-width)<2;
 },{x:target.x,width:target.width});
 await page.getByTestId('management-scroll').evaluate(e=>e.scrollTop=e.scrollHeight);
 const last=await page.getByTestId('management-scroll').getByRole('button').last().boundingBox();
 const dock=await page.getByTestId('bottom-dock').boundingBox();
 assert(last&&last.y+last.height<dock.y,'Last dashboard action scrolls above the dock');
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();
 assert.equal(await input.inputValue(),'Bản nháp giữ qua nhiều lần đổi giao diện');
 const composer=await page.getByTestId('chat-composer').getByRole('textbox').boundingBox();
 assert(composer.y+composer.height<dock.y,'Composer clears the raised logo');
 await page.evaluate(()=>{Object.defineProperty(window.visualViewport,'height',{configurable:true,get:()=>innerHeight-320});window.visualViewport.dispatchEvent(new Event('resize'));});
 await page.getByTestId('bottom-dock').waitFor({state:'detached'});
 const keyboardComposer=await input.boundingBox();assert(keyboardComposer.y+keyboardComposer.height<=524,'Composer remains above the keyboard');
 await page.evaluate(()=>{delete window.visualViewport.height;window.visualViewport.dispatchEvent(new Event('resize'));});
 await page.getByTestId('bottom-dock').waitFor();
 // Long records in the other native-style tabs must also clear the dock.
 for(const width of [320,390,430,520]){
  await page.setViewportSize({width,height:640});
  for(const dark of [false,true]){
   await page.getByRole('tab',{name:'Shop',exact:true}).click();
   const toggle=page.getByRole('switch',{name:'Giao diện tối',exact:true});
   if(await toggle.isChecked()!==dark)await toggle.click();
   for(const name of ['Sản phẩm','Đơn hàng','Shop']){
    await page.getByRole('tab',{name,exact:true}).click();
    const id=name==='Sản phẩm'?'product-card-4':name==='Đơn hàng'?'order-card-4':null;
    const action=id?page.getByTestId(id).getByRole('button').last():page.getByRole('button',{name:'Thông tin kết nối',exact:true});
    // React Native's FlatList has its own scroll viewport.
    await page.evaluate(()=>{for(const el of document.querySelectorAll('div'))if(el.getClientRects().length&&getComputedStyle(el).overflowY==='auto')el.scrollTop=el.scrollHeight;});
    await action.waitFor();await action.scrollIntoViewIfNeeded();
    const box=await action.boundingBox(),dock=await page.getByTestId('bottom-dock').boundingBox();
    assert(box&&box.y+box.height<=dock.y,'Final action stays above the dock: '+name+' '+width);
    assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
    if(id){
     const overflow=await page.getByTestId(id).evaluate(card=>card.scrollWidth>card.clientWidth+1);
     assert(!overflow,'Long card content must fit: '+name+' '+width);
    }
    await page.screenshot({path:path.join(output,`${name}-${dark?'dark':'light'}-${width}.png`)});
   }
  }
 }
 await page.reload();
 await enterApp(page);
 await page.getByRole('tab',{name:'Shop',exact:true}).click();
 assert.equal(await page.getByRole('switch',{name:'Giao diện tối',exact:true}).isChecked(),true,'Saved appearance must survive reloading');
 assert.deepEqual(errors,[]);const report={checks:['16 light/dark switches at 320/390/430/520px preserve readable frost, visible edge, backdrop and selected tab','Compact geometry, 44px targets, raised-logo hit test and rapid tab selection','Theme changes preserve the unsent chat draft; composer clears the dock and emulated keyboard','Long product/order records and final Shop actions at four widths in both themes','Saved appearance survives reloading'],measurements,errors};
 fs.writeFileSync(path.join(output,'results.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(async e=>{console.error(e);if(page)await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}).finally(async()=>browser?.close());
