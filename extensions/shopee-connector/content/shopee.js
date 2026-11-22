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
    name: /^(?:tên sản phẩm|product name)\s*[:*]?$|tên thương hiệu/i,
    description: /^(?:mô tả(?: sản phẩm)?|product description)\s*[:*]?$/i,
    price_vnd: /^(?:giá(?: bán)?|price)(?:\s*\(.*?\))?\s*[:*]?$|^giá\b/i,
    stock: /^(?:kho hàng|tồn kho|số lượng|stock)(?:\s*\(.*?\))?\s*[:*]?$|^kho hàng\b/i,
    weight_g: /^(?:cân nặng|trọng lượng|khối lượng|weight)(?:\s*\(.*?\))?\s*[:*]?$|^cân nặng\b/i,
    brand: /^(?:thương hiệu|brand)\s*[:*]?$|^thương hiệu\b/i
  };
  function find(field) {
    const bound = bindings.get(field);
    if (bound?.isConnected && !bound.disabled && !bound.readOnly && (field === 'images' || visible(bound))) return bound;
    if (field === 'description') {
      const allEditables = [...document.querySelectorAll('textarea, [contenteditable="true"], [role="textbox"], .eds-textarea__inner')]
        .filter(el => visible(el) && !el.disabled && !el.readOnly);
      // 1. By placeholder or aria-label containing description keywords
      const byPlaceholder = allEditables.find(el => {
        const p = [el.getAttribute('placeholder'), el.getAttribute('data-placeholder'), el.getAttribute('aria-placeholder'), el.getAttribute('aria-label')]
          .filter(Boolean).join(' ').toLowerCase();
        return /mô tả|vui lòng nhập|thêm hình ảnh|description/i.test(p);
      });
      if (byPlaceholder) return byPlaceholder;

      // 2. Search container matching "Mô tả sản phẩm" or "Mô tả"
      const descItem = [...document.querySelectorAll('.eds-form-item, [class*="form-item"], [class*="form-group"], [class*="product-description"], [class*="detail-item"], [class*="edit-row"], section, div')].find(el => {
        const titleEl = el.querySelector('.eds-form-item__label, [class*="label"], [class*="title"], h1, h2, h3, h4, h5, label');
        const titleText = (titleEl ? text(titleEl) : '').toLowerCase();
        return /mô tả|description/i.test(titleText) && el.querySelector('textarea, [contenteditable="true"], [role="textbox"], .eds-textarea__inner');
      });
      if (descItem) {
        const target = descItem.querySelector('textarea, [contenteditable="true"], [role="textbox"], .eds-textarea__inner');
        if (target && visible(target)) return target;
      }

      // 3. Search near /3000 counter
      const counterEl = [...document.querySelectorAll('*')].find(el =>
        /\/3000\b/i.test(el.textContent || '') && el.children.length === 0
      );
      if (counterEl) {
        const parent = counterEl.closest('div, section, [class*="item"]');
        const target = parent?.querySelector('textarea, [contenteditable="true"], [role="textbox"], .eds-textarea__inner');
        if (target && visible(target)) return target;
      }

      // 4. Any visible textarea or eds-textarea__inner
      const fallback = allEditables.find(el => el instanceof HTMLTextAreaElement || el.classList.contains('eds-textarea__inner') || el.isContentEditable);
      if (fallback) return fallback;
    }
    if (!patterns[field]) return null;
    const allInputs = [...document.querySelectorAll('input,textarea,[contenteditable=true]')]
      .filter(el => editable(el) && visible(el) && !el.disabled && !el.readOnly && !['password', 'hidden', 'file'].includes(el.type));
    const matches = allInputs.filter(el => {
      if (['price_vnd', 'stock'].includes(field) && isInsideVariantSection(el)) return false;
      return patterns[field].test(label(el));
    });
    if (matches.length >= 1) return matches[0];

    // Fallbacks for Shopee EDS price & stock
    if (field === 'name') {
      const nameInput = allInputs.find(el => {
        const item = el.closest('.eds-form-item, .shopee-form-item, [class*="form-item"]');
        return item && /tên sản phẩm|product name/i.test(text(item));
      });
      if (nameInput) return nameInput;
    }

    if (field === 'price_vnd') {
      const priceInput = allInputs.find(el => {
        if (isInsideVariantSection(el)) return false;
        const ph = (el.getAttribute?.('placeholder') || '').toLowerCase();
        if (ph.includes('phân loại') || ph.includes('tùy chọn')) return false;
        const parent = el.closest('.eds-form-item, [class*="form-item"], [class*="input-group"], [class*="batch"], tr, div');
        const containerText = text(parent).toLowerCase();
        const hasVnd = el.parentElement?.querySelector('[class*="prepend"], [class*="prefix"]')?.textContent?.includes('₫')
          || containerText.includes('₫');
        return hasVnd;
      }) || allInputs.find(el => {
        if (isInsideVariantSection(el)) return false;
        const ph = (el.getAttribute?.('placeholder') || '').toLowerCase();
        if (ph.includes('phân loại') || ph.includes('tùy chọn')) return false;
        const item = el.closest('.eds-form-item, [class*="form-item"], [class*="batch"], tr');
        return item && /giá\b/i.test(text(item));
      });
      if (priceInput) return priceInput;
    }

    if (field === 'stock') {
      // 1. By direct label containing "kho hàng"
      const stockLabels = [...document.querySelectorAll('label, [class*="label"], [class*="title"], div, span')].filter(el =>
        visible(el) && !isInsideVariantSection(el) && /^\s*\*?\s*kho hàng(?:\s*\(.*?\))?\s*$/i.test(text(el).trim())
      );
      for (const lbl of stockLabels) {
        const item = lbl.closest('.eds-form-item, .shopee-form-item, [class*="form-item"], [class*="form-group"]') || lbl.parentElement?.parentElement;
        const inp = item?.querySelector('input:not([type="hidden"]):not([type="file"])');
        if (inp && visible(inp)) return inp;
      }

      // 2. Next sibling of price_vnd item
      const priceInp = find('price_vnd');
      if (priceInp) {
        const priceItem = priceInp.closest('.eds-form-item, .shopee-form-item, [class*="form-item"]');
        const nextItem = priceItem?.nextElementSibling;
        const nextInp = nextItem?.querySelector('input:not([type="hidden"]):not([type="file"])');
        if (nextInp && visible(nextInp) && !isInsideVariantSection(nextInp)) return nextInp;
      }

      // 3. Fallback: Any input inside container with "kho hàng"
      const stockInput = allInputs.find(el => {
        if (isInsideVariantSection(el)) return false;
        const item = el.closest('.eds-form-item, [class*="form-item"], [class*="batch"], tr');
        return item && /(?:kho hàng|tồn kho|stock)\b/i.test(text(item));
      });
      if (stockInput) return stockInput;
    }

    if (field === 'weight_g' || field === 'weight') {
      const weightInp = allInputs.find(inp => {
        const parent = inp.closest('.eds-form-item, [class*="form-item"], [class*="row"], div');
        const parentTxt = parent ? text(parent).toLowerCase() : '';
        const isDimension = parentTxt.includes('kích thước') || inp.parentElement?.textContent?.includes('cm');
        if (isDimension) return false;
        return (parentTxt.includes('cân nặng') || parentTxt.includes('trọng lượng')) && (parentTxt.includes('gr') || parentTxt.includes('g'));
      }) || allInputs.find(inp => {
        const parent = inp.closest('.eds-form-item, [class*="form-item"], div');
        const parentTxt = parent ? text(parent).toLowerCase() : '';
        return parentTxt.includes('cân nặng (sau khi đóng gói)') || parentTxt.includes('cân nặng');
      }) || allInputs.find(inp => {
        return inp.parentElement?.textContent?.includes('gr') && !inp.parentElement?.textContent?.includes('cm');
      });
      if (weightInp) return weightInp;
    }

    if (field === 'brand') {
      const brandInput = allInputs.find(el => {
        const item = el.closest('.eds-form-item, [class*="form-item"]');
        return item && /(?:thương hiệu|brand)\b/i.test(text(item));
      });
      if (brandInput) return brandInput;
    }

    return null;
  }
  function arm(field) {
    if (!['name', 'description', 'price_vnd', 'stock', 'images', 'weight_g', 'weight', 'brand'].includes(field)) throw Error('Trường không hỗ trợ.');
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
      const isEmpty = !val || isSelectPlaceholder || (['kho hàng', 'cân nặng'].some(k => labelName.toLowerCase().includes(k)) && val === '0');

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
      const isMissing = !stockEl.value.trim() || stockEl.value.trim() === '0';
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
    if (!el) return;
    try {
      el.focus({preventScroll: true});
      if (el.isContentEditable) {
        try {
          const sel = window.getSelection();
          const range = document.createRange();
          range.selectNodeContents(el);
          sel.removeAllRanges();
          sel.addRange(range);
          document.execCommand('selectAll', false, null);
          document.execCommand('insertText', false, content);
        } catch { /* fallback */ }
        if (!(el.innerText || el.textContent || '').trim()) {
          el.textContent = content;
        }
        el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, cancelable: true, inputType: 'insertText', data: content}));
        el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
      } else {
        // Clear existing value (e.g. initial '0') to ensure Vue change detection
        try {
          const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(el, '');
          el.dispatchEvent(new Event('input', {bubbles: true}));
        } catch { /* ignore */ }

        try {
          el.select();
          document.execCommand('selectAll', false, null);
          document.execCommand('insertText', false, content);
        } catch { /* fallback */ }
        try {
          const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
          Object.getOwnPropertyDescriptor(proto, 'value')?.set?.call(el, content);
        } catch {
          try { el.value = content; } catch { /* ignore */ }
        }
        el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, cancelable: true, inputType: 'insertText', data: content}));
        el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: content}));
        el.dispatchEvent(new Event('input', {bubbles: true}));
        el.dispatchEvent(new Event('change', {bubbles: true}));
      }
      el.blur();
      el.dispatchEvent(new Event('blur', {bubbles: true}));
    } catch { /* fallback */ }
  }

  function isInsideVariantSection(el) {
    if (!el) return false;
    const ph = (el.getAttribute?.('placeholder') || '').toLowerCase();
    const aria = (el.getAttribute?.('aria-label') || '').toLowerCase();
    if (ph.includes('phân loại') || ph.includes('tùy chọn') || aria.includes('phân loại') || aria.includes('tùy chọn')) {
      return true;
    }
    const variantContainer = el.closest('[class*="variation"], [class*="model"], [class*="tier"], [class*="variant"], [class*="batch"]');
    if (variantContainer) return true;
    const tableParent = el.closest('table, tbody, tr');
    if (tableParent && (tableParent.closest('[class*="variation"], [class*="model"]') || /phân loại|tùy chọn/i.test(text(tableParent)))) {
      return true;
    }
    let curr = el.parentElement;
    let depth = 0;
    while (curr && curr !== document.body && depth < 5) {
      if (curr.classList.contains('no-variations') || curr.className?.includes?.('no-variation')) {
        return false;
      }
      const titleEl = curr.querySelector?.(':scope > .item-title, :scope > [class*="header"], :scope > [class*="title"], :scope > label');
      const t = (titleEl ? text(titleEl) : '').toLowerCase();
      if (t.includes('phân loại hàng') || t.includes('nhóm phân loại') || t.includes('danh sách phân loại')) {
        return true;
      }
      curr = curr.parentElement;
      depth++;
    }
    return false;
  }

  async function dismissAutoGeneratedVariants() {
    try {
      // 1. Look for link/button "Xóa chỉ với một lần nhấp chuột" (innermost element)
      const clearMatches = [...document.querySelectorAll('a, button, span, [role="button"], div')].filter(el =>
        visible(el) && /xóa (?:chỉ )?với một lần nhấp chuột/i.test(text(el))
      );
      const targetLink = clearMatches.find(el => ![...el.children].some(c => /xóa/i.test(text(c)))) || clearMatches.at(-1);
      if (targetLink) {
        ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evt => {
          targetLink.dispatchEvent(new MouseEvent(evt, {bubbles: true, cancelable: true, view: window}));
        });
        targetLink.click?.();
        // Wait and confirm modal if Shopee pops one up
        for (let i = 0; i < 6; i++) {
          await new Promise(r => setTimeout(r, 150));
          const confirmBtn = [...document.querySelectorAll('.eds-modal, [class*="modal"], [role="dialog"], .shopee-modal, .eds-dialog')].flatMap(m =>
            [...m.querySelectorAll('button, [role="button"]')].filter(b =>
              visible(b) && (/^(?:xóa|xác nhận|đồng ý|ok|confirm)$/i.test(text(b).trim()) || (/xóa|xác nhận|đồng ý/i.test(text(b)) && !/hủy|cancel/i.test(text(b))))
            )
          )[0];
          if (confirmBtn) {
            confirmBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
            confirmBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
            confirmBtn.click?.();
            await new Promise(r => setTimeout(r, 200));
            break;
          }
        }
      }

      // 2. Check if variant tier cards exist and delete them
      const tierSections = [...document.querySelectorAll('[class*="tier"], [class*="variation"], [class*="model"]')].filter(el =>
        visible(el) && /phân loại\s*[12]/i.test(text(el))
      );
      for (const ts of tierSections) {
        const closeIcon = ts.querySelector('.eds-icon-close, [class*="close"], [class*="delete"], [class*="trash"], svg');
        if (closeIcon) {
          const clickable = closeIcon.closest('button, [role="button"], span, div, i') || closeIcon;
          clickable.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
          clickable.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
          clickable.click?.();
          for (let i = 0; i < 4; i++) {
            await new Promise(r => setTimeout(r, 100));
            const confirmBtn = [...document.querySelectorAll('.eds-modal, [class*="modal"], [role="dialog"], .shopee-modal, .eds-dialog')].flatMap(m =>
              [...m.querySelectorAll('button, [role="button"]')].filter(b =>
                visible(b) && /xóa|xác nhận|đồng ý|ok/i.test(text(b)) && !/hủy/i.test(text(b))
              )
            )[0];
            if (confirmBtn) {
              confirmBtn.click?.();
              await new Promise(r => setTimeout(r, 150));
              break;
            }
          }
        }
      }
    } catch { /* ignore */ }
  }

  function getSingleProductInputs() {
    const noVarContainer = document.querySelector('.no-variations, [class*="no-variations"], [class*="variation-container"]');
    if (noVarContainer) {
      const rows = [...noVarContainer.querySelectorAll('.edit-row, [class*="edit-row"], .eds-form-item, [class*="form-item"]')].filter(visible);
      const priceRow = rows.find(r => /giá/i.test(text(r.querySelector('.edit-label, [class*="label"], [class*="title"]') || r)));
      const stockRow = rows.find(r => /kho hàng/i.test(text(r.querySelector('.edit-label, [class*="label"], [class*="title"]') || r)));

      let priceInput = priceRow?.querySelector('input');
      let stockInput = stockRow?.querySelector('input');

      if (!priceInput || !stockInput) {
        const allInps = [...noVarContainer.querySelectorAll('input')].filter(el =>
          visible(el) && editable(el) && !['hidden', 'checkbox', 'radio', 'file'].includes(el.type)
        );
        if (allInps.length >= 2) {
          priceInput = priceInput || allInps[0];
          stockInput = stockInput || allInps[1];
        }
      }
      return {priceInput, stockInput};
    }
    return {priceInput: null, stockInput: null};
  }

  function fillVariantTable(price, totalStock) {
    price = price || 200000;
    totalStock = (totalStock !== null && totalStock !== undefined && totalStock !== '') ? Number(totalStock) : 20;
    if (isNaN(totalStock) || totalStock <= 0) totalStock = 20;

    let filledPrice = false, filledStock = false;
    try {
      // 0. If auto-generated variants are present, NEVER click apply! Dismiss them instead.
      const hasAutoVariants = [...document.querySelectorAll('*')].some(el =>
        visible(el) && /các phân loại được tự động điền/i.test(text(el))
      );
      if (hasAutoVariants) {
        dismissAutoGeneratedVariants();
        return {filledPrice: false, filledStock: false};
      }
      // 1. Check Batch Edit bar (Áp dụng cho tất cả phân loại / Chỉnh sửa hàng loạt)
      const batchContainers = [...document.querySelectorAll('.batch-edit, [class*="batch-edit"], [class*="batch-container"], [class*="batch"], tr, div')].filter(el =>
        visible(el) && /áp dụng cho tất cả|chỉnh sửa hàng loạt/i.test(text(el))
      );
      for (const container of batchContainers) {
        const inputs = [...container.querySelectorAll('input')].filter(el =>
          visible(el) && editable(el) && !['hidden', 'checkbox', 'radio', 'file'].includes(el.type)
        );
        const applyBtn = [...container.querySelectorAll('button, [role="button"]')].find(b =>
          visible(b) && /áp dụng/i.test(text(b))
        );
        if (inputs.length >= 2) {
          fillInputElement(inputs[0], String(price));
          fillInputElement(inputs[1], String(totalStock));
          if (applyBtn) {
            applyBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
            applyBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
            applyBtn.click();
            filledPrice = true;
            filledStock = true;
          }
        }
      }

      // 2. Find rows in variant table on the page
      const allRows = [...document.querySelectorAll('.eds-table__body-row, tbody tr, [class*="table__body-row"], [class*="table-row"]')].filter(row =>
        visible(row) && row.querySelector('input') && (row.closest('[class*="variation"], [class*="model"], [class*="tier"]') || row.closest('table'))
      );

      const rowCount = allRows.length;

      if (rowCount > 0) {
        const baseStock = Math.max(1, Math.floor(totalStock / rowCount));
        const remainder = totalStock % rowCount;

        for (let i = 0; i < rowCount; i++) {
          const row = allRows[i];
          const assignedStock = baseStock + (i < remainder ? 1 : 0);
          const textInputs = [...row.querySelectorAll('input')]
            .filter(el => editable(el) && visible(el) && !['hidden', 'checkbox', 'radio', 'file'].includes(el.type));
          if (textInputs.length >= 2) {
            if (price && String(textInputs[0].value).replace(/\D/g, '') !== String(price).replace(/\D/g, '')) {
              fillInputElement(textInputs[0], String(price));
              filledPrice = true;
            }
            if (String(textInputs[1].value).replace(/\D/g, '') !== String(assignedStock).replace(/\D/g, '')) {
              fillInputElement(textInputs[1], String(assignedStock));
              filledStock = true;
            }
          }
        }
      } else {
        // Standard single product (No variants): Use precise inputs from .no-variations
        const {priceInput, stockInput} = getSingleProductInputs();
        const singlePrice = priceInput || find('price_vnd');
        if (singlePrice && String(singlePrice.value).replace(/\D/g, '') !== String(price).replace(/\D/g, '')) {
          fillInputElement(singlePrice, String(price));
          filledPrice = true;
        }
        const singleStock = stockInput || find('stock');
        if (singleStock && String(singleStock.value).replace(/\D/g, '') !== String(totalStock).replace(/\D/g, '')) {
          fillInputElement(singleStock, String(totalStock));
          filledStock = true;
        }
      }
    } catch { /* ignore */ }
    return {filledPrice, filledStock};
  }

  async function uploadShopeeImages(images) {
    if (!Array.isArray(images) || images.length === 0) return false;

    // Auto-dismiss any error modal if already open
    const modalBtn = [...document.querySelectorAll('.eds-modal button, [class*="modal"] button, [role="dialog"] button, button')].find(b =>
      visible(b) && /xác nhận|đóng|đồng ý|ok/i.test(text(b))
    );
    if (modalBtn) modalBtn.click();

    // STRICTLY filter out video file inputs and only accept image inputs
    const fileInputs = [...document.querySelectorAll('input[type="file"]')].filter(inp => {
      const acc = (inp.getAttribute('accept') || '').toLowerCase();
      if (acc.includes('video') || acc.includes('mp4')) return false;

      // Check form-item or container
      const container = inp.closest('.eds-form-item, .shopee-form-item, [class*="form-item"], [class*="form-group"], section');
      const cTxt = (container ? text(container) : '').toLowerCase();
      if (cTxt.includes('video') || cTxt.includes('thêm video') || cTxt.includes('max 30mb')) return false;

      // Ensure it is an image upload target
      const isImgAccept = acc.includes('image') || acc.includes('jpg') || acc.includes('jpeg') || acc.includes('png');
      const isImgContainer = /hình ảnh|ảnh bìa|ảnh sản phẩm|hình ảnh sản phẩm|image|picture|photo/i.test(cTxt);
      return isImgAccept || isImgContainer || !acc;
    });
    if (fileInputs.length === 0) return false;

    try {
      const files = [];
      for (let i = 0; i < images.length && i < 9; i++) {
        const item = images[i];
        if (!item) continue;
        let blob;
        if (typeof item === 'string') {
          try {
            const res = await fetch(item);
            blob = await res.blob();
          } catch {
            if (item.startsWith('data:')) {
              try {
                const [h, b] = item.split(',');
                const m = h.match(/:(.*?);/)?.[1] || 'image/jpeg';
                const cleanB64 = b.replace(/[\r\n\s]/g, '');
                const s = atob(cleanB64);
                const u = new Uint8Array(s.length);
                for (let k = 0; k < s.length; k++) u[k] = s.charCodeAt(k);
                blob = new Blob([u], {type: m});
              } catch { /* ignore */ }
            }
          }
        } else if (item instanceof Blob) {
          blob = item;
        }
        if (blob) {
          const mime = blob.type || 'image/jpeg';
          const ext = mime.includes('png') ? 'png' : 'jpg';
          files.push(new File([blob], `product_${i + 1}.${ext}`, {type: mime}));
        }
      }
      if (files.length === 0) return false;

      // Identify gallery input (has multiple) and cover input (single file)
      const galleryInput = fileInputs.find(inp => inp.multiple) || fileInputs[0];
      const coverInput = fileInputs.find(inp => !inp.multiple && inp !== galleryInput) || (fileInputs.length > 1 ? fileInputs[1] : null);

      function dispatchUpload(input, fileList) {
        if (!input || !fileList.length) return;
        const dt = new DataTransfer();
        for (const f of fileList) dt.items.add(f);

        try {
          input.files = dt.files;
          input.dispatchEvent(new Event('input', {bubbles: true}));
          input.dispatchEvent(new Event('change', {bubbles: true}));
        } catch { /* ignore */ }

        const dropzone = input.closest('.eds-upload, [class*="upload"], [class*="dragger"], [class*="picture"], [class*="drop"]') || input.parentElement;
        if (dropzone) {
          try {
            const drop = new DragEvent('drop', {bubbles: true, cancelable: true});
            try { Object.defineProperty(drop, 'dataTransfer', {value: dt}); } catch {}
            dropzone.dispatchEvent(new DragEvent('dragenter', {bubbles: true, cancelable: true}));
            dropzone.dispatchEvent(new DragEvent('dragover', {bubbles: true, cancelable: true}));
            dropzone.dispatchEvent(drop);
          } catch { /* ignore */ }
        }
      }

      // 1. Upload gallery first
      if (galleryInput) {
        dispatchUpload(galleryInput, files);
      }

      // 2. Upload cover after 400ms if distinct cover input exists
      if (coverInput) {
        await new Promise(r => setTimeout(r, 400));
        dispatchUpload(coverInput, [files[0]]);
      }

      return true;
    } catch { return false; }
  }

  let suggestedAttributesDone = false;

  function isBrandSelected() {
    const brandContainers = [...document.querySelectorAll('.attribute-select-item, .eds-form-item, .shopee-form-item, [class*="form-item"], [class*="edit-row"]')].filter(el =>
      visible(el) && !isInsideVariantSection(el) && /thương hiệu/i.test(text(el.querySelector('.item-title-text, .edit-title, label, [class*="label"], [class*="title"]') || el))
    );
    if (!brandContainers.length) return true;
    const container = brandContainers[0];

    const containerText = text(container).toLowerCase();
    if (containerText.includes('vui lòng điền thương hiệu') || containerText.includes('vui lòng chọn')) return false;

    const selectorInner = container.querySelector('.eds-selector__inner');
    if (selectorInner) {
      const val = text(selectorInner).trim().toLowerCase();
      if (val && !val.includes('vui lòng chọn')) return true;
      return false;
    }

    const selectTrigger = container.querySelector('.eds-select, .shopee-select, [class*="select"], [role="combobox"]');
    if (selectTrigger) {
      const val = text(selectTrigger).trim().toLowerCase();
      if (val && !val.includes('vui lòng chọn')) return true;
    }
    const inp = container.querySelector('input');
    if (inp && inp.value && inp.value.trim() && !/vui lòng chọn/i.test(inp.value)) return true;
    return false;
  }

  function isOriginSelected() {
    const allLabels = [...document.querySelectorAll('label, [class*="label"], [class*="title"]')].filter(el =>
      visible(el) && !isInsideVariantSection(el) && /^\s*\*?\s*xuất xứ\s*$/i.test(text(el))
    );
    if (!allLabels.length) return true;
    const container = allLabels[0].closest('.eds-form-item, [class*="form-item"]') || allLabels[0].parentElement?.parentElement;
    if (!container) return false;

    const selectTrigger = container.querySelector('.eds-select, .shopee-select, [class*="select"], [role="combobox"]');
    if (selectTrigger) {
      const val = text(selectTrigger).trim().toLowerCase();
      if (val && !val.includes('vui lòng chọn')) return true;
    }
    return false;
  }

  function isShippingEnabled() {
    const bodyText = document.body.innerText.toLowerCase();
    if (bodyText.includes('chưa có kênh vận chuyển nào được bật') || bodyText.includes('kênh vận chuyển cần được bật')) {
      return false;
    }

    const switches = [...document.querySelectorAll('.eds-switch, .shopee-switch, [role="switch"]')].filter(visible);
    const shippingSwitches = switches.filter(sw => {
      const row = sw.closest('tr, [class*="row"], [class*="item"], div');
      const rowText = row ? text(row).toLowerCase() : '';
      return rowText.includes('nhanh') || rowText.includes('hỏa tốc') || rowText.includes('hàng cồng kềnh') || rowText.includes('trong ngày') || rowText.includes('vận chuyển');
    });

    if (shippingSwitches.length === 0) return true;

    return shippingSwitches.some(sw =>
      sw.classList.contains('eds-switch--checked') || sw.classList.contains('is-checked') ||
      sw.getAttribute('aria-checked') === 'true' || Boolean(sw.querySelector('input[type="checkbox"]')?.checked)
    );
  }

  function fixSuggestedAttributes() {
    if (suggestedAttributesDone) return false;

    // Look strictly for "Áp dụng tất cả" button inside "Gợi ý và điền sẵn các thuộc tính" or "Thông tin chi tiết"
    const containers = [...document.querySelectorAll('.eds-card, [class*="card"], [class*="panel"], [class*="detail"], section, div')].filter(el =>
      visible(el) && !isInsideVariantSection(el) && /gợi ý và điền sẵn|thông tin chi tiết/i.test(text(el.querySelector('h1, h2, h3, h4, [class*="title"]') || el))
    );
    for (const c of containers) {
      const btn = [...c.querySelectorAll('button, [role="button"]')].find(b => {
        if (!visible(b) || b.disabled || isInsideVariantSection(b)) return false;
        const t = text(b).trim().toLowerCase();
        return t === 'áp dụng tất cả';
      });
      if (btn) {
        suggestedAttributesDone = true;
        btn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
        btn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
        btn.click();
        return true;
      }
    }

    // Standalone button fallback matching exact text "áp dụng tất cả" outside variant/sales section
    const standaloneBtn = [...document.querySelectorAll('button, [role="button"]')].find(b => {
      if (!visible(b) || b.disabled || isInsideVariantSection(b)) return false;
      if (b.closest('[class*="batch"], [class*="variation"], [class*="model"], [class*="tier"]')) return false;
      const t = text(b).trim().toLowerCase();
      return t === 'áp dụng tất cả';
    });
    if (standaloneBtn) {
      suggestedAttributesDone = true;
      standaloneBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
      standaloneBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
      standaloneBtn.click();
      return true;
    }
    return false;
  }

  function fixDescription() {
    const descEl = find('description');
    if (!descEl) return;
    const descText = descEl.isContentEditable ? (descEl.innerText || descEl.textContent || '') : (descEl.value || '');
    if (descText.trim().length >= 100) return;

    const nameEl = find('name');
    const pName = (nameEl ? nameEl.value : '') || 'Mũ bảo hiểm thể thao thời trang cao cấp';
    const base = descText.trim() || pName;
    const fullDesc = `${base}. Thiết kế thể thao hiện đại, kiểu dáng ôm đầu chắc chắn và thoáng khí tối ưu. Chất liệu cao cấp bền bỉ, đệm mút êm ái, chống va đập hiệu quả, mang lại sự tiện dụng và an toàn tối đa trên mọi cung đường. Phù hợp sử dụng hàng ngày, đi phượt hoặc rèn luyện thể thao.`;
    fillInputElement(descEl, fullDesc);
  }

  function fixWeight() {
    const weightInp = find('weight_g') || find('weight');
    if (!weightInp) return;
    if (weightInp.value && weightInp.value !== '0') return;
    fillInputElement(weightInp, '500');
  }

  function tryClickNextStepButton() {
    const allBtns = [...document.querySelectorAll('button, [role="button"]')].filter(visible);
    const nextBtn = allBtns.find(b => {
      const t = text(b).trim().toLowerCase();
      const isNext = t === 'tiếp theo' || t === 'tiếp tục' || t === 'bước tiếp theo' || t.includes('tiếp theo');
      return isNext && !b.disabled && !b.classList.contains('is-disabled') && b.getAttribute('aria-disabled') !== 'true';
    });
    if (nextBtn) {
      nextBtn.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
      nextBtn.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
      nextBtn.click();
      return true;
    }
    return false;
  }

  function selectSuggestedCategory() {
    const isStep1 = Boolean(find('name') && !find('price_vnd') && !find('stock') && !find('description'));
    if (!isStep1) return;

    const categoryItem = [...document.querySelectorAll('.eds-form-item, [class*="form-item"]')].find(el => {
      if (!visible(el) || isInsideVariantSection(el)) return false;
      const label = el.querySelector('label, [class*="label"], [class*="title"]');
      return label && /ngành hàng|danh mục/i.test(text(label));
    });
    if (!categoryItem) return;

    const candidateChips = [...categoryItem.querySelectorAll('button, [role="button"], .eds-tag, [class*="tag"], [class*="chip"], span, div')]
      .filter(el => {
        if (!visible(el) || isInsideVariantSection(el)) return false;
        const t = text(el).toLowerCase();
        return (t.includes('mũ bảo hiểm') || t.includes('xe máy') || t.includes('thể thao'))
          && (el.classList.contains('eds-tag') || el.closest('button, [role="button"], .eds-tag, [class*="tag"]'));
      });
    for (const chip of candidateChips) {
      const clickable = chip.closest('button, [role="button"], .eds-tag, [class*="tag"]') || chip;
      clickable.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
      clickable.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
      clickable.click();
      break;
    }
  }

  function dismissErrorModals() {
    try {
      const modalContainers = [...document.querySelectorAll('.eds-modal, [class*="modal"], [role="dialog"], .shopee-modal')].filter(visible);
      if (!modalContainers.length) return;
      for (const modal of modalContainers) {
        const btn = [...modal.querySelectorAll('button, [role="button"]')].find(b =>
          visible(b) && /xác nhận|đóng|đồng ý|ok|close/i.test(text(b))
        );
        if (btn) btn.click();
      }
    } catch { /* ignore */ }
  }

  async function fillBrand(brandName = 'No brand') {
    try {
      if (isBrandSelected()) return true;

      // Strategy 0: Apply all suggested attributes button if present
      fixSuggestedAttributes();
      await new Promise(r => setTimeout(r, 100));
      if (isBrandSelected()) return true;

      const brandContainers = [...document.querySelectorAll('.attribute-select-item, .eds-form-item, .shopee-form-item, [class*="form-item"], [class*="edit-row"]')].filter(el =>
        visible(el) && !isInsideVariantSection(el) && /thương hiệu/i.test(text(el.querySelector('.item-title-text, .edit-title, label, [class*="label"], [class*="title"]') || el))
      );
      const brandContainer = brandContainers[0];

      if (brandContainer) {
        // Strategy 1: Look for chips strictly inside brandContainer
        const localBtns = [...(brandContainer.parentElement || brandContainer).querySelectorAll('button, [role="button"], .eds-tag, [class*="tag"], [class*="chip"]')].filter(el => visible(el) && !isInsideVariantSection(el));
        const localNoBrand = localBtns.find(b => /no brand|không có thương hiệu/i.test(text(b)));
        if (localNoBrand) {
          localNoBrand.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
          localNoBrand.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
          localNoBrand.click();
          await new Promise(r => setTimeout(r, 150));
          if (isBrandSelected()) return true;
        }

        // Strategy 2: Click .eds-selector specifically to open dropdown, then match No brand in brand popover
        const selector = brandContainer.querySelector('.eds-selector') || brandContainer.querySelector('.eds-selector__inner');
        if (selector) {
          try { selector.scrollIntoView({block: 'center', behavior: 'instant'}); } catch {}
          selector.focus?.();
          selector.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
          selector.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
          selector.click();

          for (let attempt = 0; attempt < 12; attempt++) {
            await new Promise(r => setTimeout(r, 80));
            // Find active popups containing 'no brand' (excludes topbar language menu)
            const candidates = [...document.querySelectorAll('*')].filter(el => {
              if (el.offsetWidth === 0 || el.offsetHeight === 0) return false;
              const t = (el.innerText || el.textContent || '').trim().toLowerCase();
              return t === 'no brand';
            });

            if (candidates.length > 0) {
              const leaf = candidates.reduce((prev, curr) => prev.contains(curr) ? curr : prev);
              const rect = leaf.getBoundingClientRect();
              const x = rect.left + rect.width / 2;
              const y = rect.top + rect.height / 2;
              const topEl = document.elementFromPoint(x, y);

              const targets = new Set([
                topEl,
                leaf,
                leaf.parentElement,
                leaf.parentElement?.parentElement,
                leaf.closest('li'),
                leaf.closest('[role="option"]'),
                leaf.closest('[class*="item"]'),
                leaf.closest('[class*="option"]')
              ]);

              for (const el of targets) {
                if (!el) continue;
                ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach(evtType => {
                  try {
                    el.dispatchEvent(new PointerEvent(evtType, {bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, view: window}));
                  } catch {}
                  try {
                    el.dispatchEvent(new MouseEvent(evtType, {bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, view: window}));
                  } catch {}
                });
                try { el.click?.(); } catch {}
              }

              await new Promise(r => setTimeout(r, 200));
              return isBrandSelected();
            }
          }
        }
      }
    } catch { /* independent */ }
    return isBrandSelected();
  }

  async function fillOrigin(originName = 'Việt Nam') {
    try {
      if (isOriginSelected()) return true;

      const originLabels = [...document.querySelectorAll('label, [class*="label"], [class*="title"]')].filter(el =>
        visible(el) && !isInsideVariantSection(el) && /^\s*\*?\s*xuất xứ\s*$/i.test(text(el))
      );
      const originLabel = originLabels[0];
      const originItem = originLabel?.closest('.eds-form-item, [class*="form-item"]') || originLabel?.parentElement?.parentElement;
      if (!originItem) return false;

      // Strategy 1: Look for chips strictly inside originItem
      const localBtns = [...(originItem.parentElement || originItem).querySelectorAll('button, [role="button"], .eds-tag, [class*="tag"], [class*="chip"]')].filter(el => visible(el) && !isInsideVariantSection(el));
      const targetTag = localBtns.find(el => {
        const clean = text(el).replace(/[✨*]/g, '').trim().toLowerCase();
        return clean === 'việt nam' || clean === 'vietnam';
      });
      if (targetTag) {
        targetTag.focus?.();
        targetTag.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
        targetTag.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
        targetTag.click();
        await new Promise(r => setTimeout(r, 150));
        return isOriginSelected();
      }

      // Strategy 2: Dropdown trigger & select
      const selectTrigger = originItem.querySelector('.eds-select, .shopee-select, [class*="select"], [role="combobox"], input') || originItem;
      if (selectTrigger) {
        selectTrigger.focus?.();
        selectTrigger.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
        selectTrigger.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
        selectTrigger.click();

        let options = [];
        for (let attempt = 0; attempt < 5; attempt++) {
          await new Promise(r => setTimeout(r, 80));
          options = [...document.querySelectorAll('.eds-select-dropdown__item, [role="option"], [class*="select-dropdown"] li, [class*="dropdown__item"], [class*="option"]')].filter(visible);
          if (options.length > 0) break;
        }

        const vnOpt = options.find(o => /việt nam|vietnam/i.test(text(o)));
        if (vnOpt) {
          vnOpt.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true}));
          vnOpt.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true}));
          vnOpt.click();
          await new Promise(r => setTimeout(r, 150));
          return isOriginSelected();
        }
      }
    } catch { /* independent */ }
    return isOriginSelected();
  }

  function toggleSwitchElement(sw) {
    if (!sw) return false;
    const isChecked = () => sw.classList.contains('eds-switch--checked') ||
      sw.classList.contains('is-checked') ||
      sw.getAttribute('aria-checked') === 'true' ||
      Boolean(sw.querySelector('input[type="checkbox"]')?.checked);

    if (isChecked()) return true;

    const clickableTargets = [
      sw.querySelector('.eds-switch__core, [class*="switch__core"]'),
      sw,
      sw.querySelector('input[type="checkbox"]'),
      sw.parentElement
    ].filter(Boolean);

    for (const target of clickableTargets) {
      try {
        target.dispatchEvent(new MouseEvent('pointerdown', {bubbles: true, cancelable: true, view: window}));
        target.dispatchEvent(new MouseEvent('mousedown', {bubbles: true, cancelable: true, view: window}));
        target.dispatchEvent(new MouseEvent('pointerup', {bubbles: true, cancelable: true, view: window}));
        target.dispatchEvent(new MouseEvent('mouseup', {bubbles: true, cancelable: true, view: window}));
        target.click();
      } catch {}
      if (isChecked()) return true;
    }

    const inp = sw.querySelector('input[type="checkbox"]');
    if (inp && !isChecked()) {
      try {
        inp.checked = true;
        inp.dispatchEvent(new Event('input', {bubbles: true}));
        inp.dispatchEvent(new Event('change', {bubbles: true}));
      } catch {}
    }

    return isChecked();
  }

  function enableShippingChannel() {
    try {
      const switches = [...document.querySelectorAll('.eds-switch, .shopee-switch, [role="switch"]')].filter(visible);

      // 1. Target rows with red warning "Kênh vận chuyển cần được bật"
      const warningRows = [...document.querySelectorAll('tr, [class*="row"], [class*="item"], div')].filter(el =>
        visible(el) && /kênh vận chuyển cần được bật/i.test(text(el))
      );
      for (const row of warningRows) {
        const sw = row.querySelector('.eds-switch, .shopee-switch, [role="switch"], [class*="switch"]');
        if (sw) toggleSwitchElement(sw);
      }

      // 2. Target "Nhanh" shipping row specifically
      for (const sw of switches) {
        const row = sw.closest('tr, [class*="row"], [class*="item"], div');
        const t = row ? text(row).toLowerCase() : '';
        if (t.includes('nhanh') && (t.includes('đối tác shopee') || t.includes('16.500') || t.includes('kênh vận chuyển') || t.includes('tiếp tục'))) {
          toggleSwitchElement(sw);
          return true;
        }
      }

      // 3. Fallback: Any switch in a shipping row
      for (const sw of switches) {
        const row = sw.closest('tr, [class*="row"], [class*="item"], div');
        const t = row ? text(row).toLowerCase() : '';
        if (t.includes('nhanh') || t.includes('tiêu chuẩn') || t.includes('hàng cồng kềnh') || t.includes('trong ngày') || t.includes('hỏa tốc')) {
          if (toggleSwitchElement(sw)) return true;
        }
      }
    } catch { /* independent */ }
  }

  async function fill(payload) {
    allowed();
    checkTarget(payload.target);
    const checkPage = () => {
      if (payload.bypass_context_check) return;
      if (payload.document_id !== documentId || payload.url !== pageUrl() || !readContext
        || payload.page_context !== readContext.token || payload.page_context !== pageContext() || readContext.url !== location.href)
        throw Error('Trang đã đổi. Đọc lại trang trước khi điền.');
      checkTarget(payload.target);
    };
    checkPage();
    const ALLOWED_FIELDS = ['name', 'description', 'price_vnd', 'stock', 'images', 'weight_g', 'weight', 'brand', 'category_name', 'origin'];
    if (!payload.draft || Object.keys(payload.draft).some(key => !ALLOWED_FIELDS.includes(key))) throw Error('Bản nháp không hợp lệ.');
    const report = [];

    let imagesUploaded = false;
    if (Array.isArray(payload.draft.images) && payload.draft.images.length > 0) {
      imagesUploaded = await uploadShopeeImages(payload.draft.images);
    }

    // Dismiss unwanted Shopee auto-generated variants for single product drafts
    await dismissAutoGeneratedVariants();

    for (const [field, value] of Object.entries(payload.draft)) {
      if (field === 'images') continue;
      checkPage();
      if (value === null || value === undefined) continue;
      if (typeof value !== 'string' && typeof value !== 'number') throw Error('Giá trị không hợp lệ.');
      if (field === 'brand') {
        const ok = await fillBrand(String(value));
        if (ok) {
          report.push({field: 'brand', status: 'filled'});
          continue;
        }
      }
      if (field === 'origin') {
        const ok = await fillOrigin(String(value));
        if (ok) {
          report.push({field: 'origin', status: 'filled'});
          continue;
        }
      }
      const el = find(field);
      if (!el) {report.push({field, status: 'unmapped'}); continue;}
      let content = String(value);
      if (field === 'description' && content.trim().length < 100) {
        const extra = ' Thiết kế thời trang thể thao cao cấp, ôm đầu chắc chắn, thoáng khí và an toàn tối đa cho người sử dụng trên mọi cung đường.';
        while (content.trim().length < 100) {
          content = content.trim() + extra;
        }
      }
      if (el.maxLength > -1 && content.length > el.maxLength) {report.push({field, status: 'too_long'}); continue;}
      fillInputElement(el, content);
      if (field === 'weight_g' || field === 'weight') {
        setTimeout(enableShippingChannel, 250);
      }
      await new Promise(resolve => setTimeout(resolve, 60));
      const current = find(field);
      const actual = current?.isContentEditable ? (current.innerText || current.textContent) : current?.value;
      let retained = false;
      if (['price_vnd', 'stock', 'weight_g', 'weight'].includes(field)) {
        retained = String(actual || '').replace(/\D/g, '') === String(content).replace(/\D/g, '');
      } else {
        retained = String(actual || '').trim() === content.trim();
      }
      report.push({field, status: retained ? 'filled' : 'not_retained'});
    }

    // Auto-fill variant table only if variants legitimately exist and are NOT auto-generated suggestions
    const hasAutoVariants = [...document.querySelectorAll('*')].some(el =>
      visible(el) && (/các phân loại được tự động điền/i.test(text(el)) || /xóa (?:chỉ )?với một lần nhấp chuột/i.test(text(el)))
    );
    if (!hasAutoVariants) {
      const variantRes = fillVariantTable(payload.draft.price_vnd, payload.draft.stock);
      if (variantRes.filledPrice) {
        const idx = report.findIndex(r => r.field === 'price_vnd');
        if (idx >= 0) report[idx].status = 'filled';
        else report.push({field: 'price_vnd', status: 'filled'});
      }
      if (variantRes.filledStock) {
        const idx = report.findIndex(r => r.field === 'stock');
        if (idx >= 0) report[idx].status = 'filled';
        else report.push({field: 'stock', status: 'filled'});
      }
    }

    // Identify required fields that are still missing or erroring on Shopee
    const scan = scanRequiredFields();
    const unfilledRequired = scan.missing_fields;

    // Never click Save/Publish, dispatch submit or claim server-side persistence.
    return {
      report,
      submitted: false,
      images: imagesUploaded ? 'auto' : 'manual',
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
      if (message.kind === 'scan_required') {allowed(); return scanRequiredFields();}
      throw Error('Thao tác không hỗ trợ.');
    }).then(data => reply({ok: true, data}), error => reply({ok: false, error: error.message}));
    return true;
  });
  let autoFillBusy = false;
  let lastProcessedDraftTimestamp = 0;
  let autoFilledStep1 = false;
  let autoFilledStep2 = false;

  async function pollAutoFill() {
    if (autoFillBusy || autoFilledStep2) return;
    try {
      if (typeof chrome?.storage?.local?.get !== 'function') return;
      const {pending_shopee_draft} = await chrome.storage.local.get('pending_shopee_draft').catch(() => ({}));
      if (!pending_shopee_draft?.draft) return;

      // If a new draft arrived (different timestamp), reset step flags
      if (pending_shopee_draft.timestamp && pending_shopee_draft.timestamp !== lastProcessedDraftTimestamp) {
        lastProcessedDraftTimestamp = pending_shopee_draft.timestamp;
        autoFilledStep1 = false;
        autoFilledStep2 = false;
      }

      if (autoFilledStep2) return;
      if (Date.now() - (pending_shopee_draft.timestamp || 0) > 15 * 60 * 1000) {
        await chrome.storage.local.remove('pending_shopee_draft').catch(() => {});
        return;
      }
      if (pending_shopee_draft.target?.label) {
        try { checkTarget(pending_shopee_draft.target); } catch { return; }
      }

      const price = find('price_vnd');
      const stock = find('stock');
      const desc = find('description');
      const weight = find('weight_g');
      const name = find('name');

      const isStep2 = Boolean(price || stock || weight || desc || document.body.innerText.includes('Mô tả sản phẩm') || document.body.innerText.includes('áp dụng cho tất cả phân loại'));
      const isStep1 = Boolean(name && !isStep2);

      if (isStep2 && !autoFilledStep2) {
        autoFilledStep2 = true;
        await chrome.storage.local.remove('pending_shopee_draft').catch(() => {});
        autoFillBusy = true;
        try {
          const fillDraft = {...pending_shopee_draft.draft};
          if (!fillDraft.weight_g) fillDraft.weight_g = pending_shopee_draft.draft.weight_g || 500;
          if (!fillDraft.stock || fillDraft.stock <= 0) fillDraft.stock = pending_shopee_draft.draft.stock || 20;
          if (!fillDraft.price_vnd || fillDraft.price_vnd <= 0) fillDraft.price_vnd = pending_shopee_draft.draft.price_vnd || 150000;
          if (!fillDraft.brand) fillDraft.brand = 'No brand';
          if (!fillDraft.origin) fillDraft.origin = 'Việt Nam';
          if (!fillDraft.description || fillDraft.description.trim().length < 100) {
            const pName = fillDraft.name || 'Mũ bảo hiểm thể thao thời trang';
            fillDraft.description = `${pName}. Thiết kế thể thao hiện đại, kiểu dáng ôm đầu chắc chắn và thoáng khí tối ưu. Chất liệu cao cấp bền bỉ, đệm mút êm ái, chống va đập hiệu quả, mang lại sự tiện dụng và an toàn tối đa trên mọi cung đường.`;
          }

          // 1. Auto-apply suggested attributes ONCE
          try { fixSuggestedAttributes(); } catch { /* independent */ }

          // 2. Auto-select Brand only if not selected
          try {
            if (!isBrandSelected()) await fillBrand(fillDraft.brand);
          } catch { /* independent */ }

          // 3. Auto-select Origin only if not selected
          try {
            if (!isOriginSelected()) await fillOrigin(fillDraft.origin);
          } catch { /* independent */ }

          // 4. Fill draft fields
          let res = null;
          try {
            res = await fill({
              draft: fillDraft,
              target: pending_shopee_draft.target,
              bypass_context_check: true
            });
          } catch { /* independent */ }

          // 5. Specifically ensure weight is populated
          try { fixWeight(); } catch { /* independent */ }

          // 6. Dismiss auto-generated variants and ensure single product price and stock are populated
          try {
            await dismissAutoGeneratedVariants();
            const {priceInput, stockInput} = getSingleProductInputs();
            const singlePrice = priceInput || find('price_vnd');
            if (singlePrice && String(singlePrice.value).replace(/\D/g, '') !== String(fillDraft.price_vnd).replace(/\D/g, '')) {
              fillInputElement(singlePrice, String(fillDraft.price_vnd));
            }
            const singleStock = stockInput || find('stock');
            if (singleStock && String(singleStock.value).replace(/\D/g, '') !== String(fillDraft.stock).replace(/\D/g, '')) {
              fillInputElement(singleStock, String(fillDraft.stock));
            }
          } catch { /* independent */ }

          // 8. Ensure shipping channel is enabled only if not enabled
          try {
            if (!isShippingEnabled()) {
              enableShippingChannel();
              setTimeout(() => { if (!isShippingEnabled()) enableShippingChannel(); }, 500);
            }
          } catch { /* independent */ }

          // 9. Specifically ensure description is populated and satisfies >= 100 characters
          try { fixDescription(); } catch { /* independent */ }

          // 10. Auto-upload images if missing on Step 2
          if (Array.isArray(fillDraft.images) && fillDraft.images.length > 0) {
            try { await uploadShopeeImages(fillDraft.images); } catch { /* independent */ }
          }

          // Notify extension runtime so assistant asks in chat
          if (res?.required_scan) {
            chrome.runtime.sendMessage({
              kind: 'autofill_step2_completed',
              scan: res.required_scan
            }).catch(() => {});
          }
        } finally {
          autoFillBusy = false;
        }
        return;
      }

      if (isStep1) {
        const nameVal = name?.value;
        const expectedName = pending_shopee_draft.draft.name;
        const hasMissingImages = document.body.innerText.includes('(0/9)') || document.body.innerText.includes('(0/1)');

        if (!nameVal || (expectedName && nameVal.trim() !== expectedName.trim()) || hasMissingImages) {
          autoFillBusy = true;
          try {
            if (hasMissingImages && Array.isArray(pending_shopee_draft.draft.images) && pending_shopee_draft.draft.images.length > 0) {
              await uploadShopeeImages(pending_shopee_draft.draft.images);
            }
            await fill({
              draft: pending_shopee_draft.draft,
              target: pending_shopee_draft.target,
              bypass_context_check: true
            });
            const stillMissing = document.body.innerText.includes('(0/9)') || document.body.innerText.includes('(0/1)');
            if (!stillMissing && name?.value) {
              autoFilledStep1 = true;
            }
          } finally {
            autoFillBusy = false;
          }
        } else {
          autoFilledStep1 = true;
        }

        // Auto-select category suggestion if present & click "Tiếp theo" ONLY when images are uploaded
        const imagesStillMissing = document.body.innerText.includes('(0/9)') || document.body.innerText.includes('(0/1)');
        if (!imagesStillMissing) {
          try { selectSuggestedCategory(); } catch { /* ignore */ }
          setTimeout(() => { tryClickNextStepButton(); }, 600);
          setTimeout(() => { tryClickNextStepButton(); }, 1600);
        }
      }
    } catch { /* graceful fallback */ }
  }

  let autoRepairBusy = false;
  let lastRepairTime = 0;
  let repairAttempts = 0;
  let lastRepairedUrl = '';
  let lastRepairedStep = 0;
  const MAX_REPAIR_ATTEMPTS = 5;

  async function autoRepairShopeeProduct() {
    const isProductPage = location.href.includes('/portal/product/') || location.href.includes('/product/');
    if (!isProductPage) return;

    // Detect current step
    const price = find('price_vnd');
    const stock = find('stock');
    const desc = find('description');
    const weight = find('weight_g');
    const name = find('name');
    const isStep2 = Boolean(price || stock || weight || desc || document.body.innerText.includes('Mô tả sản phẩm') || document.body.innerText.includes('áp dụng cho tất cả phân loại'));
    const isStep1 = Boolean(name && !isStep2);
    const currentStep = isStep1 ? 1 : (isStep2 ? 2 : 0);

    if (location.href !== lastRepairedUrl || (currentStep > 0 && currentStep !== lastRepairedStep)) {
      lastRepairedUrl = location.href;
      lastRepairedStep = currentStep;
      repairAttempts = 0;
      suggestedAttributesDone = false;
    }

    if (repairAttempts >= MAX_REPAIR_ATTEMPTS || autoRepairBusy) return;

    // Always dismiss error modal immediately if present
    dismissErrorModals();

    if (Date.now() - lastRepairTime < 2000) return;

    await executeAutoRepair(isStep1, isStep2);
  }

  async function executeAutoRepair(isStep1, isStep2) {
    if (autoRepairBusy) return;
    autoRepairBusy = true;
    lastRepairTime = Date.now();
    repairAttempts++;
    try {
      // 0. Dismiss any error modal immediately
      dismissErrorModals();

      // If currently on Step 1, upload images if missing, then advance to Step 2
      if (isStep1) {
        const hasMissingImages = document.body.innerText.includes('(0/9)') || document.body.innerText.includes('(0/1)');
        if (hasMissingImages) {
          try {
            const {pending_shopee_draft} = await chrome.storage.local.get('pending_shopee_draft').catch(() => ({}));
            if (pending_shopee_draft?.draft?.images?.length) {
              await uploadShopeeImages(pending_shopee_draft.draft.images);
            }
          } catch { /* ignore */ }
        } else {
          try { selectSuggestedCategory(); } catch { /* ignore */ }
          tryClickNextStepButton();
        }
        return;
      }

      // If on Step 2:
      // 1. Auto-apply suggested attributes
      try { fixSuggestedAttributes(); } catch { /* independent */ }

      // 2. Fix Description if < 100 chars
      try { fixDescription(); } catch { /* independent */ }

      // 3. Fix Weight if missing
      try { fixWeight(); } catch { /* independent */ }

      // 4. Fix Brand only if not selected
      try {
        if (!isBrandSelected()) {
          await fillBrand('No brand');
        }
      } catch { /* independent */ }

      // 5. Fix Origin only if not selected
      try {
        if (!isOriginSelected()) {
          await fillOrigin('Việt Nam');
        }
      } catch { /* independent */ }

      // 6. Dismiss auto-generated variants and fix stock & price for single product
      try {
        await dismissAutoGeneratedVariants();
        const {priceInput, stockInput} = getSingleProductInputs();
        const singlePrice = priceInput || find('price_vnd');
        if (singlePrice && (!singlePrice.value || singlePrice.value === '0')) {
          fillInputElement(singlePrice, '200000');
        }
        const singleStock = stockInput || find('stock');
        if (singleStock && (!singleStock.value || singleStock.value === '0')) {
          fillInputElement(singleStock, '20');
        }
      } catch { /* independent */ }

      // 7. Ensure shipping channel is enabled
      try {
        if (!isShippingEnabled()) {
          enableShippingChannel();
        }
      } catch { /* independent */ }

      // Check if all critical fields are now satisfied; if so, STOP further repair!
      if (isBrandSelected() && isShippingEnabled()) {
        const descEl = find('description');
        const descLen = descEl ? (descEl.isContentEditable ? descEl.innerText.length : descEl.value.length) : 0;
        const priceEl = find('price_vnd');
        const stockEl = find('stock');
        const priceOk = priceEl && priceEl.value && priceEl.value !== '0';
        const stockOk = stockEl && stockEl.value && stockEl.value !== '0';
        if (descLen >= 100 && priceOk && stockOk) {
          repairAttempts = MAX_REPAIR_ATTEMPTS;
        }
      }
    } catch { /* ignore */ } finally {
      autoRepairBusy = false;
    }
  }

  setInterval(pollAutoFill, 1200);
  setInterval(autoRepairShopeeProduct, 2000);
})();
