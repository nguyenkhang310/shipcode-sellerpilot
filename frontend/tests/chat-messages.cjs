const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const filename=path.resolve(__dirname,'../src/features/assistant/chatMessages.ts');
const code=ts.transpileModule(fs.readFileSync(filename,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText;
const loaded={exports:{}};
vm.runInNewContext('(function(require,module,exports){'+code+'\n})',{})(()=>({productDraftImageUrl:url=>'http://api'+url}),loaded,loaded.exports);
const {restoreMessages,latestProductCards}=loaded.exports;
const {assistantText,assistantMessage}=loaded.exports;
const draft={id:1,status:'ready',preview_urls:['/image-a','/image-b']};
const turn=(id,tool,message,answer,product=draft)=>({message,response:{run_id:id,tool,answer,product_draft:product}});

test('history combines internal image upload with the seller caption and keeps its gallery',()=>{
 const messages=restoreMessages([
  turn(1,'create_product_draft','Đã thêm 2 ảnh sản phẩm','Sản phẩm tên gì?'),
  turn(2,'prepare_product_publish','Bàn phím trắng, bán 990k, kho 20','Bản nháp đã đủ thông tin.'),
  turn(3,'update_product_draft','Để 850k nhé','Đã sửa giá.'),
 ]);
 assert.equal(messages.length,4);
 assert.equal(messages[0].text,'Bàn phím trắng, bán 990k, kho 20');
 assert.equal(JSON.stringify(messages[0].imageUris),JSON.stringify(['http://api/image-a','http://api/image-b']));
 assert.equal(messages[2].imageUris,undefined);
 assert.equal(messages.some(message=>message.text==='Sản phẩm tên gì?'),false);
});

test('upload without a following seller turn remains recoverable',()=>{
 const messages=restoreMessages([turn(1,'create_product_draft','Đã thêm ảnh','Bạn đang bán gì?')]);
 assert.equal(messages.length,2);
 assert.equal(messages[0].imageUris.length,2);
});

test('cancelled draft history does not reload deleted images; ordinary chat stays intact',()=>{
 const messages=restoreMessages([
  turn(1,'create_product_draft','Đã thêm ảnh','Bạn đang bán gì?',{...draft,status:'cancelled'}),
  turn(2,'update_product_draft','Hủy','Đã hủy',{...draft,status:'cancelled'}),
  turn(3,'get_inventory','Xem kho','Còn 20 cái',null),
 ]);
 assert.equal(messages.length,4);
 assert.equal(messages[0].imageUris,undefined);
 assert.equal(messages[3].text,'Còn 20 cái');
});

test('each product keeps its own latest card when multiple products share a conversation',()=>{
 const messages=restoreMessages([
  turn(1,'prepare_product_publish','Sản phẩm một','Bản nháp một'),
  turn(2,'update_product_draft','Đổi giá một','Đã sửa một'),
  turn(3,'prepare_product_publish','Sản phẩm hai','Bản nháp hai',{...draft,id:2}),
 ]);
 const cards=latestProductCards(messages);
 assert.equal(cards.size,2);
 assert(cards.has('2:a')&&cards.has('3:a'));
 assert(!cards.has('1:a'));
});

test('serialized answer is decoded for fresh messages and persisted history, without changing seller text',()=>{
 const answer='Hôm nay chưa có đơn mới.\n\nGiá trị đơn là 0đ.';
 const wrapped=JSON.stringify({answer});
 const input=turn(20,'get_shop_summary',wrapped,wrapped,null);
 const fresh=assistantMessage(input.response);
 assert.equal(fresh.text,answer);
 assert.equal(fresh.response.answer,answer);
 assert.equal(input.response.answer,wrapped);
 const messages=restoreMessages([input]);
 assert.equal(messages[0].text,wrapped);
 assert.equal(messages[1].text,answer);
});

test('nested and fenced answer objects are decoded but code samples and literal escapes are preserved',()=>{
 assert.equal(assistantText(JSON.stringify({answer:JSON.stringify({answer:'Nội dung.'})})),'Nội dung.');
 assert.equal(assistantText('```json\n{"answer":"Dòng một.\\nDòng hai."}\n```'),'Dòng một.\nDòng hai.');
 for (const text of ['Văn bản có \\n giữ nguyên.','{"answer":"Ví dụ", "stock":8}',
   'Ví dụ: {"answer":"Nội dung"}', '```ts\nconst answer = "Ví dụ";\n```']) {
   assert.equal(assistantText(text),text);
 }
});

test('a text-first draft does not consume its later gallery when history is restored',()=>{
 const messages=restoreMessages([
  turn(1,'update_product_draft','Đăng bàn phím giúp mình','Bạn thêm ảnh nhé.',{id:1,status:'collecting',preview_urls:[]}),
  turn(2,'create_product_draft','Đã thêm 2 ảnh','Đã nhận ảnh.'),
  turn(3,'prepare_product_publish','Đúng mẫu này','Bản nháp sẵn sàng.'),
 ]);
 assert.equal(messages[0].imageUris?.length||0,0);
 assert.deepEqual(Array.from(messages[2].imageUris),['http://api/image-a','http://api/image-b']);
});

test('appended photos stay with their own caption and an unfinished last upload is visible',()=>{
 const product={...draft,preview_urls:['/front','/side','/back']};
 const upload=(id,start,count)=>({...turn(id,'create_product_draft','Ảnh '+id,'Đã nhận ảnh.',product),
   response:{...turn(id,'create_product_draft','','',product).response,facts:{image_start_index:start,new_image_count:count}}});
 const messages=restoreMessages([
   turn(1,'update_product_draft','Đăng bàn phím','Bạn thêm ảnh nhé.',product),
   upload(2,0,1),turn(3,'update_product_draft','Mặt trước đây','Đã nhận.',product),
   upload(4,1,1),turn(5,'update_product_draft','Thêm mặt bên','Đã nhận.',product),
   upload(6,2,1),
 ]);
 assert.equal(messages.length,8);
 assert.equal(messages[0].imageUris,undefined);
 assert.deepEqual(Array.from(messages[2].imageUris),['http://api/front']);
 assert.deepEqual(Array.from(messages[4].imageUris),['http://api/side']);
 assert.deepEqual(Array.from(messages[6].imageUris),['http://api/back']);
 assert.equal(messages[6].text,'Ảnh 6');
});
