import {API, pageMessage, state, mutate} from './state.js';
import {getCachedPage, getSyncStatus} from './shopee-sync.js';
import {resourceContext, resourcePresent} from './shop-data.js';

let configPromise;
const config = () => configPromise ||= fetch(chrome.runtime.getURL('connection.local.json')).then(r => r.json());
const fail = (message, status = 503) => {throw Object.assign(Error(message), {status});};
async function backend(path, options = {}, signal) {
  const {token} = await config();
  if (!token) fail('Chạy npm run extension:setup và build lại extension.');
  let response;
  try {
    response = await fetch(API + '/browser-connector' + path, {...options,
      headers: {'Content-Type': 'application/json', Authorization: 'Bearer ' + token},
      signal: AbortSignal.any([signal || new AbortController().signal, AbortSignal.timeout(12000)]),
      credentials: 'omit', redirect: 'error'});
  } catch (error) {
    if (signal?.aborted) throw error;
    fail(error.name === 'TimeoutError' ? 'Backend phản hồi quá lâu. Kiểm tra terminal đang chạy API.'
      : 'Chưa kết nối được backend tại 127.0.0.1:8000. Chạy npm run demo trên máy này.');
  }
  if (response.status === 404) {
    fail(path === '/health' || path === '/requests'
      ? 'Backend đang chạy bản cũ, chưa có API extension. Nhấn Ctrl+C ở terminal chạy npm run demo rồi chạy lại npm run demo; không cần tạo lại key.'
      : 'Không tìm thấy tác vụ AI. Backend có thể vừa khởi động lại; gửi lại tin nhắn để thử.', 404);
  }
  const body = await response.json();
  if (!response.ok) {
    let msg = 'Kết nối AI chưa sẵn sàng.';
    if (typeof body.detail === 'string') msg = body.detail;
    else if (Array.isArray(body.detail)) msg = body.detail.map(e => `${e.loc?.slice(1).join('.') || 'trường'}: ${e.msg}`).join(', ');
    fail(msg, response.status);
  }
  return body.data;
}
const runId = () => Date.now();
const digest = async value => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value)))).map(v => v.toString(16).padStart(2, '0')).join('');
function compact(response) {
  return response.product_draft ? {...response, product_draft: {id: response.product_draft.id}} : response;
}
function hydrate(response, connection) {
  return response.product_draft ? {...response, product_draft: connection.drafts[response.product_draft.id] || null} : response;
}
function chatData(connection, conversation, answer, extra = {}) {
  return {run_id: runId(), conversation_id: conversation, answer, intent: 'sales_advice', mode: 'ai',
    provider: 'gemini', model: null, fallback_reason: null, tool: null, facts: {source: 'shopee_browser', scope: 'visible_page'},
    proposal: null, product_draft: null, integration_mode: 'shopee_browser', suggestions: [], ...extra};
}
async function ensureCurrent(id) {
  if ((await state()).id !== id) fail('Kết nối shop đã đổi. Mở lại cuộc trò chuyện.', 409);
}
async function infer(connection, body, signal, draft) {
  // Always verify the linked account live; cached data must never bypass this guard.
  const page = await pageMessage(connection, {kind: 'read'});
  let shopContext = null;
  if (!draft) {
    // Sending a message never starts, retries or waits on browser navigation.
    // A live page may supplement a missing cache, with partial coverage preserved.
    const resources = Object.fromEntries(await Promise.all(['products', 'dashboard', 'orders'].map(async key => {
      const cached = await getCachedPage(key, connection.id);
      return [key, resourceContext(cached || (resourcePresent(page, key) ? page : null), key)];
    })));
    const sync = await getSyncStatus(connection.id);
    shopContext = {connection_id: connection.id, account_label: connection.target.label, ...resources,
    sync_status: sync.status};
  }
  const conversation = connection.conversations[body.conversation_id];
  const history = (conversation?.turns || []).slice(-8).flatMap(turn => [
    {role: 'user', content: turn.message.slice(0, 6000)}, {role: 'assistant', content: turn.response.answer.slice(0, 6000)},
  ]);
  const requestId = crypto.randomUUID();
  await backend('/requests', {method: 'POST', body: JSON.stringify({
    request_id: requestId, connection_id: connection.id, message: body.message, snapshot: page.snapshot, history, shop_context: shopContext,
    mode: draft ? 'listing' : 'chat', draft: draft ? Object.fromEntries(['name', 'description', 'price_vnd', 'stock'].map(key => [key, draft[key]])) : {},
    images: draft?.preview_urls || [],
  })}, signal);
  const jobPath = '/requests/' + connection.id + '/' + requestId;
  const cancel = () => {void backend(jobPath + '/cancel', {method: 'POST'}).catch(() => {});};
  signal?.addEventListener('abort', cancel, {once: true});
  try {
    const deadline = Date.now() + 100000;
    while (Date.now() < deadline) {
      signal?.throwIfAborted();
      await ensureCurrent(connection.id);
      const result = await backend(jobPath, {}, signal);
      if (result.status === 'completed') return {...result.result, page};
      if (result.status === 'failed') fail(result.message || 'AI chưa xử lý được.', 502);
      if (result.status === 'cancelled') fail('Tin nhắn đã được dừng.', 409);
      await new Promise(resolve => setTimeout(resolve, 700));
    }
    cancel(); fail('AI phản hồi quá lâu. Thông tin bản nháp vẫn được giữ.', 408);
  } finally {signal?.removeEventListener('abort', cancel);}
}
function draftFor(connection, conversation) {
  return Object.values(connection.drafts).filter(d => d.conversation_id === conversation && ['collecting', 'ready'].includes(d.status)).at(-1);
}
async function saveTurn(connectionId, conversationId, message, response) {
  await mutate(connection => {
    if (connection.id !== connectionId) fail('Kết nối đã thay đổi.', 409);
    if (connection.deleted_conversations?.includes(conversationId)) fail('Cuộc trò chuyện đã bị xóa.', 410);
    const entry = connection.conversations[conversationId] ||= {id: conversationId, title: message.slice(0, 70), turns: [], is_pinned: false};
    entry.updated_at = new Date().toISOString();
    entry.turns.push({message, response: compact(response), created_at: entry.updated_at});
    // Keep photos once on the draft; repeated history references are reconstructed on read.
    if (entry.turns.length > 80) entry.turns.splice(0, entry.turns.length - 80);
    if (response.product_draft) connection.drafts[response.product_draft.id] = response.product_draft;
    connection.results ||= {};
  });
}
export async function handleApi(path, method, raw, signal) {
  const connection = await state();
  if (connection.mode === 'local') {
    // Full existing app behavior is available only after an explicit source switch.
    if (!/^\/(?:chat(?:\/requests\/[a-z0-9-]+(?:\/cancel)?)?|conversations(?:\/[a-z0-9-]+)?|management\/(?:dashboard|products|orders(?:\/[0-9]+)?)|product-drafts(?:\/images-data|\/[0-9]+\/(?:publish|cancel))|product-edits\/[0-9]+\/(?:confirm|reject)|proposals\/[0-9]+\/(?:confirm|reject)|health)(?:\?[^#]*)?$/i.test(path)) fail('Đường dẫn không được phép.', 400);
    const response = await fetch(API + path, {method, body: method === 'GET' ? undefined : raw,
      headers: {'Content-Type': 'application/json'}, credentials: 'omit', redirect: 'error', signal});
    const result = await response.json();
    if (!response.ok) fail(typeof result.detail === 'string' ? result.detail : result.detail?.message || 'API chưa sẵn sàng.', response.status);
    return result;
  }
  const body = raw ? JSON.parse(raw) : {};
  if (path === '/conversations' && method === 'GET') return {data: {items: Object.values(connection.conversations)
    .map(({turns, ...value}) => ({...value, turns: turns.length})).sort((a, b) => Number(b.is_pinned) - Number(a.is_pinned) || b.updated_at.localeCompare(a.updated_at))}};
  const history = path.match(/^\/conversations\/([a-z0-9-]+)$/i);
  if (history) {
    const entry = connection.conversations[history[1]];
    if (!entry) fail('Không tìm thấy cuộc trò chuyện.', 404);
    if (method === 'GET') return {data: {...entry, turns: entry.turns.map(turn => ({...turn, response: hydrate(turn.response, connection)}))}};
    return mutate(current => {
      if (current.id !== connection.id) fail('Kết nối đã đổi.', 409);
      if (method === 'DELETE') {
        delete current.conversations[history[1]];
        current.deleted_conversations ||= [];
        current.deleted_conversations.push(history[1]);
        current.results = {}; current.image_requests = {};
        for (const [id, draft] of Object.entries(current.drafts)) if (draft.conversation_id === history[1]) delete current.drafts[id];
        return {data: {id: history[1], deleted: true}};
      }
      if (method !== 'PATCH' || typeof body.is_pinned !== 'boolean') fail('Thao tác không hợp lệ.', 422);
      current.conversations[history[1]].is_pinned = body.is_pinned;
      return {data: {id: history[1], is_pinned: body.is_pinned}};
    });
  }
  if (path === '/product-drafts/images-data' && method === 'POST') {
    if (!connection.target?.label) fail('Chọn tài khoản Shopee trước khi gửi ảnh.', 409);
    const targetStatus = await pageMessage(connection, {kind: 'target_status'});
    if (!targetStatus.target_matches) fail('Tài khoản Shopee không còn khớp. Kiểm tra đăng nhập và chọn lại tài khoản trước khi gửi ảnh.', 409);
    const images = body.images_base64;
    if (!Array.isArray(images) || !images.length || images.length > 6 || images.some(v => typeof v !== 'string' || v.length > 1400000) || images.reduce((n, v) => n + v.length, 0) > 5000000) fail('Chọn tối đa 6 ảnh, tổng dung lượng ảnh đã nén dưới 5 MB.', 413);
    const hash = await digest(raw);
    const replay = connection.image_requests?.[body.request_id];
    if (replay) {
      if (replay.hash !== hash) fail('Mã tải ảnh đã dùng cho nội dung khác.', 409);
      return {data: hydrate(replay.response, connection)};
    }
    if (draftFor(connection, body.conversation_id)) fail('Hoàn tất hoặc hủy bản nháp hiện tại trước nhé.', 409);
    const now = new Date().toISOString();
    const urls = images.map(v => v.startsWith('data:') ? v : 'data:image/jpeg;base64,' + v);
    const draft = {id: runId(), conversation_id: body.conversation_id, status: 'collecting', name: null, description: null,
      price_vnd: null, stock: null, category_id: null, category_name: null, sku: null, published_product_id: null,
      preview_url: urls[0], preview_urls: urls, image_count: urls.length, missing_fields: ['name', 'description', 'price_vnd', 'stock'], created_at: now, decided_at: null};
    const response = chatData(connection, body.conversation_id, 'Đã nhận ảnh. Bạn muốn đăng sản phẩm nào và có thông tin gì cho món này?',
      {intent: 'create_product', tool: 'create_product_draft', product_draft: draft});
    await saveTurn(connection.id, body.conversation_id, '[Ảnh sản phẩm]', response);
    if (body.request_id) await mutate(current => {
      if (current.id !== connection.id) fail('Kết nối đã đổi.', 409);
      current.image_requests ||= {}; current.image_requests[body.request_id] = {hash, response: compact(response)};
    });
    return {data: response};
  }
  if (path === '/chat' && method === 'POST') {
    if (typeof body.message !== 'string' || !body.message.trim() || body.message.length > 4000) fail('Tin nhắn không hợp lệ.', 422);
    const hash = await digest(raw);
    const replay = connection.results?.[body.request_id];
    if (replay) {
      if (replay.hash !== hash) fail('Mã tin nhắn đã dùng cho nội dung khác.', 409);
      return {data: hydrate(replay.data, connection)};
    }
    const conversation = body.conversation_id || crypto.randomUUID();
    const draft = draftFor(connection, conversation);
    const result = await infer(connection, {...body, conversation_id: conversation}, signal, draft);
    signal?.throwIfAborted();
    let next;
    if (draft) next = {...draft, ...result.draft, status: result.missing_fields.length ? 'collecting' : 'ready', missing_fields: result.missing_fields};

    let autoFilled = false;
    let updatedItems = [];
    if (draft) {
      const msg = body.message.toLowerCase();
      let newBrand = null, newOrigin = null, newWeight = null;
      if (/không có thương hiệu|no brand|không thương hiệu/i.test(msg)) newBrand = 'Không có thương hiệu';
      else {
        const bm = body.message.match(/thương hiệu[:\s]+([^\n,.]+)/i);
        if (bm) newBrand = bm[1].trim();
      }

      if (/việt nam|vietnam/i.test(msg)) newOrigin = 'Việt Nam';
      else {
        const om = body.message.match(/xuất xứ[:\s]+([^\n,.]+)/i);
        if (om) newOrigin = om[1].trim();
      }

      const wm = body.message.match(/(\d+)\s*(?:g|gam|gram|kg)?/i);
      if (wm && /g|gam|gram|nặng|trọng lượng|kg/i.test(msg)) {
        const num = parseInt(wm[1], 10);
        newWeight = /kg/i.test(msg) ? num * 1000 : num;
      }

      if (newBrand) { draft.brand = newBrand; updatedItems.push(`Thương hiệu: ${newBrand}`); }
      if (newOrigin) { draft.origin = newOrigin; updatedItems.push(`Xuất xứ: ${newOrigin}`); }
      if (newWeight) { draft.weight_g = newWeight; updatedItems.push(`Trọng lượng: ${newWeight}g`); }

      if (updatedItems.length > 0) {
        try {
          const page = await pageMessage(connection, {kind: 'read'});
          if (page?.snapshot?.url && page.snapshot.url.includes('tiktok.com')) {
            const payloadDraft = {
              name: draft.name,
              description: draft.description,
              price_vnd: draft.price_vnd || 300000,
              stock: draft.stock || 50,
              images: draft.preview_urls?.length ? draft.preview_urls : (draft.preview_url ? [draft.preview_url] : []),
              category_name: draft.category_name || null,
              brand: draft.brand || 'Không có thương hiệu',
              origin: draft.origin || 'Việt Nam',
              weight_g: draft.weight_g || 500
            };
            await pageMessage(connection, {
              kind: 'fill',
              document_id: page.document_id,
              page_context: page.page_context,
              url: page.snapshot.url,
              draft: payloadDraft
            });
            autoFilled = true;
          }
        } catch { /* ignore */ }
      }
    }

    let finalAnswer = result.answer;
    if (autoFilled) {
      finalAnswer = `Đã tự động điền ${updatedItems.join(', ')} vào form TikTok Shop cho bạn rồi nhé! Bạn kiểm tra lại và bấm "Gửi để xét duyệt" trên TikTok Shop nhé.`;
    }

    const response = chatData(connection, conversation, finalAnswer, {provider: result.provider, model: result.model,
      ...(next ? {product_draft: next, intent: 'create_product', tool: next.status === 'ready' ? 'prepare_product_publish' : 'update_product_draft'} : {})});
    await saveTurn(connection.id, conversation, body.message, response);
    if (body.request_id) await mutate(current => { if (current.id === connection.id) {
      current.results[body.request_id] = {data: compact(response), hash};
      const ids = Object.keys(current.results); for (const id of ids.slice(0, Math.max(0, ids.length - 80))) delete current.results[id];
    } });
    return {data: response};
  }
  const job = path.match(/^\/chat\/requests\/([a-z0-9-]+)(\/cancel)?$/i);
  if (job) {
    const result = connection.results?.[job[1]];
    if (job[2]) return {data: {request_id: job[1], status: 'cancelled', response: null, error: null}};
    if (!result) fail('Chưa có kết quả được lưu.', 404);
    return {data: {request_id: job[1], status: 'completed', response: {data: hydrate(result.data, connection)}, error: null}};
  }
  const decision = path.match(/^\/product-drafts\/(\d+)\/(publish|cancel)$/);
  if (decision && method === 'POST') {
    const draft = connection.drafts[decision[1]];
    if (!draft || !['collecting', 'ready'].includes(draft.status)) fail('Bản nháp không còn khả dụng.', 409);
    let updated, result;
    if (decision[2] === 'cancel') updated = {...draft, status: 'cancelled', preview_url: '', preview_urls: [], image_count: 0};
    else {
      if (draft.status !== 'ready') fail('Cần bổ sung thông tin bản nháp.', 409);
      const page = await pageMessage(connection, {kind: 'read'});
      const baseDraft = Object.fromEntries(['name', 'description', 'price_vnd', 'stock'].map(key => [key, draft[key]]));
      const isTikTok = page.snapshot.url && page.snapshot.url.includes('tiktok.com');
      const payloadDraft = isTikTok ? {
        ...baseDraft,
        images: draft.preview_urls?.length ? draft.preview_urls : (draft.preview_url ? [draft.preview_url] : []),
        category_name: draft.category_name || null,
        brand: draft.brand || null,
        origin: draft.origin || null,
        weight_g: draft.weight_g || 500
      } : baseDraft;
      result = await pageMessage(connection, {kind: 'fill', document_id: page.document_id, page_context: page.page_context, url: page.snapshot.url,
        draft: payloadDraft});
      const filled = result.report.filter(row => row.status === 'filled');
      if (!filled.length) {
        const labels = {name: 'Tên sản phẩm', description: 'Mô tả', price_vnd: 'Giá bán', stock: 'Tồn kho'};
        const missing = result.report.filter(row => row.status !== 'filled').map(row => `${labels[row.field] || row.field} (${row.status === 'unmapped' ? 'chưa thấy ô' : 'chưa lưu'})`).join(', ');
        fail(missing ? `Chưa điền xong: ${missing}. Mở menu kết nối → “Gán ô trên form sản phẩm” để chỉ định ô.` : 'Một số ô chưa nhận dữ liệu. Mở “Gán ô nhập” để liên kết đúng trường, rồi thử lại. Kiểm tra cả những ô đã điền.', 409);
      }
      updated = {...draft, status: 'filled', decided_at: new Date().toISOString()};
    }
    await mutate(current => {if (current.id !== connection.id) fail('Kết nối đã đổi.', 409); current.drafts[draft.id] = updated;
      for (const convo of Object.values(current.conversations)) for (const turn of convo.turns) if (turn.response.product_draft?.id === draft.id) turn.response.product_draft = {id: updated.id};});
    if (result?.unfilled_required !== undefined && draft.conversation_id) {
      if (result.unfilled_required.length) {
        const unique = [...new Set(result.unfilled_required)].slice(0, 5);
        const promptText = `Mình đã tự động điền các thông tin sản phẩm và tải ảnh lên TikTok Shop! Còn ${unique.length} mục thuộc tính cần bạn xác nhận:\n` +
          unique.map(f => `• ${f}`).join('\n') +
          `\nBạn muốn điền thông tin nào cho các mục này? Bạn có thể nhắn ở đây (Ví dụ: Thương hiệu: Không có thương hiệu, Xuất xứ: Việt Nam...) hoặc chọn trực tiếp trên trang TikTok Shop nhé!`;
        await saveTurn(connection.id, draft.conversation_id, '[Trợ lý kiểm tra form]', {
          answer: promptText,
          intent: 'request_attributes',
          tool: 'prompt_attributes'
        });
      } else {
        const promptText = `Đã tự động điền đầy đủ tất cả thông tin sản phẩm, ngành hàng, thương hiệu và tải ảnh lên TikTok Shop! Bạn kiểm tra lại và bấm "Gửi để xét duyệt" trên TikTok Shop nhé.`;
        await saveTurn(connection.id, draft.conversation_id, '[Trợ lý kiểm tra form]', {
          answer: promptText,
          intent: 'form_filled_success',
          tool: 'confirm_fill'
        });
      }
    }
    return {data: updated};
  }
  if (path.startsWith('/management/')) fail('Chưa xác minh adapter cho API quản lý local trên Shopee. Giao diện Shopee dùng dữ liệu đồng bộ riêng, không gán số liệu còn thiếu thành 0.', 501);
  fail('Thao tác này chưa được nối và kiểm chứng trên Shopee thật. Không có thay đổi nào được thực hiện.', 501);
}
export {backend};
