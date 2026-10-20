// All records/media are intercepted fixtures. No real shop or external inference.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const {snapshot,mockApi}=require('./management-fixture.cjs');
const output=path.resolve(__dirname,'../../docs/evaluations/readability');fs.mkdirSync(output,{recursive:true});
let browser,page;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 page=await browser.newPage({viewport:{width:320,height:640}});
 const errors=[],checks=[];page.on('pageerror',e=>errors.push(e.message));
 await mockApi(page,(route,days,headers)=>route.fulfill({headers,json:{data:snapshot(days)}}));
 await page.route('**/api/v1/product-drafts/99/image**',route=>route.fulfill({contentType:'image/png',path:path.resolve(__dirname,'../assets/shipcode-logo-app.png')}));
 const description=Array.from({length:18},(_,i)=>`Đoạn ${i+1}: Bàn phím dành cho góc làm việc. Giữ đầy đủ mô tả tiếng Việt để người bán duyệt trước khi đăng.`).join('\n\n');
 const draft={id:99,status:'ready',preview_url:'/product-drafts/99/image?view=1',preview_urls:['/product-drafts/99/image?view=1','/product-drafts/99/image?view=2'],image_count:2,name:'Bàn phím không dây màu trắng cho học tập và công việc với tên dài cần xuống dòng rõ ràng',description,category_id:4,category_name:'Máy Tính & Laptop',price_vnd:999999999,stock:1000000,sku:'QA-LONG-SKU-ONLY',missing_fields:[],published_product_id:null,created_at:'2026-10-20T01:00:00Z',decided_at:null};
 let conversation,answer,historyRequested=false;
 await page.route('**/api/v1/chat',async route=>{
  const body=route.request().postDataJSON();conversation=body.conversation_id;
  answer={run_id:99,conversation_id:conversation,answer:'Mình đã soạn bản nháp. Bạn kiểm tra nội dung trước khi đăng.',intent:'create_product',mode:'ai',provider:'gemini',model:'qa',fallback_reason:null,tool:'prepare_product_publish',facts:{},proposal:null,product_draft:draft,integration_mode:'local_store',suggestions:[]};
  await route.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{data:answer}});
 });
 await page.goto(process.env.QA_APP_URL||'http://127.0.0.1:5174');
 const account=page.getByRole('button',{name:'Cài đặt shop và giao diện',exact:true});
 await account.screenshot({path:path.join(output,'avatar.png')});
 const label=page.getByRole('tab',{name:'Sản phẩm',exact:true}).getByText('Sản phẩm',{exact:true});
 assert(await label.evaluate(el=>parseFloat(getComputedStyle(el).fontSize))>=12,'Navigation no longer shrinks to 10px');
 await page.getByRole('tab',{name:'SellerPilot',exact:true}).click();
 await page.getByRole('textbox',{name:'Nhắn cho SellerPilot',exact:true}).fill('Đăng bàn phím giúp mình');
 await page.getByRole('button',{name:'Gửi tin nhắn',exact:true}).click();
 const card=page.getByTestId('product-draft-card');await card.waitFor();
 for(const width of [320,390,430,520]){
  await page.setViewportSize({width,height:844});
  const raised=await page.getByTestId('assistant-dock-button').boundingBox();
  const productTab=await page.getByRole('tab',{name:'Sản phẩm',exact:true}).boundingBox();
  assert(raised.y+20<productTab.y,'Assistant visibly rises above the four management tabs');
  assert(raised.width>=70&&raised.height>=70,'Assistant keeps a generous touch target');
  assert(await page.getByTestId('dock-contour').getAttribute('d').then(d=>d.includes('80 C')),'Dock contour has a real concave cutout');
  const hit=await page.evaluate(({x,y})=>document.elementFromPoint(x,y)?.closest('[role="tab"]')?.getAttribute('aria-label'),{x:raised.x+raised.width/2,y:raised.y+8});
  assert.equal(hit,'SellerPilot','The protruding part is clickable, not clipped by the bar');
  for(const name of ['Quản lý','Sản phẩm','Đơn hàng','Shop']){
   const tab=await page.getByRole('tab',{name,exact:true}).boundingBox();
   assert(tab.width>=44&&tab.height>=44,'Each management tab has a usable touch target');
   const fits=await page.getByRole('tab',{name,exact:true}).getByText(name,{exact:true}).evaluate(el=>el.scrollWidth<=el.clientWidth+1);
   assert(fits,'Navigation caption is fully visible: '+name+' at '+width);

  }

  await page.getByRole('button',{name:'Xem ảnh sản phẩm 2',exact:true}).click();
  await page.waitForFunction(()=>document.querySelector('[data-testid="draft-main-image"] img')?.currentSrc.includes('view=2'));
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  const overflow=await card.evaluate(el=>el.scrollWidth>el.clientWidth+1);assert(!overflow,'Draft card does not overflow at '+width);
  const body=page.getByTestId('draft-description'),before=await body.boundingBox();
  await page.getByRole('button',{name:'Xem toàn bộ mô tả',exact:true}).click();
  assert((await body.boundingBox()).height>before.height,'Full description is readable');
  await page.getByRole('button',{name:'Thu gọn mô tả',exact:true}).click();
  const action=page.getByRole('button',{name:'Đăng sản phẩm lên UTech Official',exact:true});await action.scrollIntoViewIfNeeded();
  const box=await action.boundingBox();assert(box.width>=44&&box.height>=48);
  await page.screenshot({path:path.join(output,`draft-${width}.png`)});
 }
 checks.push('Raised 72px assistant, concave glass dock, clickable upper edge and four 44px management targets at all widths');
 checks.push('Readable navigation, long title/price/stock, two selectable photos and expandable description at 320/390/430/520px');
 // A delayed history reload after a decision must not overwrite a new conversation.
 await page.route('**/api/v1/product-drafts/99/publish',route=>route.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{data:{...draft,status:'published'}}}));
 await page.route('**/api/v1/conversations/*',async route=>{
  historyRequested=true;await new Promise(r=>setTimeout(r,1000));
  await route.fulfill({headers:{'Access-Control-Allow-Origin':'*'},json:{data:{id:conversation,turns:[{message:'Hội thoại cũ',response:{...answer,answer:'OLD_CONVERSATION_SHOULD_NOT_RETURN'},created_at:draft.created_at}]}}});
 });
 await page.getByRole('button',{name:'Đăng sản phẩm lên UTech Official',exact:true}).click();
 await page.waitForFunction(()=>true);while(!historyRequested)await new Promise(r=>setTimeout(r,20));
 await page.getByRole('button',{name:'Tạo cuộc trò chuyện mới',exact:true}).click();
 await new Promise(r=>setTimeout(r,1300));
 assert.equal(await page.getByText('OLD_CONVERSATION_SHOULD_NOT_RETURN',{exact:true}).count(),0);
 checks.push('A late post-decision history response cannot replace the newly opened conversation');
 assert.deepEqual(errors,[]);console.log(JSON.stringify({checks,errors},null,2));fs.writeFileSync(path.join(output,'results.json'),JSON.stringify({checks,errors},null,2));
})().catch(async e=>{console.error(e);if(page)await page.screenshot({path:path.join(output,'failure.png')});process.exitCode=1;}).finally(async()=>browser?.close());
