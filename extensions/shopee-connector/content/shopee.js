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
  function autoDetectTarget() {
    const candidates = [...document.querySelectorAll('header [class*="user-name"],header [class*="shop-name"],header [class*="account-name"],[class*="header"] [class*="user-name"],[class*="header"] [class*="shop-name"]')]
      .filter(el => visible(el) && identityNodes().includes(el));
    const labels = [...new Set(candidates.map(text))];
    return labels.length === 1 ? labels[0] : null;
  }
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
  const columnTypes = {
    name: /^(?:sản phẩm|tên sản phẩm|thông tin sản phẩm|product|product name|product information)$/i,
    sku: /^(?:sku|mã sku|sku sản phẩm|sku phân loại|sku biến thể|seller sku)$/i,
    stock: /^(?:tồn kho|kho hàng|kho|stock|inventory|số lượng tồn|available stock)$/i,
    price: /^(?:giá|giá bán|price)$/i, sold: /^(?:đã bán|sold|sales)$/i,
    order: /^(?:mã đơn(?: hàng)?|order id|order number)$/i,
    status: /^(?:trạng thái|status)$/i, total: /^(?:tổng tiền|tổng đơn hàng|total)$/i,
  };
  const resourceLabels = {
    dashboard: /^(?:trang chủ|tổng quan|dashboard|home)$/i,
    products: /^(?:tất cả sản phẩm|quản lý sản phẩm|danh sách sản phẩm|all products|my products)$/i,
    orders: /^(?:tất cả đơn hàng|danh sách đơn hàng|đơn hàng|all orders|my orders)$/i,
  };
  const navRoot = 'nav,aside,[role=navigation],[class*="sidebar"]';
  function readOnlyControl(el) {
    if (el.closest('form') && el.type === 'submit') return false;
    const href = el.getAttribute('href');
    if (!href) return true;
    try {
      const url = new URL(href, location.href);
      return url.origin === ORIGIN && !url.username && !url.password
        && !/logout|signout|delete|remove|publish|submit/i.test(url.pathname);
    } catch {return false;}
  }
  function navigationNodes(key) {
    return [...document.querySelectorAll(key === 'dashboard' ? navRoot + ',header,[class*="header"]' : navRoot)].flatMap(root => [...root.querySelectorAll('a,button,[role=menuitem],[role=link],[class*="menu-item"],[class*="menu__item"],[class*="sidebar-item"]')])
      .filter((el, index, nodes) => nodes.indexOf(el) === index && visible(el) && readOnlyControl(el) && !el.closest('form') && (
        resourceLabels[key].test(text(el)) || key === 'dashboard' && el.getAttribute('href')
          && /shopee|kênh người bán/i.test(text(el) || el.getAttribute('aria-label') || el.querySelector('img')?.alt || '')
          && new URL(el.getAttribute('href'), location.href).pathname === '/'
        || key === 'orders' && /^tất cả$/i.test(text(el))
          && [...ancestors(el, 4)].some(parent => /quản lý đơn hàng/i.test(text(parent)) && text(parent).length < 500)));
  }
  function* ancestors(el, count) {let node = el.parentElement; while (node && count-- > 0) {yield node; node = node.parentElement;}}
  function navigation() {
    return Object.fromEntries(Object.keys(resourceLabels).map(key => {
      const urls = navigationNodes(key).flatMap(el => {
        const href = el.getAttribute('href'); if (!href) return [];
        try {
          const url = new URL(href, location.href);
          if (url.origin !== ORIGIN || url.username || url.password || /(?:logout|signout|delete|remove|publish|submit)/i.test(url.pathname)
            || [...url.searchParams.keys()].some(param => /token|secret|auth|password/i.test(param))) return [];
          url.hash = ''; return [url.href];
        } catch {return [];}
      });
      return [key, [...new Set(urls)].length === 1 ? urls[0] : null];
    }));
  }
  function pagination() {
    const roots = [...document.querySelectorAll('[class*="pagination"],[class*="pager"],[aria-label*="pagination" i],[aria-label*="phân trang" i]')].filter(visible);
    const controls = roots.flatMap(root => [...root.querySelectorAll('button,a,[role=button]')]).filter((el, i, all) => all.indexOf(el) === i && visible(el) && readOnlyControl(el));
    const next = controls.filter(el => /^(?:next(?: page)?|trang (?:sau|tiếp)|tiếp theo)$/i.test(el.getAttribute('aria-label') || el.title || text(el))
      || /(?:pagination[^\s]*(?:__|-)(?:next|right)|(?:^|\s)(?:next|btn-next)(?:\s|$))/.test(el.className || ''));
    const disabled = el => Boolean(el.disabled || el.getAttribute('aria-disabled') === 'true' || /(?:^|[\s_-])disabled(?:[\s_-]|$)/.test(el.className || ''));
    const selected = roots.flatMap(root => [...root.querySelectorAll('[aria-current=page],[class*=active],[class*=current],[class*=selected]')])
      .filter(el => visible(el) && /^\d+$/.test(text(el))).map(el => Number(text(el)));
    const current = [...new Set(selected)].length === 1 ? selected[0] : null;
    const nextControl = next.find(el => !disabled(el)) || next[0];
    return {current, recognized: Boolean(roots.length && next.length), has_next: Boolean(nextControl && !disabled(nextControl)),
      at_last: Boolean(next.length && next.every(disabled)), control: nextControl,
      first_control: controls.find(el => !disabled(el) && (text(el) === '1' || /^(?:first page|trang đầu)$/i.test(el.getAttribute('aria-label') || el.title || '')))};
  }
  function read(target) {
    allowed(); checkTarget(target);
    const root = document.querySelector('main,[role=main]') || document.body;
    const candidates = [...root.querySelectorAll('table,[role=table],[role=grid],[class*="table"]')].filter(visible);
    const tables = [], inventory = [], parsed = new Set();
    let rowsTruncated = false;
    for (const table of candidates) {
      if ([...parsed].some(parent => parent.contains(table))) continue;
      const rows = [...table.querySelectorAll('tr,[role=row],[class*="table__row"],[class*="table-row"]')].filter(visible);
      const cells = row => [...row.querySelectorAll('th,td,[role=columnheader],[role=cell],[role=gridcell],[class*="table__cell"],[class*="table-cell"]')]
        .filter((el, index, all) => !all.some(other => other !== el && other.contains(el)));
      const headerIndex = rows.findIndex(row => row.querySelector('th,[role=columnheader]') || /header|thead/.test(row.className || '') || row.closest('thead,[class*="thead"],[class*="table__header"]'));
      if (headerIndex < 0) continue;
      const headers = cells(rows[headerIndex]).map(cell => text(cell).replace(/[:*?]/g, '').trim());
      const types = headers.map(header => Object.entries(columnTypes).find(([, pattern]) => pattern.test(header))?.[0] || null);
      const indexes = types.flatMap((type, index) => type ? [index] : []);
      if (!indexes.length) continue;
      parsed.add(table);
      const allBodyRows = rows.slice(headerIndex + 1).filter(row => !row.closest('thead,[class*="thead"],[class*="table__header"]')
        && !rows.some(other => other !== row && other.contains(row)));
      rowsTruncated ||= allBodyRows.length > 500;
      const bodyRows = allBodyRows.slice(0, 500);
      tables.push([indexes.map(index => headers[index]), ...bodyRows.map(row => {
        const values = cells(row);
        const valuesText = indexes.map(index => text(values[index]).slice(0, 200));
        if (types.includes('name') && types.includes('stock')) {
          const nameCell = values[types.indexOf('name')];
          const links = [...(nameCell?.querySelectorAll('a[href]') || [])];
          let productId = null;
          for (const link of links) {
            try {
              const url = new URL(link.href, ORIGIN);
              if (url.origin !== ORIGIN) continue;
              const id = url.searchParams.get('product_id') || url.searchParams.get('item_id') || url.pathname.match(/\/(?:product|item)\/(\d+)(?:\/|$)/)?.[1];
              if (id && /^\d+$/.test(id)) {productId = id; break;}
            } catch { /* An unrecognized link is not a product identity. */ }
          }
          const name = text(links.find(el => text(el) && text(el).length <= 200) || nameCell).slice(0, 200);
          const sku = text(values[types.indexOf('sku')]).slice(0, 100) || text(nameCell).match(/(?:SKU|Mã SKU)\s*:\s*([^\s]+)/i)?.[1] || null;
          inventory.push({key: sku ? 'sku:' + sku : productId ? 'product:' + productId : 'unverified:' + JSON.stringify(valuesText),
            identity_verified: Boolean(sku || productId), name, sku, stock: text(values[types.indexOf('stock')])});
        }
        return valuesText;
      })]);
    }
    const metricLabels = /^(?:doanh số|doanh thu|revenue|đơn hàng|orders|lượt truy cập|visitors|product clicks|order conversion rate|tỷ lệ chuyển đổi|chờ xác nhận|chờ lấy hàng|đã xử lý|sản phẩm bị tạm khóa)$/i;
    const scalar = /^(?:[₫đ]\s*)?\d[\d.,\s]*(?:%|[₫đ]|\s?[kmb])?$/i;
    const metrics = [], occurrences = new Map();
    for (const el of root.querySelectorAll('span,div,p,dt,h3,h4')) {
      if ((el.textContent || '').length > 80 || !visible(el) || !metricLabels.test(text(el)) || [...el.children].some(child => metricLabels.test(text(child)))) continue;
      const key = text(el).toLowerCase(); occurrences.set(key, (occurrences.get(key) || 0) + 1);
      const siblings = [el.nextElementSibling, ...[...(el.parentElement?.children || [])].filter(child => child !== el)];
      const values = siblings.filter(child => child && visible(child) && scalar.test(text(child))).map(text);
      const unique = [...new Set(values)];
      if (unique.length === 1) metrics.push({label: text(el), value: unique[0]});
    }
    const fields = [...root.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => visible(el) && !['hidden', 'password'].includes(el.type) && Object.values(patterns).some(pattern => pattern.test(label(el))))
      .map(el => ({label: label(el), type: el.type || 'richtext', disabled: Boolean(el.disabled || el.readOnly)})).slice(0, 80);
    const list_kind = inventory.length || tables.some(table => table[0].some(h => columnTypes.name.test(h))) ? 'products'
      : tables.some(table => table[0].some(h => columnTypes.order.test(h))) ? 'orders'
      : [...root.querySelectorAll('h1,h2,[role=heading]')].some(el => resourceLabels.products.test(text(el))) ? 'products'
      : [...root.querySelectorAll('h1,h2,[role=heading]')].some(el => resourceLabels.orders.test(text(el))) ? 'orders' : null;
    const empty_confirmed = Boolean(list_kind && [...root.querySelectorAll('p,span,div')].some(el => visible(el) && /^(?:(?:không có|chưa có|không tìm thấy) (?:sản phẩm|đơn hàng)(?: nào)?|no products(?: found)?|no orders(?: found)?)(?:[.!])?$/i.test(text(el))));
    const filtered = [...root.querySelectorAll('input')].some(el => visible(el) && (el.type === 'search' || /tìm kiếm|search/i.test(label(el))) && el.value.trim());
    const data = {account_label: target.label, metrics: metrics.filter(row => occurrences.get(row.label.toLowerCase()) === 1).slice(0, 20),
      tables: structuredClone(tables), fields, coverage: 'visible_page_only', period: 'unverified', account_verification: 'user_selected_browser_label'};
    while (JSON.stringify(data).length > 15000 && data.tables.length) {
      const last = data.tables[data.tables.length - 1]; if (last.length > 2) last.pop(); else data.tables.pop();
    }
    const paging = pagination(); delete paging.control; delete paging.first_control;
    const loading = [...root.querySelectorAll('[aria-busy=true],[role=progressbar]')].some(visible);
    readContext = {token: pageContext(), url: location.href};
    return {document_id: documentId, page_context: readContext.token, snapshot: {url: pageUrl(), title: 'Shopee · Kênh Người Bán',
      captured_at: new Date().toISOString(), text: JSON.stringify(data), scope: 'visible_page'}, metrics: data.metrics,
      tables, inventory, fields, target, navigation: navigation(), pagination: paging, loading, empty_confirmed, list_kind, filtered, rows_truncated: rowsTruncated,
      bindings: [...bindings.keys()]};
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
      if (message.kind === 'navigate_section') {
        allowed(); checkTarget(message.target);
        if (!resourceLabels[message.resource]) throw Error('Mục dữ liệu không hỗ trợ.');
        const nodes = navigationNodes(message.resource);
        if (!nodes.length) throw Error('Không tìm thấy mục ' + message.resource + ' trong menu Shopee.');
        nodes[0].click(); return {navigated: true};
      }
      if (['next_page', 'first_page'].includes(message.kind)) {
        allowed(); checkTarget(message.target);
        if (message.document_id !== documentId || message.page_context !== pageContext()) throw Error('Trang đã đổi trước khi chuyển trang.');
        const paging = pagination();
        if (message.kind === 'first_page') {
          if (!paging.first_control) throw Error('Không xác nhận được nút trang đầu.');
          paging.first_control.click(); return {navigated: true};
        }
        if (!paging.recognized || !paging.has_next || !paging.control) throw Error('Không xác nhận được nút trang tiếp theo.');
        paging.control.click(); return {navigated: true};
      }
      if (message.kind === 'target_status') {
        let matches = false;
        try {allowed(); checkTarget(message.target); matches = true;} catch { /* A label is not an API identity. */ }
        return {target_matches: matches, document_id: documentId, page_context: pageContext()};
      }
      if (message.kind === 'auto_detect_target') {
        allowed();
        const label = autoDetectTarget();
        return {label, document_id: documentId};
      }
      if (message.kind === 'select_target') {allowed(); return selectTarget(message.nonce);}
      if (message.kind === 'bind') {allowed(); return arm(message.field);}
      if (message.kind === 'fill') return fill(message);
      throw Error('Thao tác không hỗ trợ.');
    }).then(data => reply({ok: true, data}), error => reply({ok: false, error: error.message}));
    return true;
  });
})();
