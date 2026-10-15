/* Shared, progressively enhanced interactions for the seller centre. */
(() => {
  const toggle = document.querySelector('.menu-toggle');
  const sidebar = document.querySelector('.seller-sidebar');
  const backdrop = document.querySelector('.sidebar-backdrop');
  const mobile = matchMedia('(max-width: 800px)');
  const closeNavigation = (restoreFocus = false) => {
    document.body.classList.remove('nav-open');
    backdrop.hidden = true;
    toggle.setAttribute('aria-expanded', 'false');
    toggle.setAttribute('aria-label', 'Mở menu quản lý');
    if (restoreFocus) toggle.focus();
  };
  toggle.addEventListener('click', () => {
    if (document.body.classList.contains('nav-open')) return closeNavigation(true);
    document.body.classList.add('nav-open');
    backdrop.hidden = false;
    toggle.setAttribute('aria-expanded', 'true');
    toggle.setAttribute('aria-label', 'Đóng menu quản lý');
    sidebar.querySelector('a').focus();
  });
  backdrop.addEventListener('click', () => closeNavigation(true));
  mobile.addEventListener('change', () => closeNavigation());
  document.addEventListener('keydown', event => {
    if (event.key === 'Escape') {
      if (document.body.classList.contains('nav-open')) closeNavigation(true);
      document.querySelectorAll('.header-popover[open]').forEach(menu => {
        menu.open = false;
        menu.querySelector('summary').focus();
      });
    }
    if (event.key === 'Tab' && document.body.classList.contains('nav-open')) {
      const controls = [toggle, ...sidebar.querySelectorAll('a,button')].filter(el => el.getClientRects().length);
      const first = controls[0], last = controls[controls.length - 1];
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  document.querySelectorAll('.nav-group-title').forEach(button => {
    button.addEventListener('click', () => {
      const content = document.getElementById(button.getAttribute('aria-controls'));
      content.hidden = !content.hidden;
      button.setAttribute('aria-expanded', String(!content.hidden));
    });
  });
  document.addEventListener('click', event => {
    document.querySelectorAll('.header-popover[open]').forEach(menu => {
      if (!menu.contains(event.target)) menu.open = false;
    });
  });
  document.querySelectorAll('[data-dismiss]').forEach(button => button.addEventListener('click', () => button.closest('.notice').remove()));
  document.querySelectorAll('form[data-confirm]').forEach(form => form.addEventListener('submit', event => {
    if (!confirm(form.dataset.confirm)) event.preventDefault();
  }));
  let toastTimer;
  const toast = message => {
    const el = document.querySelector('.toast');
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
  };
  document.querySelectorAll('[data-copy]').forEach(button => button.addEventListener('click', async () => {
    try { await navigator.clipboard.writeText(button.dataset.copy); toast('Đã sao chép.'); }
    catch { toast('Chưa sao chép được. Hãy chọn và sao chép nội dung trực tiếp.'); }
  }));
  document.querySelectorAll('[data-bulk-form]').forEach(form => {
    const items = [...document.querySelectorAll('input[data-bulk-item][form="' + form.id + '"]')];
    const all = [...document.querySelectorAll('[data-select-all="' + form.id + '"]')];
    const submit = form.querySelector('button[type=submit]');
    const sync = () => {
      const count = items.filter(item => item.checked).length;
      form.querySelector('[data-selection-count]').textContent = count;
      all.forEach(checkbox => {
        checkbox.checked = items.length > 0 && count === items.length;
        checkbox.indeterminate = count > 0 && count < items.length;
        checkbox.disabled = items.length === 0;
      });
      submit.disabled = count === 0;
    };
    all.forEach(checkbox => checkbox.addEventListener('change', () => { items.forEach(item => { item.checked = checkbox.checked; }); sync(); }));
    items.forEach(item => item.addEventListener('change', sync));
    sync();
  });
  document.querySelectorAll('.chart-container').forEach(container => {
    const tooltip = container.querySelector('.chart-tooltip');
    container.querySelectorAll('.chart-point').forEach(point => {
      const show = () => {
        tooltip.textContent = point.dataset.chartLabel + ' · ' + point.dataset.chartValue;
        tooltip.hidden = false;
        const box = point.getBoundingClientRect(), parent = container.getBoundingClientRect();
        const left = box.left - parent.left + container.scrollLeft;
        tooltip.style.left = Math.max(container.scrollLeft + 4, Math.min(left - tooltip.offsetWidth / 2, container.scrollLeft + container.clientWidth - tooltip.offsetWidth - 4)) + 'px';
        tooltip.style.top = Math.max(0, box.top - parent.top - 42) + 'px';
      };
      point.addEventListener('mouseenter', show);
      point.addEventListener('focus', show);
      point.addEventListener('click', show);
      point.addEventListener('mouseleave', () => { tooltip.hidden = true; });
      point.addEventListener('blur', () => { tooltip.hidden = true; });
    });
  });
  // Legacy forms also get a contained horizontal scroll area on small screens.
  document.querySelectorAll('.data-table').forEach(table => {
    if (!table.parentElement.classList.contains('table-wrap')) {
      const wrapper = document.createElement('div');
      wrapper.className = 'table-wrap';
      table.before(wrapper);
      wrapper.append(table);
    }
  });
  document.querySelectorAll('.chat-log').forEach(log => { log.scrollTop = log.scrollHeight; });
  const editor = document.getElementById('product-editor');
  if (editor) {
    const imageUrl = document.getElementById('image-url');
    const file = document.getElementById('image-file');
    const preview = document.getElementById('product-image-preview');
    const placeholder = document.querySelector('.image-placeholder');
    const imageStatus = document.querySelector('[data-image-status]');
    let objectUrl;
    const previewImage = () => {
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = undefined;
      file.setCustomValidity('');
      if (file.files[0] && file.files[0].size > 8 * 1024 * 1024) {
        file.setCustomValidity('Ảnh tối đa 8 MB.');
        file.reportValidity();
        return;
      }
      if (file.files[0]) objectUrl = URL.createObjectURL(file.files[0]);
      const source = objectUrl || imageUrl.value.trim();
      preview.hidden = !source;
      placeholder.hidden = Boolean(source);
      imageStatus.textContent = source ? 'Đang tải ảnh…' : 'Ảnh bìa sản phẩm';
      if (source) preview.src = source;
      else preview.removeAttribute('src');
    };
    preview.addEventListener('load', () => { imageStatus.textContent = 'Ảnh bìa sản phẩm'; });
    preview.addEventListener('error', () => { preview.hidden = true; placeholder.hidden = false; imageStatus.textContent = 'Chưa tải được ảnh. Kiểm tra lại đường dẫn.'; });
    imageUrl.addEventListener('change', previewImage);
    file.addEventListener('change', previewImage);
    const variants = [...editor.querySelectorAll('[data-active-variant="1"]')];
    if (variants.length) {
      const syncTotals = () => {
        const prices = variants.map(row => Number(row.querySelector('[name^=variant_price_]').value));
        const stocks = variants.map(row => Number(row.querySelector('[name^=variant_stock_]').value));
        document.getElementById('price').value = Math.min(...prices);
        document.getElementById('stock').value = stocks.reduce((total, stock) => total + stock, 0);
      };
      variants.forEach(row => row.addEventListener('input', syncTotals));
    }
  }
  const couponType = document.getElementById('coupon-type');
  if (couponType) {
    const updateUnit = () => {
      const percent = couponType.value === 'percent';
      document.getElementById('voucher-value').max = percent ? '100' : '10000000';
      document.querySelector('[data-discount-unit]').textContent = percent ? 'Nhập phần trăm giảm từ 1 đến 100%.' : 'Nhập số tiền giảm, đơn vị đồng.';
    };
    couponType.addEventListener('change', updateUnit);
    updateUnit();
  }
})();
