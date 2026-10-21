type Reply = { ok: boolean; data?: unknown; error?: string; status?: number };
type ExtensionRuntime = { sendMessage: (message: unknown) => Promise<Reply> };
const runtime = () => (globalThis as typeof globalThis & { chrome?: { runtime?: ExtensionRuntime } }).chrome?.runtime;
export const inExtension = () => typeof location !== 'undefined' && location.protocol === 'chrome-extension:';
export const isShopeeExtension = () => inExtension() && new URLSearchParams(location.search).get('source') !== 'local';
export async function extensionCall<T>(kind: string, payload: Record<string, unknown> = {}): Promise<T> {
  const result = await runtime()?.sendMessage({ kind, ...payload });
  if (!result?.ok) throw Object.assign(new Error(result?.error || 'Chưa kết nối được extension.'), { status: result?.status || 503 });
  return result.data as T;
}
export async function extensionRequest(path: string, options: RequestInit, signal: AbortSignal): Promise<unknown> {
  if (signal.aborted) throw new DOMException('Aborted', 'AbortError');
  const id = crypto.randomUUID();
  const connection = await extensionCall<{ id: string }>('connection');
  return new Promise((resolve, reject) => {
    const abort = () => { void extensionCall('cancel', { id }).catch(() => {}); reject(new DOMException('Aborted', 'AbortError')); };
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) { abort(); return; }
    void extensionCall('api', { id, connection_id: connection.id, path, method: options.method || 'GET', body: options.body || null,
      authorization: new Headers(options.headers).get('Authorization') })
      .then(resolve, reject).finally(() => signal.removeEventListener('abort', abort));
  });
}
