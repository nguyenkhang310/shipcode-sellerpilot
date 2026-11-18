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
  const text = el => (typeof el?.innerText === 'string' ? el.innerText : el?.textContent || '').normalize('NFC').trim().replace(/\s+/g, ' ');
  const label = el => {
    let lbl = el.getAttribute('aria-label') || [...(el.labels || [])].map(text).join(' ');
    if (!lbl || /^(?:nhập vào|input|0|[₫đ]|vnd)$/i.test(lbl.trim())) {
      const formItem = el.closest('.eds-form-item, .shopee-form-item, [class*="form-item"], [class*="form-group"], [class*="form_item"], tr, [role="row"]');
      if (formItem) {
        const labelEl = formItem.querySelector('.eds-form-item__label, .shopee-form-item__label, [class*="form-item__label"], [class*="label"], [class*="title"], th');
        if (labelEl) lbl = text(labelEl);
      }
    }
    if (!lbl) lbl = el.getAttribute('placeholder') || '';
    return lbl.replace(/\([^)]*\)/g, '').replace(/[:*?]/g, '').trim().slice(0, 200);
  };
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
  function accountLabels() {
    const identities = identityNodes();
    const candidates = [...document.querySelectorAll('header [class*="user-name"],header [class*="shop-name"],header [class*="account-name"],[class*="header"] [class*="user-name"],[class*="header"] [class*="shop-name"]')]
      .filter(el => visible(el) && identities.includes(el));
    return [...new Set(candidates.map(text))];
  }
  function autoDetectTarget() {
    const labels = accountLabels();
    return labels.length === 1 ? labels[0] : null;
  }
  function checkTarget(target) {
    if (!target?.label || typeof target.label !== 'string') throw Error('Chọn tài khoản Shopee trước khi đọc dữ liệu hoặc điền form.');
    const labels = accountLabels();
    if (labels.length === 1 && labels[0] === target.label) return;
    const matches = labels.length ? 0 : identityNodes().filter(el => text(el) === target.label).length;
    if (matches !== 1) {
      throw Object.assign(Error('Chưa xác minh được tài khoản trên trang này. Chờ trang tải xong hoặc kiểm tra tên shop.'),
        {code: labels.length ? 'target_mismatch' : 'target_unverified'});
    }
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
  const cleanHeader = str => (str || '')
    .replace(/\([^)]*\)/g, '')
    .replace(/[^a-zA-Z0-9\sàáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđĐ]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
  const columnTypes = {
    name: /^(?:sản phẩm|tên sản phẩm|thông tin sản phẩm|product|product name|product information)(?:\s*\(.*?\))?$/i,
    sku: /^(?:sku|mã sku|sku sản phẩm|sku phân loại|sku biến thể|seller sku)(?:\s*\(.*?\))?$/i,
    stock: /^(?:tồn kho|kho hàng|kho|stock|inventory|số lượng tồn|available stock)(?:\s*\(.*?\))?$/i,
    price: /^(?:giá|giá bán|price)(?:\s*\(.*?\))?$/i, sold: /^(?:đã bán|sold|sales|hiệu suất)(?:\s*\(.*?\))?$/i,
    order: /^(?:mã đơn(?: hàng)?|order id|order number)(?:\s*\(.*?\))?$/i,
    status: /^(?:trạng thái|status)(?:\s*\(.*?\))?$/i, total: /^(?:tổng tiền|tổng đơn hàng|total)(?:\s*\(.*?\))?$/i,
  };
  const resourceLabels = {
    dashboard: /^(?:trang chủ|tổng quan|dashboard|home)$/i,
    products: /^(?:sản phẩm|tất cả sản phẩm|quản lý sản phẩm|danh sách sản phẩm|all products|my products)$/i,
    orders: /^(?:đơn hàng|tất cả đơn hàng|quản lý đơn hàng|danh sách đơn hàng|all orders|my orders)$/i,
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
    const candidates = [...root.querySelectorAll('table,[role=table],[role=grid],[class*="table"],[class*="product-list"],[class*="item-list"]')].filter(visible);
    const tables = [], inventory = [], parsed = new Set();
    let rowsTruncated = false;
    const rowSelector = 'tr,[role=row],[class*="table__row"],[class*="table-row"],[class*="header-row"],[class*="body-row"],[class*="table__header-row"],[class*="table__body-row"],[class*="eds-table__row"],[class*="item-wrap"],[class*="product-item"]';
    const cellSelector = 'th,td,[role=columnheader],[role=cell],[role=gridcell],[class*="table__cell"],[class*="table-cell"],[class*="header-cell"],[class*="body-cell"],[class*="table__header-cell"],[class*="table__body-cell"],[class*="eds-table__cell"]';
    for (const table of candidates) {
      if ([...parsed].some(parent => parent.contains(table))) continue;
      const rows = [...table.querySelectorAll(rowSelector)].filter(visible);
      const cells = row => {
        const found = [...row.querySelectorAll(cellSelector)].filter((el, index, all) => !all.some(other => other !== el && other.contains(el)));
        return found.length ? found : [...row.children].filter(visible);
      };
      let headerIndex = rows.findIndex(row => row.querySelector('th,[role=columnheader]') || /header|thead/.test(row.className || '') || row.closest('thead,[class*="thead"],[class*="table__header"],[class*="header-row"]'));
      if (headerIndex < 0 && rows.length > 0) {
        const row0Cells = cells(rows[0]).map(c => cleanHeader(text(c)));
        if (row0Cells.some(h => Object.values(columnTypes).some(p => p.test(h)))) {
          headerIndex = 0;
        }
      }
      if (headerIndex < 0) continue;
      const headers = cells(rows[headerIndex]).map(cell => cleanHeader(text(cell)));
      const types = headers.map(header => Object.entries(columnTypes).find(([, pattern]) => pattern.test(header))?.[0] || null);
      const indexes = types.flatMap((type, index) => type ? [index] : []);
      if (!indexes.length) continue;
      parsed.add(table);
      const allBodyRows = rows.slice(headerIndex + 1).filter(row => !row.closest('thead,[class*="thead"],[class*="table__header"],[class*="header-row"]')
        && !rows.some(other => other !== row && other.contains(row)));
      rowsTruncated ||= allBodyRows.length > 500;
      const bodyRows = allBodyRows.slice(0, 500);
      tables.push([indexes.map(index => headers[index]), ...bodyRows.map(row => {
        const values = cells(row);
        const valuesText = indexes.map(index => text(values[index]).slice(0, 200));
        if (types.includes('name')) {
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
          const sku = (types.includes('sku') ? text(values[types.indexOf('sku')]).slice(0, 100) : '') || text(nameCell).match(/(?:SKU|Mã SKU)\s*:\s*([^\s]+)/i)?.[1] || null;
          const stock = types.includes('stock') ? text(values[types.indexOf('stock')]) : (types.includes('price') ? text(values[types.indexOf('price')]) : '');
          inventory.push({key: sku ? 'sku:' + sku : productId ? 'product:' + productId : 'unverified:' + JSON.stringify(valuesText),
            identity_verified: Boolean(sku || productId), name, sku, stock});
        }
        return valuesText;
      })]);
    }
    // Direct support for Shopee Product List DOM (.product-variation-item)
    const variationItems = [...document.querySelectorAll('.product-variation-item, [class*="product-variation-item"]')].filter(visible);
    if (variationItems.length > 0 && (inventory.length === 0 || !tables.some(t => t.length > 1 && t[0].some(h => columnTypes.name.test(h))))) {
      const domProducts = [];
      const tableData = [['Tên sản phẩm', 'Giá', 'Kho hàng', 'Hiệu suất']];
      for (const item of variationItems) {
        const itemCells = [...item.querySelectorAll('.product-variation-padding, [class*="product-variation-padding"]')].filter(visible);
        const cellList = itemCells.length >= 3 ? itemCells : [...item.children].filter(visible);
        if (cellList.length >= 3) {
          const rawName = text(cellList[0]);
          const name = rawName.replace(/SKU sản phẩm:.*$/i, '').replace(/ID Sản phẩm:.*$/i, '').trim() || rawName;
          const sku = rawName.match(/SKU sản phẩm:\s*([^\s-]+)/i)?.[1] || null;
          const productId = rawName.match(/ID Sản phẩm:\s*(\d+)/i)?.[1] || null;
          const price = text(cellList[1]).trim();
          const stock = text(cellList[2]).trim();
          const sold = cellList[3] ? text(cellList[3]).trim() : '';
          tableData.push([name, price, stock, sold]);
          domProducts.push({
            key: sku ? 'sku:' + sku : productId ? 'product:' + productId : 'unverified:' + name,
            identity_verified: Boolean(sku || productId),
            name,
            sku,
            stock
          });
        }
      }
      if (domProducts.length > 0) {
        // Remove empty or 1-row product tables that lacked body rows
        for (let i = tables.length - 1; i >= 0; i--) {
          if (tables[i].length <= 1 && tables[i][0]?.some(h => columnTypes.name.test(h))) {
            tables.splice(i, 1);
          }
        }
        tables.push(tableData);
        inventory.push(...domProducts);
      }
    }
    const metricLabels = /^(?:doanh số|doanh thu|revenue|đơn hàng|orders|lượt truy cập|visitors|product clicks|order conversion rate|tỷ lệ chuyển đổi|chờ xác nhận|chờ lấy hàng|đã xử lý|sản phẩm bị tạm khóa|đơn trả hàng\/hoàn tiền\/huỷ)$/i;
    const scalar = /^(?:[₫đ]\s*)?\d[\d.,\s]*(?:%|[₫đ]|\s?[kmb])?$/i;
    const metrics = [], occurrences = new Map();
    for (const el of root.querySelectorAll('span,div,p,dt,h3,h4')) {
      const t = text(el);
      if (t.length > 80 || !visible(el)) continue;
      const combined = t.match(/^(\d[\d.,\s]*)\s+(.+)$/);
      if (combined && metricLabels.test(combined[2].trim())) {
        const key = combined[2].trim().toLowerCase();
        occurrences.set(key, (occurrences.get(key) || 0) + 1);
        metrics.push({label: combined[2].trim(), value: combined[1].trim()});
        continue;
      }
      if (!metricLabels.test(t) || [...el.children].some(child => metricLabels.test(text(child)))) continue;
      const key = t.toLowerCase(); occurrences.set(key, (occurrences.get(key) || 0) + 1);
      const siblings = [el.nextElementSibling, ...[...(el.parentElement?.children || [])].filter(child => child !== el)];
      const values = siblings.filter(child => child && visible(child) && scalar.test(text(child))).map(text);
      const unique = [...new Set(values)];
      if (unique.length === 1) metrics.push({label: t, value: unique[0]});
    }
    const fields = [...root.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => visible(el) && !['hidden', 'password'].includes(el.type) && Object.values(patterns).some(pattern => pattern.test(label(el))))
      .map(el => ({label: label(el), type: el.type || 'richtext', disabled: Boolean(el.disabled || el.readOnly)})).slice(0, 80);
    const list_kind = inventory.length || tables.some(table => table[0].some(h => columnTypes.name.test(h))) ? 'products'
      : tables.some(table => table[0].some(h => columnTypes.order.test(h))) ? 'orders'
      : [...root.querySelectorAll('h1,h2,[role=heading]')].some(el => resourceLabels.products.test(text(el))) ? 'products'
      : [...root.querySelectorAll('h1,h2,[role=heading]')].some(el => resourceLabels.orders.test(text(el))) ? 'orders'
      : location.pathname.includes('/product') ? 'products'
      : (location.pathname.includes('/order') || location.pathname.includes('/sale')) ? 'orders' : null;
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
  const patterns = {
    name: /^(?:tên sản phẩm|product name)\s*[:*]?$/i,
    description: /^(?:mô tả(?: sản phẩm)?|product description)\s*[:*]?$/i,
    price_vnd: /^(?:giá(?: bán)?|price)\s*[:*]?$/i,
    stock: /^(?:kho hàng|tồn kho|số lượng|stock)\s*[:*]?$/i,
    weight_g: /^(?:cân nặng(?: sau khi đóng gói)?|trọng lượng|khối lượng|weight)\s*[:*]?$/i,
    brand: /^(?:thương hiệu|brand)\s*[:*]?$/i,
    origin: /^(?:xuất xứ|quốc gia xuất xứ|origin)\s*[:*]?$/i,
  };
  function find(field) {
    const bound = bindings.get(field);
    if (bound?.isConnected && !bound.disabled && !bound.readOnly && (field === 'images' || visible(bound))) return bound;
    if (!patterns[field]) return null;
    const matches = [...document.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => editable(el) && visible(el) && !el.disabled && !el.readOnly && !['password', 'hidden', 'file'].includes(el.type) && patterns[field].test(label(el)));
    return matches.length === 1 ? matches[0] : null;
  }
  function arm(field) {
    if (!['name', 'description', 'price_vnd', 'stock', 'images', 'weight_g', 'brand', 'origin'].includes(field)) throw Error('Trường không hỗ trợ.');
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
  function scanRequiredFields() {
    const isProductForm = location.href.includes('/product/new') || location.href.includes('/portal/product/new')
      || location.href.includes('/portal/product/detail') || location.href.includes('/product/edit');
    if (!isProductForm) return { is_product_form: false, total_required: 0, missing_count: 0, missing_fields: [], items: [] };

    const items = [];
    const missing = [];
    const cleanLabel = str => (str || '').replace(/\([^)]*\)/g, '').replace(/[*:\s]+/g, ' ').trim();

    // 1. Scan form items on Shopee
    const allFormItems = [...document.querySelectorAll('.eds-form-item, .shopee-form-item, [class*="form-item"], [class*="form-group"]')].filter(visible);

    for (const item of allFormItems) {
      const labelEl = item.querySelector('.eds-form-item__label, .shopee-form-item__label, [class*="form-item__label"], [class*="label"], [class*="title"]');
      const rawLabel = labelEl ? text(labelEl) : '';
      const isRequired = item.classList.contains('is-required')
        || (item.className && typeof item.className === 'string' && item.className.includes('required'))
        || rawLabel.includes('*')
        || Boolean(item.querySelector('.eds-form-item__label-wrap--required, [class*="required-icon"], [class*="required-star"], [class*="is-required"]'));

      if (!isRequired && !rawLabel.includes('*')) continue;

      const labelName = cleanLabel(rawLabel);
      if (!labelName || labelName.length > 60) continue;
      if (items.some(i => i.label.toLowerCase() === labelName.toLowerCase())) continue;

      const inputEl = item.querySelector('input:not([type="hidden"]):not([type="file"]), textarea, [contenteditable="true"]');
      const selectEl = item.querySelector('.eds-select, [class*="select"], [class*="dropdown"]');
      const errorEl = item.querySelector('.eds-form-item__error, [class*="form-item__error"]');

      let val = '';
      if (inputEl) {
        val = inputEl.isContentEditable ? text(inputEl) : (inputEl.value || '').trim();
      } else if (selectEl) {
        val = text(selectEl).trim();
      }

      const suggestionBtns = [...item.querySelectorAll('button, [role="button"], .eds-tag, [class*="tag"], [class*="recommend"]')].filter(visible);
      const suggestions = suggestionBtns.map(text).filter(t => t && t.length < 40 && !/áp dụng|xóa|thêm|sửa|chọn/i.test(t)).slice(0, 5);

      const isSelectPlaceholder = /vui lòng chọn|vui lòng điền|chọn ngành hàng/i.test(val);
      const hasError = Boolean(errorEl && visible(errorEl));
      const isEmpty = !val || isSelectPlaceholder || (/cân nặng|trọng lượng/.test(labelName.toLowerCase()) && val === '0');

      const status = (isEmpty || hasError) ? 'missing' : 'filled';
      items.push({
        label: labelName,
        status,
        current_value: isSelectPlaceholder ? '' : val,
        suggestions
      });
      if (status === 'missing') missing.push(labelName);
    }

    // 2. Check core product fields
    const nameEl = find('name');
    if (nameEl && !items.some(i => i.label.toLowerCase().includes('tên sản phẩm'))) {
      const isMissing = !nameEl.value.trim();
      items.unshift({ label: 'Tên sản phẩm', status: isMissing ? 'missing' : 'filled', current_value: nameEl.value.trim(), suggestions: [] });
      if (isMissing && !missing.includes('Tên sản phẩm')) missing.unshift('Tên sản phẩm');
    }

    const priceEl = find('price_vnd');
    if (priceEl && !items.some(i => i.label.toLowerCase().includes('giá'))) {
      const isMissing = !priceEl.value.trim();
      items.push({ label: 'Giá bán', status: isMissing ? 'missing' : 'filled', current_value: priceEl.value.trim(), suggestions: [] });
      if (isMissing && !missing.includes('Giá bán')) missing.push('Giá bán');
    }

    const stockEl = find('stock');
    if (stockEl && !items.some(i => i.label.toLowerCase().includes('kho hàng') || i.label.toLowerCase().includes('tồn kho'))) {
      const isMissing = !stockEl.value.trim();
      items.push({ label: 'Kho hàng', status: isMissing ? 'missing' : 'filled', current_value: stockEl.value.trim(), suggestions: [] });
      if (isMissing && !missing.includes('Kho hàng')) missing.push('Kho hàng');
    }

    const weightEl = find('weight_g');
    if (weightEl && !items.some(i => i.label.toLowerCase().includes('cân nặng') || i.label.toLowerCase().includes('trọng lượng'))) {
      const isMissing = !weightEl.value.trim() || weightEl.value.trim() === '0';
      items.push({ label: 'Cân nặng', status: isMissing ? 'missing' : 'filled', current_value: weightEl.value.trim(), suggestions: [] });
      if (isMissing && !missing.includes('Cân nặng')) missing.push('Cân nặng');
    }

    const brandEl = [...document.querySelectorAll('.eds-form-item, [class*="form-item"]')].find(el => /thương hiệu/i.test(text(el)));
    if (brandEl && !items.some(i => i.label.toLowerCase().includes('thương hiệu'))) {
      const isMissing = /vui lòng chọn|vui lòng điền/i.test(text(brandEl));
      const btns = [...brandEl.querySelectorAll('button, [role="button"], [class*="tag"]')].filter(visible).map(text).filter(t => t && t.length < 40 && !/áp dụng|xóa/i.test(t)).slice(0, 5);
      items.push({ label: 'Thương hiệu', status: isMissing ? 'missing' : 'filled', current_value: isMissing ? '' : text(brandEl), suggestions: btns });
      if (isMissing && !missing.includes('Thương hiệu')) missing.push('Thương hiệu');
    }

    const catEl = [...document.querySelectorAll('.eds-form-item, [class*="form-item"]')].find(el => /ngành hàng|danh mục/i.test(text(el)));
    if (catEl && !items.some(i => i.label.toLowerCase().includes('ngành hàng'))) {
      const isMissing = /chọn ngành hàng|vui lòng chọn/i.test(text(catEl));
      items.push({ label: 'Ngành hàng', status: isMissing ? 'missing' : 'filled', current_value: isMissing ? '' : text(catEl), suggestions: [] });
      if (isMissing && !missing.includes('Ngành hàng')) missing.push('Ngành hàng');
    }

    return {
      is_product_form: true,
      total_required: items.length,
      missing_count: missing.length,
      missing_fields: missing,
      items
    };
  }
  function fillInputElement(el, content) {
    el.focus({preventScroll: true});
    if (el.isContentEditable) el.textContent = content;
    else {
      const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      Object.getOwnPropertyDescriptor(proto, 'value').set.call(el, content);
    }
    el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
    el.dispatchEvent(new Event('change', {bubbles: true})); el.blur();
  }
  async function uploadShopeeImages(images, checkPage) {
    if (!Array.isArray(images) || !images.length) return false;
    if (images.length > 6 || images.some(v => typeof v !== 'string' || !/^data:image\/(?:jpeg|png|webp);base64,/.test(v) || v.length > 1400000)
      || images.reduce((n, v) => n + v.length, 0) > 5000000) throw Error('Ảnh sản phẩm không hợp lệ.');
    const bound = bindings.get('images');
    const candidates = [...document.querySelectorAll('input[type=file]')].filter(el => !el.disabled && /image|jpg|jpeg|png/i.test(el.accept) && !/video/i.test(el.accept));
    const target = bound?.isConnected ? bound : candidates.length === 1 ? candidates[0] : null;
    if (!target || (!target.multiple && images.length > 1)) return false;
    const files = new DataTransfer();
    for (const [i, data] of images.entries()) {
      const blob = await (await fetch(data)).blob();
      checkPage();
      files.items.add(new File([blob], 'product-' + (i + 1) + (blob.type === 'image/png' ? '.png' : '.jpg'), {type: blob.type}));
    }
    checkPage(); target.files = files.files;
    // A single change event, no synthetic drop as well (which uploads twice).
    target.dispatchEvent(new Event('change', {bubbles: true}));
    return true; // handed to Shopee's uploader; server acceptance remains unverified
  }
  async function fillSelect(field, value, checkPage) {
    const normalize = v => text(v).toLocaleLowerCase('vi').replace(/\s+/g, ' ').trim();
    const wanted = String(value).normalize('NFC').toLocaleLowerCase('vi').trim();
    const equal = v => v === wanted || field === 'brand' && /^(?:no brand|không có thương hiệu|không thương hiệu)$/.test(wanted) && /^(?:no brand|không có thương hiệu|không thương hiệu)$/.test(v);
    const items = [...document.querySelectorAll('.eds-form-item, .shopee-form-item, .attribute-select-item, [class*="form-item"]')].filter(el => {
      const labelEl = el.querySelector('label, [class*="label"], [class*="title"]');
      return visible(el) && patterns[field].test(text(labelEl).replace(/[:*]/g, '').trim());
    });
    if (items.length !== 1) return false;
    const item = items[0], trigger = item.querySelector('[role=combobox], .eds-selector, .eds-select');
    const selected = () => [...item.querySelectorAll('[class*="selected"], [class*="selection"], [role=combobox]')].some(el => equal(normalize(el)));
    if (selected()) return true;
    if (!trigger) return false;
    checkPage(); trigger.click(); await new Promise(r => setTimeout(r, 120)); checkPage();
    const controls = trigger.getAttribute('aria-controls');
    const popups = controls ? [document.getElementById(controls)].filter(Boolean) : [...document.querySelectorAll('[role=listbox], .eds-select-dropdown, .eds-selector__dropdown')].filter(visible);
    if (popups.length !== 1) return false;
    const options = [...popups[0].querySelectorAll('[role=option], li, .eds-select-dropdown__item, .eds-selector__option')].filter(el => visible(el) && equal(normalize(el)));
    if (options.length !== 1) return false;
    checkPage(); options[0].click(); await new Promise(r => setTimeout(r, 120)); checkPage();
    return selected();
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
    const ALLOWED_FIELDS = ['name', 'description', 'price_vnd', 'stock', 'images', 'weight_g', 'brand', 'category_name', 'origin'];
    if (!payload.draft || Object.keys(payload.draft).some(key => !ALLOWED_FIELDS.includes(key))) throw Error('Bản nháp không hợp lệ.');
    const report = [];

    let imagesUploaded = false;
    if (Array.isArray(payload.draft.images) && payload.draft.images.length > 0) {
      imagesUploaded = await uploadShopeeImages(payload.draft.images, checkPage);
    }

    for (const [field, value] of Object.entries(payload.draft)) {
      if (field === 'images') continue;
      checkPage();
      if (value === null || value === undefined) continue;
      if (typeof value !== 'string' && typeof value !== 'number') throw Error('Giá trị không hợp lệ.');
      if (['brand', 'origin'].includes(field) && !find(field)) {
        const retained = await fillSelect(field, value, checkPage);
        report.push({field, status: retained ? 'filled' : 'unmapped'}); continue;
      }
      const el = find(field);
      if (!el) {report.push({field, status: 'unmapped'}); continue;}
      let content = String(value);
      if (field === 'weight_g') {
        const container = el.closest('.eds-form-item, [class*="form-item"], label') || el.parentElement;
        const unit = text(container);
        if (/\bkg\b/i.test(unit)) content = String(Number(value) / 1000);
        else if (!/\b(?:g|gr|gam|gram)\b/i.test(unit)) {report.push({field, status: 'unmapped'}); continue;}
      }
      if (el.maxLength > -1 && content.length > el.maxLength) {report.push({field, status: 'too_long'}); continue;}
      fillInputElement(el, content);
      await new Promise(resolve => setTimeout(resolve, 60));
      checkPage();
      const current = find(field);
      const actual = current?.isContentEditable ? (current.innerText || current.textContent) : current?.value;
      let retained = false;
      if (['price_vnd', 'stock', 'weight_g', 'weight'].includes(field)) {
        retained = String(actual ?? '').trim() === content.trim();
      } else {
        retained = String(actual || '').trim() === content.trim();
      }
      report.push({field, status: retained ? 'filled' : 'not_retained'});
    }

    // Identify required fields that are still missing or erroring on Shopee
    const scan = scanRequiredFields();
    const unfilledRequired = scan.missing_fields;

    // Never click Save/Publish, dispatch submit or claim server-side persistence.
    return {
      report,
      submitted: false,
      images: imagesUploaded ? 'handed_to_uploader' : 'manual',
      category: 'manual',
      variants: 'manual',
      unfilled_required: unfilledRequired,
      required_scan: scan
    };
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
        let matches = false, check = 'unverified';
        try {allowed(); checkTarget(message.target); matches = true; check = 'matched';}
        catch (error) {if (error.code === 'target_mismatch') check = 'mismatch';}
        return {target_matches: matches, target_check: check, document_id: documentId, page_context: pageContext()};
      }
      if (message.kind === 'auto_detect_target') {
        allowed();
        const label = autoDetectTarget();
        return {label, document_id: documentId};
      }
      if (message.kind === 'select_target') {allowed(); return selectTarget(message.nonce);}
      if (message.kind === 'bind') {allowed(); return arm(message.field);}
      if (message.kind === 'fill') return fill(message);
      if (message.kind === 'scan_required') {allowed(); checkTarget(message.target); return scanRequiredFields();}
      throw Error('Thao tác không hỗ trợ.');
    }).then(data => reply({ok: true, data}), error => reply({ok: false, error: error.message, code: error.code}));
    return true;
  });
  // Continuation is authorized and scoped in the worker; this page never reads
  // or executes a global pending draft from another shop/tab.
  let continuing = false;
  setInterval(async () => {
    if (continuing || !/^\/portal\/product\/new\/?$/.test(location.pathname)) return;
    continuing = true;
    try { await chrome.runtime.sendMessage({kind: 'autofill_continue'}); } catch { /* worker may be asleep */ }
    finally { continuing = false; }
  }, 1500);
})();
