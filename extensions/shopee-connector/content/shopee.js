// Runs in Chrome's isolated world. No cookies, private APIs or page-script eval.
(() => {
  if (globalThis.__sellerPilotContent) return;
  globalThis.__sellerPilotContent = true;
  const ORIGIN = 'https://banhang.shopee.vn';
  const documentId = crypto.randomUUID();
  const bindings = new Map();
  let selection;
  let readContext;
  let contextUrl = location.href, contextToken = crypto.randomUUID();
  const pageContext = () => {
    if (contextUrl !== location.href) {contextUrl = location.href; contextToken = crypto.randomUUID();}
    return contextToken;
  };
  const visible = el => Boolean(el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden');
  const editable = el => el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el?.isContentEditable;
  const text = el => (el?.innerText || el?.textContent || '').normalize('NFC').trim().replace(/\s+/g, ' ');
  const label = el => (el.getAttribute('aria-label') || [...(el.labels || [])].map(text).join(' ')
    || el.getAttribute('placeholder') || '').slice(0, 200);
  const allowed = () => {
    if (location.origin !== ORIGIN) throw Error('Chỉ hỗ trợ Kênh Người Bán Shopee.');
    if ([...document.querySelectorAll('input[type=password]')].some(visible)) throw Error('Bạn đăng nhập Shopee trước nhé.');
  };
  const pageUrl = () => location.origin + location.pathname;
  const identityNodes = () => [...document.querySelectorAll('span,a,button,div,strong')]
    .filter(el => !editable(el) && !el.closest('main,[role=main],form,table')
      && (el.textContent || '').trim().length <= 160 && visible(el)
      && text(el).length > 0 && text(el).length <= 80
      && ![...el.children].some(child => visible(child) && text(child) === text(el)));
  function checkTarget(target) {
    if (!target?.label || typeof target.label !== 'string') throw Error('Chọn tài khoản Shopee trước khi đọc dữ liệu hoặc điền form.');
    if (identityNodes().filter(el => text(el) === target.label).length !== 1)
      throw Error('Không xác nhận được tài khoản đã chọn trên trang này. Kiểm tra đăng nhập rồi chọn lại tài khoản.');
  }
  function selectTarget(nonce) {
    if (typeof nonce !== 'string' || !/^[a-z0-9-]{36}$/i.test(nonce)) throw Error('Yêu cầu chọn tài khoản không hợp lệ.');
    selection?.abort();
    const controller = selection = new AbortController();
    const hint = document.createElement('div');
    hint.textContent = 'SellerPilot · Bấm tên tài khoản/shop trên thanh đầu trang để liên kết. Esc để hủy.';
    Object.assign(hint.style, {position: 'fixed', top: '8px', left: '50%', transform: 'translateX(-50%)',
      zIndex: '2147483647', padding: '12px 18px', maxWidth: '70vw', font: '14px/20px system-ui',
      borderRadius: '10px', background: '#0B1F3F', color: '#fff', boxShadow: '0 4px 20px #0003', pointerEvents: 'none'});
    document.documentElement.append(hint);
    const timer = setTimeout(() => controller.abort(), 30000);
    controller.signal.addEventListener('abort', () => {hint.remove(); clearTimeout(timer);}, {once: true});
    document.addEventListener('keydown', event => {if (event.key === 'Escape') controller.abort();}, {signal: controller.signal});
    document.addEventListener('click', event => {
      if (!event.isTrusted) return;
      const candidates = identityNodes();
      const node = event.composedPath().find(el => candidates.includes(el));
      if (!node || node === hint || candidates.filter(el => text(el) === text(node)).length !== 1) return;
      event.preventDefault(); event.stopImmediatePropagation();
      const label = text(node);
      controller.abort();
      void chrome.runtime.sendMessage({kind: 'target_selected', nonce, document_id: documentId, label}).then(result => {
        const notice = document.createElement('div');
        notice.textContent = result?.ok ? 'SellerPilot · Đã chọn tài khoản ' + label : 'SellerPilot · ' + (result?.error || 'Chưa liên kết được. Thử lại.');
        Object.assign(notice.style, hint.style);
        document.documentElement.append(notice); setTimeout(() => notice.remove(), 4500);
      }).catch(() => {});
    }, {capture: true, signal: controller.signal});
    return {document_id: documentId};
  }
  function read(target) {
    allowed();
    checkTarget(target);
    const root = document.querySelector('main,[role=main]') || document.body;
    // Export only recognized business columns. Never send body text, buyer details,
    // input values, arbitrary columns, hidden state, scripts or query parameters.
    const column = /^(sản phẩm|tên sản phẩm|product|product name|sku|mã sku|giá|giá bán|price|tồn kho|kho hàng|stock|số lượng|quantity|đã bán|sold|mã đơn hàng|mã đơn|order id|trạng thái|status|tổng tiền|tổng đơn hàng|total)$/i;
    const tables = [...root.querySelectorAll('table,[role=table],[role=grid]')].filter(visible).slice(0, 8)
      .map(table => {
        const rows = [...table.querySelectorAll('tr,[role=row]')].filter(visible);
        const cells = row => [...row.querySelectorAll('th,td,[role=columnheader],[role=cell],[role=gridcell]')];
        const headerIndex = rows.findIndex(row => row.querySelector('th,[role=columnheader]'));
        if (headerIndex < 0) return [];
        const headers = cells(rows[headerIndex]).map(text);
        const indexes = headers.flatMap((name, index) => column.test(name) ? [index] : []);
        if (!indexes.length) return [];
        return [indexes.map(index => headers[index]), ...rows.slice(headerIndex + 1, headerIndex + 31).map(row => {
          const values = cells(row);
          return indexes.map(index => text(values[index]).slice(0, 200));
        })];
      }).filter(table => table.length);
    const metricLabels = /^(doanh số|doanh thu|revenue|đơn hàng|orders|lượt truy cập|visitors|product clicks|order conversion rate|tỷ lệ chuyển đổi|chờ lấy hàng|đã xử lý|sản phẩm bị tạm khóa)$/i;
    const scalar = /^(?:[₫đ]\s*)?\d[\d.,\s]*(?:%|[₫đ]|\s?[kmb])?$/i;
    const metrics = [];
    const occurrences = new Map();
    for (const el of root.querySelectorAll('span,div,p,dt')) {
      if ((el.textContent || '').length > 80) continue;
      if (!visible(el) || !metricLabels.test(text(el)) || [...el.children].some(child => metricLabels.test(text(child)))) continue;
      const key = text(el).toLowerCase();
      occurrences.set(key, (occurrences.get(key) || 0) + 1);
      // Immediate siblings only. Ambiguous or unsupported layouts produce no metric.
      const values = [el.nextElementSibling, ...[...(el.parentElement?.children || [])].filter(child => child !== el)]
        .filter(child => child && visible(child) && scalar.test(text(child))).map(text);
      const unique = [...new Set(values)];
      if (unique.length === 1 && !metrics.some(row => row.label.toLowerCase() === text(el).toLowerCase())) metrics.push({label: text(el), value: unique[0]});
    }
    const fields = [...root.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => visible(el) && !['hidden', 'password'].includes(el.type) && Object.values(patterns).some(pattern => pattern.test(label(el))))
      .map(el => ({label: label(el), type: el.type || 'richtext', disabled: Boolean(el.disabled || el.readOnly)})).slice(0, 80);
    const data = {account_label: target.label, metrics: metrics.filter(row => occurrences.get(row.label.toLowerCase()) === 1).slice(0, 20), tables, fields,
      coverage: 'visible_page_only', period: 'unverified', account_verification: 'user_selected_browser_label'};
    // Drop whole rows until valid JSON fits the backend contract; never truncate JSON.
    while (JSON.stringify(data).length > 15000 && data.tables.length) {
      const last = data.tables[data.tables.length - 1];
      if (last.length > 2) last.pop(); else data.tables.pop();
    }
    readContext = {token: pageContext(), url: location.href};
    return {document_id: documentId, page_context: readContext.token, snapshot: {url: pageUrl(), title: 'Shopee · Kênh Người Bán',
      captured_at: new Date().toISOString(), text: JSON.stringify(data), scope: 'visible_page'},
      metrics: data.metrics, tables: data.tables, fields, target, bindings: [...bindings.keys()]};
  }
  const patterns = {name: /^(?:tên sản phẩm|product name)\s*[:*]?$/i,
    description: /^(?:mô tả(?: sản phẩm)?|product description)\s*[:*]?$/i,
    price_vnd: /^(?:giá(?: bán)?|price)\s*[:*]?$/i, stock: /^(?:kho hàng|tồn kho|số lượng|stock)\s*[:*]?$/i};
  function find(field) {
    const bound = bindings.get(field);
    if (bound?.isConnected && !bound.disabled && !bound.readOnly && (field === 'images' || visible(bound))) return bound;
    if (!patterns[field]) return null;
    const matches = [...document.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => editable(el) && visible(el) && !el.disabled && !el.readOnly && !['password', 'hidden', 'file'].includes(el.type) && patterns[field].test(label(el)));
    return matches.length === 1 ? matches[0] : null;
  }
  function arm(field) {
    if (!['name', 'description', 'price_vnd', 'stock', 'images'].includes(field)) throw Error('Trường không hỗ trợ.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    document.addEventListener('click', event => {
      const el = event.composedPath().find(el => field === 'images' ? el instanceof HTMLInputElement && el.type === 'file' : editable(el));
      if (!el || (el instanceof HTMLInputElement && !['text', 'number', 'tel', 'search', 'file'].includes(el.type)) || el.disabled || el.readOnly) return;
      event.preventDefault(); event.stopImmediatePropagation();
      bindings.set(field, el); clearTimeout(timer); controller.abort();
      const outline = el.style.outline;
      el.style.outline = '2px solid #ee4d2d'; setTimeout(() => {el.style.outline = outline;}, 1200);
      void chrome.runtime.sendMessage({kind: 'binding_complete', field}).catch(() => {});
    }, {capture: true, signal: controller.signal});
    return {armed: field};
  }
  async function fill(payload) {
    allowed();
    checkTarget(payload.target);
    const checkPage = () => {
      if (payload.document_id !== documentId || payload.url !== pageUrl() || !readContext
        || payload.page_context !== readContext.token || payload.page_context !== pageContext() || readContext.url !== location.href)
        throw Error('Trang đã đổi. Đọc lại trang trước khi điền.');
      checkTarget(payload.target);
    };
    checkPage();
    if (!payload.draft || Object.keys(payload.draft).some(key => !patterns[key])) throw Error('Bản nháp không hợp lệ.');
    const report = [];
    for (const [field, value] of Object.entries(payload.draft)) {
      checkPage();
      if (value === null || value === undefined) continue;
      if (typeof value !== 'string' && typeof value !== 'number') throw Error('Giá trị không hợp lệ.');
      const el = find(field);
      if (!el) {report.push({field, status: 'unmapped'}); continue;}
      const content = String(value);
      if (el.maxLength > -1 && content.length > el.maxLength) {report.push({field, status: 'too_long'}); continue;}
      el.focus();
      if (el.isContentEditable) {
        el.textContent = content;
      } else {
        const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, content);
      }
      el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
      el.dispatchEvent(new Event('change', {bubbles: true})); el.blur();
      await new Promise(resolve => setTimeout(resolve, 120));
      const current = find(field);
      const actual = current?.isContentEditable ? current.textContent : current?.value;
      report.push({field, status: actual === content ? 'filled' : 'not_retained'});
    }
    // Never click Save/Publish, dispatch submit or claim server-side persistence.
    return {report, submitted: false, images: 'manual', category: 'manual', variants: 'manual'};
  }
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id) return;
    Promise.resolve().then(() => {
      if (message.kind === 'read') return read(message.target);
      if (message.kind === 'target_status') {
        let matches = false;
        try {allowed(); checkTarget(message.target); matches = true;} catch { /* A label is not an API identity. */ }
        return {target_matches: matches, document_id: documentId, page_context: pageContext()};
      }
      if (message.kind === 'select_target') {allowed(); return selectTarget(message.nonce);}
      if (message.kind === 'bind') {allowed(); return arm(message.field);}
      if (message.kind === 'fill') return fill(message);
      throw Error('Thao tác không hỗ trợ.');
    }).then(data => reply({ok: true, data}), error => reply({ok: false, error: error.message}));
    return true;
  });
})();
