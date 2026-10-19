(() => {
  const password = document.getElementById('auth-password');
  const toggle = document.getElementById('password-toggle');
  toggle?.addEventListener('click', () => {
    const showing = password.type === 'password';
    password.type = showing ? 'text' : 'password';
    toggle.setAttribute('aria-pressed', String(showing));
    toggle.setAttribute('aria-label', showing ? 'Ẩn mật khẩu' : 'Hiện mật khẩu');
  });
  const form = document.getElementById('auth-form');
  const submit = document.getElementById('auth-submit');
  const syncSubmit = () => {
    submit.disabled = [...form.querySelectorAll('input[required]')].some(field => !field.value.trim());
  };
  form?.addEventListener('input', syncSubmit);
  if (form && submit) syncSubmit();
  const dialog = document.getElementById('auth-method-dialog');
  document.querySelectorAll('[data-auth-method]').forEach(button => button.addEventListener('click', () => {
    const method = button.dataset.authMethod;
    document.getElementById('auth-method-title').textContent = 'Đăng nhập ' + method;
    document.getElementById('auth-method-message').textContent = 'Phương thức ' + method + ' chưa được kết nối. Bạn có thể tiếp tục bằng email hoặc tên đăng nhập của mình.';
    dialog.showModal();
  }));
  document.getElementById('auth-method-close')?.addEventListener('click', () => {
    dialog.close();
    document.getElementById('auth-login')?.focus();
  });
})();
