// Runs in Chrome's isolated world for TikTok Shop Seller Center.
// No cookies, private APIs or page-script eval.
(() => {
  if (globalThis.__sellerPilotTikTokContent) return;
  globalThis.__sellerPilotTikTokContent = true;
  const ALLOWED_ORIGINS = ['https://seller-vn.tiktok.com', 'https://seller.tiktok.com'];
  const ORIGIN = ALLOWED_ORIGINS.includes(location.origin) ? location.origin : 'https://seller-vn.tiktok.com';
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
  const text = el => (typeof el === 'string' ? el : el?.innerText || el?.textContent || '').normalize('NFC').trim().replace(/\s+/g, ' ');
  const label = el => {
    const parts = [
      el.getAttribute('aria-label'),
      el.getAttribute('placeholder'),
      el.getAttribute('name'),
      el.id,
      el.title,
      ...(el.labels ? [...el.labels].map(text) : [])
    ];
    let prev = el.previousElementSibling;
    while (prev && parts.length < 5) {
      const t = text(prev);
      if (t && t.length <= 80) parts.push(t);
      prev = prev.previousElementSibling;
    }
    const formItem = el.closest('.arco-form-item, [class*="form-item"], [class*="formItem"], .form-group, .form-row');
    if (formItem) {
      const labelEl = formItem.querySelector('.arco-form-item-label, [class*="form-item-label"], [class*="label-col"], [class*="label-item"], label, [class*="label"]');
      if (labelEl && !labelEl.contains(el)) {
        const t = text(labelEl);
        if (t && t.length <= 100) parts.push(t);
      }
    } else {
      const cell = el.closest('td, [role="cell"], [role="gridcell"], [class*="table-cell"], [class*="table-td"]');
      if (cell) {
        const row = cell.closest('tr, [role="row"], [class*="table-row"], [class*="table-tr"]');
        const table = row?.closest('table, [role="table"], [role="grid"], [class*="arco-table"]');
        if (row && table) {
          const cells = [...row.children];
          const cellIndex = cells.indexOf(cell);
          const headerRow = table.querySelector('thead tr, [role="rowheader"], [class*="table-header"] tr, [class*="table-thead"] tr');
          if (headerRow && cellIndex >= 0) {
            const headerCells = [...headerRow.children];
            if (headerCells[cellIndex]) {
              const t = text(headerCells[cellIndex]);
              if (t && t.length <= 80) parts.push(t);
            }
          }
        }
      }
      let parent = el.parentElement;
      for (let depth = 0; !el.labels?.length && !el.getAttribute('aria-label') && depth < 4 && parent && parent !== document.body && !parent.matches('form,main,[role=main]'); depth++) {
        const labelEl = parent.querySelector('label, [class*="label"], [class*="title"]');
        if (labelEl && labelEl !== el && !labelEl.contains(el)) {
          const t = text(labelEl);
          if (t && t.length <= 80) {
            parts.push(t);
            break;
          }
        }
        parent = parent.parentElement;
      }
    }
    if (el instanceof HTMLTextAreaElement || el.isContentEditable) {
      const section = el.closest('section, [class*="card"], [class*="section"], [class*="panel"], [class*="module"]');
      if (section) {
        const heading = section.querySelector('h1, h2, h3, h4, [class*="title"], [class*="header"]');
        if (heading && !heading.contains(el)) {
          const t = text(heading);
          if (t && t.length <= 80) parts.push(t);
        }
      }
    }
    return parts.filter(Boolean).map(text).filter(Boolean).join(' ').slice(0, 300);
  };
  const allowed = () => {
    if (!ALLOWED_ORIGINS.includes(location.origin)) throw Error('Chỉ hỗ trợ Kênh Người Bán TikTok Shop (seller-vn.tiktok.com).');
    if ([...document.querySelectorAll('input[type=password]')].some(visible)) throw Error('Bạn đăng nhập TikTok Shop trước nhé.');
  };
  const pageUrl = () => location.origin + location.pathname;
  const identityNodes = () => [...document.querySelectorAll('span,a,button,div,strong')]
    .filter(el => !editable(el) && !el.closest('main,[role=main],form,table')
      && (el.textContent || '').trim().length <= 160 && visible(el)
      && text(el).length > 0 && text(el).length <= 80
      && ![...el.children].some(child => visible(child) && text(child) === text(el)));
  function autoDetectTarget() {
    const candidates = [...document.querySelectorAll('header [class*="shop-name"],header [class*="account"],header [class*="arco-dropdown"],header [class*="user-name"],header [class*="user-info"],header [class*="shop-info"],[class*="header"] [class*="user-name"],[class*="header"] [class*="shop-name"]')]
      .filter(el => visible(el) && identityNodes().includes(el));
    const labels = [...new Set(candidates.map(text))];
    return labels.length === 1 ? labels[0] : null;
  }
  function checkTarget(target) {
    if (!target?.label || typeof target.label !== 'string') throw Error('Chọn tài khoản TikTok Shop trước khi đọc dữ liệu hoặc điền form.');
    if (identityNodes().filter(el => text(el) === target.label).length !== 1)
      throw Error('Không xác nhận được tài khoản đã chọn trên trang này. Kiểm tra đăng nhập rồi chọn lại tài khoản.');
  }
  function selectTarget(nonce) {
    if (typeof nonce !== 'string' || !/^[a-z0-9-]{36}$/i.test(nonce)) throw Error('Yêu cầu chọn tài khoản không hợp lệ.');
    selection?.abort();
    const controller = selection = new AbortController();
    const hint = document.createElement('div');
    hint.textContent = 'SellerPilot · Bấm tên tài khoản/shop trên thanh đầu trang TikTok Shop để liên kết. Esc để hủy.';
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
    sku: /^(?:sku|mã sku|sku sản phẩm|sku phân loại|mã người bán|seller sku)$/i,
    stock: /^(?:tồn kho|kho hàng|kho|số lượng tồn|stock|inventory|available stock|quantity)$/i,
    price: /^(?:giá|giá bán|giá bán lẻ|price|retail price)$/i, sold: /^(?:đã bán|sold|sales)$/i,
    order: /^(?:mã đơn(?: hàng)?|order id|order number)$/i,
    status: /^(?:trạng thái|status)$/i, total: /^(?:tổng tiền|tổng đơn hàng|total)$/i,
  };
  const resourceLabels = {
    dashboard: /^(?:trang chủ|tổng quan|dashboard|home)$/i,
    products: /^(?:quản lý sản phẩm|tất cả sản phẩm|danh sách sản phẩm|all products|manage products)$/i,
    orders: /^(?:quản lý đơn hàng|tất cả đơn hàng|danh sách đơn hàng|all orders|manage orders)$/i,
  };
  const navRoot = 'nav,aside,[role=navigation],[class*="sidebar"],[class*="menu"]';
  function readOnlyControl(el) {
    if (el.closest('form') && el.type === 'submit') return false;
    const href = el.getAttribute('href');
    if (!href) return true;
    try {
      const url = new URL(href, location.href);
      return ALLOWED_ORIGINS.includes(url.origin) && !url.username && !url.password
        && !/logout|signout|delete|remove|publish|submit/i.test(url.pathname);
    } catch {return false;}
  }
  function navigationNodes(key) {
    return [...document.querySelectorAll(key === 'dashboard' ? navRoot + ',header,[class*="header"]' : navRoot)].flatMap(root => [...root.querySelectorAll('a,button,[role=menuitem],[role=link],[class*="menu-item"],[class*="menu__item"],[class*="sidebar-item"]')])
      .filter((el, index, nodes) => nodes.indexOf(el) === index && visible(el) && readOnlyControl(el) && !el.closest('form') && (
        resourceLabels[key].test(text(el)) || key === 'dashboard' && el.getAttribute('href')
          && /tiktok|seller center/i.test(text(el) || el.getAttribute('aria-label') || el.querySelector('img')?.alt || '')
          && new URL(el.getAttribute('href'), location.href).pathname === '/'
        || key === 'orders' && /^tất cả$/i.test(text(el))));
  }
  function pagination() {
    const roots = [...document.querySelectorAll('[class*="pagination"],[class*="pager"],[class*="arco-pagination"],[aria-label*="pagination" i],[aria-label*="phân trang" i]')].filter(visible);
    const controls = roots.flatMap(root => [...root.querySelectorAll('button,a,[role=button],[class*="arco-pagination-item"]')]).filter((el, i, all) => all.indexOf(el) === i && visible(el) && readOnlyControl(el));
    const next = controls.filter(el => /^(?:next(?: page)?|trang (?:sau|tiếp)|tiếp theo)$/i.test(el.getAttribute('aria-label') || el.title || text(el))
      || /(?:pagination[^\s]*(?:__|-)(?:next|right)|(?:^|\s)(?:next|btn-next|arco-pagination-item-next)(?:\s|$))/.test(el.className || ''));
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
    const root = document.querySelector('main,[role=main],[class*="main-content"]') || document.body;
    const candidates = [...root.querySelectorAll('table,[role=table],[role=grid],[class*="table"],[class*="arco-table"]')].filter(visible);
    const tables = [], inventory = [], parsed = new Set();
    let rowsTruncated = false;
    for (const table of candidates) {
      if ([...parsed].some(parent => parent.contains(table))) continue;
      const rows = [...table.querySelectorAll('tr,[role=row],[class*="table__row"],[class*="table-row"],[class*="arco-table-tr"]')].filter(visible);
      const cells = row => [...row.querySelectorAll('th,td,[role=columnheader],[role=cell],[role=gridcell],[class*="table__cell"],[class*="table-cell"],[class*="arco-table-th"],[class*="arco-table-td"]')]
        .filter((el, index, all) => !all.some(other => other !== el && other.contains(el)));
      const headerIndex = rows.findIndex(row => row.querySelector('th,[role=columnheader],[class*="arco-table-th"]') || /header|thead/.test(row.className || '') || row.closest('thead,[class*="thead"],[class*="table__header"]'));
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
          const name = text(nameCell).slice(0, 200);
          const sku = text(values[types.indexOf('sku')]).slice(0, 100) || null;
          inventory.push({key: sku ? 'sku:' + sku : 'unverified:' + JSON.stringify(valuesText),
            identity_verified: Boolean(sku), name, sku, stock: text(values[types.indexOf('stock')])});
        }
        return valuesText;
      })]);
    }
    const metricLabels = /^(?:doanh số|doanh thu|revenue|đơn hàng|orders|lượt xem|visitors|tỷ lệ chuyển đổi|chờ xác nhận|chờ vận chuyển|đã xử lý|sản phẩm bị đóng băng)$/i;
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
      : tables.some(table => table[0].some(h => columnTypes.order.test(h))) ? 'orders' : null;
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
    return {document_id: documentId, page_context: readContext.token, snapshot: {url: pageUrl(), title: 'TikTok Shop · Kênh Người Bán',
      captured_at: new Date().toISOString(), text: JSON.stringify(data), scope: 'visible_page'}, metrics: data.metrics,
      tables, inventory, fields, target, navigation: {}, pagination: paging, loading, empty_confirmed, list_kind, filtered, rows_truncated: rowsTruncated,
      bindings: [...bindings.keys()]};
  }
  const patterns = {
    name: /(?:tên sản phẩm|tên hàng hóa|tên mặt hàng|product name)/i,
    description: /(?:mô tả(?: sản phẩm)?|chi tiết sản phẩm|product description)/i,
    price_vnd: /(?:giá(?: bán)?|giá bán lẻ|retail price|đơn giá|price)/i,
    stock: /(?:kho hàng|tồn kho|số lượng|số lượng tồn|stock|quantity|hàng có sẵn)/i
  };
  function findAll(field) {
    const bound = bindings.get(field);
    if (bound?.isConnected && !bound.disabled && !bound.readOnly && (field === 'images' || visible(bound))) return [bound];
    if (!patterns[field]) return [];
    return [...document.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => editable(el) && visible(el) && !el.disabled && !el.readOnly && !['password', 'hidden', 'file', 'search'].includes(el.type)
        && !el.closest('header, nav, aside, [role="navigation"], [class*="header"], [class*="sidebar"]')
        && patterns[field].test(label(el)));
  }
  function find(field) {
    return findAll(field)[0] || null;
  }
  function arm(field) {
    if (!['name', 'description', 'price_vnd', 'stock', 'images'].includes(field)) throw Error('Trường không hỗ trợ.');
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 30000);
    document.addEventListener('click', event => {
      const el = event.composedPath().find(node => {
        if (node instanceof HTMLElement) {
          if (field === 'images') return node instanceof HTMLInputElement && node.type === 'file';
          return editable(node) || Boolean(node.querySelector?.('input,textarea,[contenteditable=true]'));
        }
        return false;
      });
      if (!el) return;
      const target = editable(el) ? el : el.querySelector('input,textarea,[contenteditable=true]');
      if (!target || target.disabled || target.readOnly) return;
      event.preventDefault(); event.stopImmediatePropagation();
      bindings.set(field, target); clearTimeout(timer); controller.abort();
      const outline = target.style.outline;
      target.style.outline = '2px solid #fe2c55'; setTimeout(() => {target.style.outline = outline;}, 1200);
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
    const ALLOWED_KEYS = ['name', 'description', 'price_vnd', 'stock', 'images', 'category_name', 'brand', 'origin', 'weight_g'];
    if (!payload.draft || Object.keys(payload.draft).some(key => !ALLOWED_KEYS.includes(key))) throw Error('Bản nháp không hợp lệ.');

    const written = new Map();
    function simulateClick(el) {
      checkPage();
      if (!el) return;
      el.scrollIntoView?.({behavior: 'instant', block: 'center'});
      const rect = el.getBoundingClientRect();
      const clientX = rect.left + rect.width / 2;
      const clientY = rect.top + rect.height / 2;
      const downOpts = {bubbles: true, cancelable: true, view: window, button: 0, buttons: 1, clientX, clientY, pointerId: 1, pointerType: 'mouse', isPrimary: true};
      const upOpts = {bubbles: true, cancelable: true, view: window, button: 0, buttons: 0, clientX, clientY, pointerId: 1, pointerType: 'mouse', isPrimary: true};
      el.dispatchEvent(new PointerEvent('pointerdown', downOpts));
      el.dispatchEvent(new MouseEvent('mousedown', downOpts));
      el.focus?.();
      el.dispatchEvent(new PointerEvent('pointerup', upOpts));
      el.dispatchEvent(new MouseEvent('mouseup', upOpts));
      el.dispatchEvent(new MouseEvent('click', upOpts));
      el.click?.();
    }

    function triggerClick(el) {
      if (!el) return;
      simulateClick(el);
      try {
        const key = Object.keys(el).find(k => k.startsWith('__reactProps') || k.startsWith('__reactEvents') || k.startsWith('__reactFiber'));
        if (key && el[key]?.onClick) {
          el[key].onClick({
            bubbles: true,
            cancelable: true,
            preventDefault: () => {},
            stopPropagation: () => {},
            target: el,
            currentTarget: el
          });
        }
      } catch { /* ignore */ }
    }

    async function waitForField(matcher, maxWaitMs = 4000) {
      const start = Date.now();
      while (Date.now() - start < maxWaitMs) {
        const el = findFieldContainer(matcher);
        if (el) return el;
        await new Promise(r => setTimeout(r, 200));
      }
      return null;
    }

    function setInputValue(input, val) {
      checkPage();
      if (!input || input.disabled || input.readOnly) return;
      const content = String(val);

      if (input.isContentEditable) {
        input.focus?.();
        try {
          document.execCommand('selectAll', false, null);
          if (!document.execCommand('insertText', false, content)) {
            input.textContent = content;
          }
        } catch {
          input.textContent = content;
        }
        input.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
        input.dispatchEvent(new Event('input', {bubbles: true}));
        input.dispatchEvent(new Event('change', {bubbles: true}));
        return;
      }

      input.focus?.();
      input.select?.();
      const tracker = input._valueTracker;
      if (tracker) tracker.setValue('');

      if (input instanceof HTMLInputElement || input instanceof HTMLTextAreaElement) {
        const proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
        const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
        if (setter) {
          try {
            setter.call(input, content);
          } catch {
            input.value = content;
          }
        } else {
          input.value = content;
        }
      } else {
        try {
          input.value = content;
        } catch {
          input.textContent = content;
        }
      }

      input.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
      input.dispatchEvent(new Event('input', {bubbles: true}));
      input.dispatchEvent(new Event('change', {bubbles: true}));
      input.dispatchEvent(new Event('blur', {bubbles: true}));
    }

    function findFieldContainer(matcher) {
      const allElements = [...document.querySelectorAll('label, .arco-form-item-label, [class*="label"], [class*="title"], dt, span, div')]
        .filter(el => {
          if (!visible(el)) return false;
          const t = text(el);
          return t.length >= 2 && t.length <= 60 && matcher.test(t) && !el.querySelector('input, select, textarea');
        });
      allElements.sort((a, b) => text(a).length - text(b).length);
      const best = allElements[0];
      if (!best) return null;
      return best.closest('.arco-form-item, [class*="form-item"], [class*="formItem"], .arco-col, [class*="field"], [class*="attribute"]') || best.parentElement;
    }

    function getColumnHeaderText(cell) {
      try {
        const row = cell.closest('tr, [role="row"], .arco-table-tr, [class*="table-tr"], [class*="row"]');
        const table = row?.closest('table, [role="table"], [role="grid"], .arco-table, [class*="table"]');
        if (!row || !table) return '';
        const cells = [...row.children].filter(visible);
        const idx = cells.indexOf(cell);
        if (idx < 0) return '';
        const headerRow = table.querySelector('thead tr, [role="rowheader"], .arco-table-header .arco-table-tr, .arco-table-header [role="row"], [class*="header"] [role="row"], [class*="header"] tr, [class*="thead"] [class*="tr"]');
        if (headerRow) {
          const headerCells = [...headerRow.children].filter(visible);
          if (headerCells[idx]) return text(headerCells[idx]);
        }
        const headers = [...table.querySelectorAll('th, [role="columnheader"], .arco-table-th, [class*="th"]')].filter(visible);
        if (headers[idx]) return text(headers[idx]);
      } catch { /* ignore */ }
      return '';
    }

    function fillSalesAndPricing(draft) {
      for (const field of ['price_vnd', 'stock']) {
        const value = draft[field];
        if (!Number.isInteger(value) || (field === 'stock' ? value < 0 : value < 1000)) continue;
        const inputs = findAll(field);
        if (inputs.length !== 1) continue; // Multi-variant prices require explicit field mapping.
        setInputValue(inputs[0], value);
        written.set(field, {element: inputs[0], value: String(value)});
      }
    }

    function fillShippingInfo(draft) {
      if (!Number.isInteger(draft.weight_g) || draft.weight_g <= 0) return;
      const inputs = [...document.querySelectorAll('input')].filter(el => visible(el) && !el.disabled && !el.readOnly && /trọng lượng|weight/i.test(label(el)));
      if (inputs.length !== 1) return;
      const unit = text(inputs[0].closest('.arco-form-item, [class*="form-item"]'));
      // Do not confuse grams with kilograms or invent package dimensions.
      if (/\bkg\b/i.test(unit) || !/\b(?:g|gam|gram)\b/i.test(unit)) return;
      setInputValue(inputs[0], draft.weight_g);
    }

    // 1. Tự động tải ảnh lên nếu có
    let imagesUploaded = false;
    if (Array.isArray(payload.draft.images) && payload.draft.images.length > 0) {
      try {
        const fileInputs = [...document.querySelectorAll('input[type="file"]')];
        const imageInput = fileInputs.find(el => el.accept?.includes('image') || el.closest('[class*="upload"], [class*="image"], [class*="picture"]')) || fileInputs[0];
        if (imageInput) {
          const dt = new DataTransfer();
          for (let i = 0; i < payload.draft.images.length && i < 9; i++) {
            const dataUrl = payload.draft.images[i];
            if (!dataUrl || typeof dataUrl !== 'string') continue;
            const res = await fetch(dataUrl);
            const blob = await res.blob();
            const mime = blob.type || 'image/jpeg';
            const ext = mime.includes('png') ? 'png' : 'jpg';
            const file = new File([blob], `product_${i + 1}.${ext}`, {type: mime});
            dt.items.add(file);
          }
          if (dt.files.length > 0) {
            checkPage();
          imageInput.files = dt.files;
            imageInput.dispatchEvent(new Event('input', {bubbles: true}));
            imageInput.dispatchEvent(new Event('change', {bubbles: true}));
            imagesUploaded = true;
          }
        }
      } catch { /* fallback manual */ }
    }

    // 2. Điền tên sản phẩm và mô tả
    const report = [];
    for (const [field, value] of Object.entries(payload.draft)) {
      if (field !== 'name' && field !== 'description') continue;
      checkPage();
      if (value === null || value === undefined) continue;
      const elements = findAll(field);
      const content = String(value);
      if (elements.length !== 1) continue;
      const el = elements[0];
      if (el.maxLength > -1 && content.length > el.maxLength) continue;
      setInputValue(el, content);
      written.set(field, {element: el, value: content});
    }

    // 3. Tự động chọn Hạng mục khớp nhất từ các đề xuất của TikTok Shop (chờ API trả về đề xuất)
    function scoreCategoryMatch(candidateText, draftName, draftDesc, targetCat) {
      if (!candidateText || typeof candidateText !== 'string') return -1;
      const clean = str => (str || '')
        .toLowerCase()
        .normalize('NFC')
        .replace(/[^a-z0-9àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ\s]/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();

      const candNorm = clean(candidateText);
      const nameNorm = clean(draftName);
      const descNorm = clean(draftDesc);
      const targetNorm = clean(targetCat);
      if (!candNorm) return -1;

      let score = 0;
      if (targetNorm && targetNorm.length > 2 && candNorm.includes(targetNorm)) {
        score += 60;
      }

      const stopWords = new Set(['và', 'cho', 'các', 'của', 'trong', 'với', 'loại', 'khác', 'dành', 'phụ', 'đề', 'xuất', 'áp', 'dụng']);
      const candTokens = candNorm.split(' ').filter(w => w.length >= 2 && !stopWords.has(w));
      const nameTokens = new Set(nameNorm.split(' ').filter(w => w.length >= 2 && !stopWords.has(w)));
      const descTokens = new Set(descNorm.split(' ').filter(w => w.length >= 2 && !stopWords.has(w)));

      for (const token of candTokens) {
        if (nameTokens.has(token)) score += 6;
        else if (descTokens.has(token)) score += 2;
      }

      for (let i = 0; i < candTokens.length - 1; i++) {
        const bi = candTokens[i] + ' ' + candTokens[i + 1];
        if (nameNorm.includes(bi)) score += 12;
        else if (descNorm.includes(bi)) score += 4;
        if (i < candTokens.length - 2) {
          const tri = bi + ' ' + candTokens[i + 2];
          if (nameNorm.includes(tri)) score += 20;
          else if (descNorm.includes(tri)) score += 6;
        }
      }
      return score;
    }

    async function selectBestCategory(draft, maxWaitMs = 8000) {
      const startTime = Date.now();
      let bestItem = null;

      while (Date.now() - startTime < maxWaitMs) {
        // A. Tìm các nút "Áp dụng" trên toàn bộ trang
        const applyElements = [...document.querySelectorAll('*')].filter(el => {
          if (!visible(el)) return false;
          if (el.children.length > 0) return false;
          const t = text(el).trim();
          return /^(?:áp dụng|apply)$/i.test(t);
        });

        const rows = [];
        for (const applyEl of applyElements) {
          const btn = applyEl.closest('button, [role="button"], a, [class*="btn"]') || applyEl;
          let row = btn.parentElement;
          for (let depth = 0; depth < 6 && row && row !== document.body; depth++) {
            const rt = text(row);
            // Gợi ý ngành hàng trên TikTok Shop bắt buộc chứa dấu '>' hoặc '›' hoặc '/'
            if (rt.includes('>') || rt.includes('›') || (rt.includes('/') && !rt.includes('giá'))) {
              const catPath = rt.replace(/áp dụng|apply/gi, '').trim();
              rows.push({applyEl, btn, row, text: catPath});
              break;
            }
            row = row.parentElement;
          }
        }

        if (rows.length > 0) {
          let maxScore = -1;
          for (const item of rows) {
            const sc = scoreCategoryMatch(item.text, draft.name, draft.description, draft.category_name);
            if (sc > maxScore) {
              maxScore = sc;
              bestItem = item;
            }
          }
          const ranked = rows.map(item => ({item, score: scoreCategoryMatch(item.text, draft.name, draft.description, draft.category_name)})).sort((a,b) => b.score - a.score);
          if (!draft.category_name || ranked[0]?.score < 60 || ranked[1]?.score === ranked[0]?.score) bestItem = null;
          break;
        }

        // B. Nếu chưa hiện đề xuất, tìm nút trigger mở đề xuất (ví dụ: "✨ Đề xuất", "+ 3 đề xuất")
        const trigger = [...document.querySelectorAll('button, [role="button"], span, div, a')].find(el => {
          if (!visible(el)) return false;
          const t = text(el);
          return (/\d+\s*đề xuất/i.test(t) || /✨\s*đề xuất/i.test(t)) && !el.closest('[class*="popover"], [class*="popup"]');
        });
        if (trigger) {
          triggerClick(trigger);
          await new Promise(r => setTimeout(r, 400));
        }

        await new Promise(r => setTimeout(r, 300));
      }

      if (bestItem) {
        triggerClick(bestItem.btn);
        if (bestItem.applyEl !== bestItem.btn) triggerClick(bestItem.applyEl);
        await new Promise(r => setTimeout(r, 600));

        // Nếu popover đề xuất vẫn còn mở sau 600ms, thử click trực tiếp dòng chứa text
        const stillOpen = visible(bestItem.applyEl) || visible(bestItem.btn);
        if (stillOpen) {
          triggerClick(bestItem.row);
          await new Promise(r => setTimeout(r, 600));
        }

        return true;
      }
      return false;
    }

    let categorySelected = false;
    try {
      if (payload.draft.category_name) categorySelected = await selectBestCategory(payload.draft, 8000);
    } catch { /* fallback */ }

    // Đợi TikTok Shop tải phần Thuộc tính phụ thuộc (Thương hiệu, Xuất xứ)
    await new Promise(resolve => setTimeout(resolve, 800));

    // 4. Tự động xử lý Thuộc tính bắt buộc (Thương hiệu, Quốc gia xuất xứ, và các thuộc tính khác)
    async function selectDropdownOption(container, searchTerms) {
      if (!container) return false;
      container.scrollIntoView?.({behavior: 'instant', block: 'center'});
      await new Promise(r => setTimeout(r, 100));

      const curValEl = container.querySelector('.arco-select-view-value, [class*="view-value"]');
      const curVal = text(curValEl);
      if (searchTerms.some(term => String(term).trim().toLocaleLowerCase() === curVal.trim().toLocaleLowerCase())) {
        for (const term of searchTerms) {
          if (new RegExp(term, 'i').test(curVal)) return true;
        }
      }

      const selectView = container.querySelector('.arco-select-view, .arco-select, [role="combobox"]');
      const arrow = container.querySelector('.arco-select-suffix, svg, [class*="arrow"]');
      const trigger = arrow || selectView || container;

      // Click một lần duy nhất để mở popup dropdown
      triggerClick(trigger);
      await new Promise(r => setTimeout(r, 450));

      const findOption = () => {
        const candidates = [...document.querySelectorAll('.arco-select-option, [role="option"], .arco-trigger-popup div, .arco-select-popup div, [class*="option"], li')]
          .filter(visible);
        for (const term of searchTerms) {
          const matching = candidates.filter(el => text(el).trim().toLocaleLowerCase() === String(term).trim().toLocaleLowerCase());
          const match = matching.length === 1 ? matching[0] : null;
          if (match) return match;
        }
        return null;
      };

      let opt = findOption();

      if (!opt) {
        const searchInput = container.querySelector('input.arco-select-view-input, input:not([type="hidden"])') ||
                            document.querySelector('.arco-trigger-popup input, .arco-select-popup input');
        if (searchInput) {
          for (const term of searchTerms) {
            setInputValue(searchInput, term);
            await new Promise(r => setTimeout(r, 450));
            opt = findOption();
            if (opt) break;
          }
        }
      }

      if (opt) {
        triggerClick(opt);
        await new Promise(r => setTimeout(r, 300));
        return true;
      }

      document.dispatchEvent(new KeyboardEvent('keydown', {key: 'Escape', bubbles: true}));
      return false;
    }

    try {
      if (payload.draft.brand) {
        const container = await waitForField(/thương hiệu|brand|nhãn hiệu/i, 1500);
        await selectDropdownOption(container, [payload.draft.brand]);
      }
      if (payload.draft.origin) {
        const container = await waitForField(/quốc gia xuất xứ|xuất xứ|country of origin/i, 1500);
        await selectDropdownOption(container, [payload.draft.origin]);
      }
    } catch (error) { checkPage(); }

    // 5. Điền thông tin bán hàng (Giá, Tồn kho) và Vận chuyển (Trọng lượng, Kích thước)
    // Khối này chỉ hiển thị đầy đủ sau khi Hạng mục và Thuộc tính đã được kích hoạt
    await new Promise(resolve => setTimeout(resolve, 800));
    fillSalesAndPricing(payload.draft);
    fillShippingInfo(payload.draft);

    await new Promise(resolve => setTimeout(resolve, 250));
    for (const inp of document.querySelectorAll('input')) {
      if (inp.value && visible(inp)) inp.dispatchEvent(new Event('blur', {bubbles: true}));
    }

    // 5. Quét chính xác toàn bộ các trường bắt buộc vẫn còn thiếu trên trang
    await new Promise(resolve => setTimeout(resolve, 350));
    const unfilledRequired = [];
    try {
      const isRequiredElement = el => {
        const t = text(el);
        if (t.includes('*')) return true;
        if (el.className && typeof el.className === 'string' && el.className.includes('required')) return true;
        if (Boolean(el.querySelector?.('.arco-form-item-label-required-symbol, [class*="required"]'))) return true;
        try {
          const before = window.getComputedStyle(el, '::before').getPropertyValue('content');
          if (before && before.includes('*')) return true;
        } catch { /* ignore */ }
        return false;
      };

      const allContainers = [...document.querySelectorAll('.arco-form-item, [class*="form-item"], [class*="formItem"], .arco-col, [class*="attribute-item"]')].filter(visible);

      for (const container of allContainers) {
        const lblEl = container.querySelector('.arco-form-item-label, label, [class*="label"], [class*="title"], dt');
        const isReq = isRequiredElement(container) || (lblEl && isRequiredElement(lblEl));
        if (!isReq) continue;

        let rawLabel = text(lblEl || container).split('\n')[0].replace(/[*?:()]/g, '').trim();
        if (!rawLabel || rawLabel.length < 2 || rawLabel.length > 50) continue;
        if (/^(?:bắt buộc|thông tin cơ bản|chi tiết|thông tin bán hàng|vận chuyển|đề xuất)$/i.test(rawLabel)) continue;

        let isFilled = false;

        const viewVal = container.querySelector('.arco-select-view-value, .arco-cascader-view-value, [class*="view-value"]');
        if (viewVal) {
          const vt = text(viewVal);
          if (vt && !/chọn|select|vui lòng/i.test(vt)) isFilled = true;
        }

        if (!isFilled) {
          const inputs = [...container.querySelectorAll('input:not([type="hidden"]):not([type="password"]):not([type="file"]):not([type="checkbox"]):not([type="radio"]), textarea')];
          for (const input of inputs) {
            if (input.classList.contains('arco-select-view-input')) continue;
            const v = input.value?.trim();
            if (v && v.length > 0 && !/chọn|select/i.test(v)) {
              isFilled = true;
              break;
            }
          }
        }

        if (!isFilled) {
          const ce = container.querySelector('[contenteditable="true"]');
          if (ce && text(ce).trim().length > 0) isFilled = true;
        }

        if (!isFilled && /ảnh|hình ảnh|image/i.test(rawLabel)) {
          if (container.querySelectorAll('img, [class*="image-item"], [class*="upload-item"]').length > 0) isFilled = true;
        }

        const hasError = Boolean(container.querySelector('.arco-form-item-message, [class*="error"], [class*="danger"], [class*="explain"]'));
        if (hasError) isFilled = false;

        if (!isFilled) {
          rawLabel = rawLabel.replace(/\s*(?:chọn một|vui lòng chọn|đề xuất).*$/i, '').trim();
          if (rawLabel && rawLabel.length <= 60 && !unfilledRequired.includes(rawLabel)) {
            unfilledRequired.push(rawLabel);
          }
        }
      }

      // Kiểm tra trực tiếp các trường cốt lõi
      const catCheck = findFieldContainer(/hạng mục|ngành hàng|category/i);
      if (catCheck) {
        const cv = catCheck.querySelector('.arco-select-view-value, .arco-cascader-view-value, [class*="view-value"], input');
        const rawT = text(catCheck).replace(/^.*?hạng mục/i, '').replace(/\d+\s*đề xuất/gi, '').trim();
        const cvt = text(cv) || (cv instanceof HTMLInputElement ? cv.value : '') || rawT;
        if (!cvt || /^(?:vui lòng chọn|chọn một|chọn)$/i.test(cvt) || cvt.length < 3) {
          if (!unfilledRequired.includes('Hạng mục')) unfilledRequired.unshift('Hạng mục');
        }
      }

      const brandCheck = findFieldContainer(/thương hiệu|brand|nhãn hiệu/i);
      if (brandCheck) {
        const bv = brandCheck.querySelector('.arco-select-view-value, [class*="view-value"], input');
        const bvt = text(bv) || (bv instanceof HTMLInputElement ? bv.value : '');
        if (!bvt || /chọn|select|vui lòng/i.test(bvt)) {
          if (!unfilledRequired.includes('Thương hiệu')) unfilledRequired.push('Thương hiệu');
        }
      }

      const originCheck = findFieldContainer(/quốc gia xuất xứ|xuất xứ|country of origin/i);
      if (originCheck) {
        const ov = originCheck.querySelector('.arco-select-view-value, [class*="view-value"], input');
        const ovt = text(ov) || (ov instanceof HTMLInputElement ? ov.value : '');
        if (!ovt || /chọn|select|vui lòng/i.test(ovt)) {
          if (!unfilledRequired.includes('Quốc gia xuất xứ')) unfilledRequired.push('Quốc gia xuất xứ');
        }
      }

      const weightCheck = findFieldContainer(/trọng lượng kiện hàng|trọng lượng/i);
      if (weightCheck) {
        const wv = weightCheck.querySelector('input:not([type="hidden"])');
        const wvt = (wv?.value || '').trim();
        if (!wvt || wvt === '0') {
          if (!unfilledRequired.includes('Trọng lượng kiện hàng')) unfilledRequired.push('Trọng lượng kiện hàng');
        }
      }
    } catch { /* ignore */ }

    checkPage();
    for (const field of ['name', 'description', 'price_vnd', 'stock']) {
      const write = written.get(field);
      const retained = write?.element.isConnected && String(write.element.isContentEditable ? write.element.textContent : write.element.value).trim() === write.value.trim();
      report.push({field, status: !write ? 'unmapped' : retained ? 'filled' : 'not_retained'});
    }
    return {report, submitted: false, images: imagesUploaded ? 'auto' : 'manual', category: categorySelected ? 'auto' : 'manual', variants: 'manual', unfilled_required: unfilledRequired};
  }
  chrome.runtime.onMessage.addListener((message, sender, reply) => {
    if (sender.id !== chrome.runtime.id) return;
    Promise.resolve().then(() => {
      if (message.kind === 'read') return read(message.target);
      if (message.kind === 'target_status') {
        let matches = false;
        try {allowed(); checkTarget(message.target); matches = true;} catch { /* Ignore */ }
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
