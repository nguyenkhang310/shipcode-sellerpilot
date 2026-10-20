// Isolated synthetic TikTok form. Never attaches to a signed-in browser.
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.CHROME_EXECUTABLE||undefined});
 try{
  const page=await browser.newPage();
  await page.route('https://seller-vn.tiktok.com/**',route=>route.fulfill({contentType:'text/html',body:`<!doctype html><html><meta charset="utf-8"><header><button>fixture-shop</button></header><main><form>
  <label>Tên sản phẩm<input id="name"></label><label>Mô tả sản phẩm<textarea id="description"></textarea></label><label>Giá bán<input id="price"></label><label>Tồn kho<input id="stock"></label>
  <label>Trọng lượng (g)<input id="weight"></label><label>Chiều dài<input id="length"></label>
  <div class="arco-form-item"><label>Xuất xứ</label><select id="origin"><option value="">Chọn</option><option>Việt Nam</option></select></div><button type="submit">Gửi xét duyệt</button></form></main></html>`}));
  await page.goto('https://seller-vn.tiktok.com/product/create');
  await page.evaluate(()=>{
   window.chrome={runtime:{id:'qa',onMessage:{addListener:fn=>window.listener=fn}}};window.submitted=false;
   document.querySelector('form').addEventListener('submit',e=>{e.preventDefault();window.submitted=true;});
  });
  await page.addScriptTag({content:fs.readFileSync(path.resolve(__dirname,'../content/tiktok.js'),'utf8')});
  const target={label:'fixture-shop'};
  const message=value=>page.evaluate(value=>new Promise(resolve=>window.listener(value,{id:'qa'},resolve)),{target,...value});
  const read=await message({kind:'read'});assert(read.ok,read.error);
  const draft={name:'Bàn phím',description:'Dòng một\nDòng hai.',price_vnd:500000,stock:0};
  const fill=extra=>message({kind:'fill',document_id:read.data.document_id,page_context:read.data.page_context,url:read.data.snapshot.url,draft:{...draft,...extra}});
  const result=await fill();assert(result.ok,result.error);
  assert(result.data.report.every(row=>row.status==='filled'),JSON.stringify(result.data));
  assert.equal(await page.locator('#name').inputValue(),'Bàn phím','Never append invented authenticity');
  assert.equal(await page.locator('#stock').inputValue(),'0','Zero stock is not replaced by 50');
  assert.equal(await page.locator('#weight').inputValue(),'');assert.equal(await page.locator('#length').inputValue(),'');assert.equal(await page.locator('#origin').inputValue(),'');
  assert.equal(await page.evaluate(()=>window.submitted),false);
  await page.evaluate(()=>document.querySelector('#stock').addEventListener('input',e=>{e.target.value='99';}));
  const rejected=await fill();assert(rejected.ok,rejected.error);assert.equal(rejected.data.report.find(r=>r.field==='stock').status,'not_retained');
  await page.evaluate(()=>{const el=document.createElement('label');el.innerHTML='Giá bán<input>';document.querySelector('form').append(el);});
  const ambiguous=await fill();assert.equal(ambiguous.data.report.find(r=>r.field==='price_vnd').status,'unmapped');
  assert.equal(await page.evaluate(()=>window.submitted),false);
  console.log('PASS · TikTok: giữ nguyên tên, tồn 0, không đoán thuộc tính/vận chuyển, không submit, xác minh dữ liệu được giữ và từ chối ô giá mơ hồ.');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
