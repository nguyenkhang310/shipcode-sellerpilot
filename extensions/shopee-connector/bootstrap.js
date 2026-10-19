// Wait for a scoped connection before mounting the same app bundle as mobile/web.
(async () => {
  try {
    const result = await chrome.runtime.sendMessage({kind: 'connection'});
    if (!result?.ok) throw Error(result?.error || 'Chưa khởi tạo được extension.');
    const url = new URL(location.href); url.searchParams.set('scope', result.data.id);
    url.searchParams.set('source', result.data.mode);
    url.searchParams.set('tab', 'assistant'); history.replaceState(null, '', url);
    for (const src of globalThis.SELLERPILOT_BUNDLES) {
      await new Promise((resolve, reject) => {
        const script = document.createElement('script'); script.src = src;
        script.onload = resolve; script.onerror = () => reject(Error('Không tải được giao diện SellerPilot.'));
        document.body.append(script);
      });
    }
  } catch (error) {
    document.querySelector('#root').textContent = error.message + ' Chạy npm run extension:build rồi tải lại extension.';
  }
})();
