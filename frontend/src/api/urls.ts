export function resolveApiUrls(options: {
  configuredApi?: string; configuredStore?: string;
  metroHost?: string; nativeDevelopment: boolean; android: boolean;
}) {
  const explicit = options.configuredApi?.trim().replace(/\/+$/, '');
  let host = options.android ? '10.0.2.2' : '127.0.0.1';
  if (options.nativeDevelopment && options.metroHost) {
    try {
      const metro = new URL(/^https?:\/\//.test(options.metroHost) ? options.metroHost : `http://${options.metroHost}`);
      // An Expo tunnel forwards Metro only; port 8000 is not exposed by it.
      if (!/\.(?:exp\.direct|expo\.dev)$/.test(metro.hostname)) host = metro.hostname;
    } catch { /* Keep the platform default when Metro has no usable host. */ }
  }
  const api = explicit || `http://${host}:8000/api/v1`;
  const parsed = new URL(api);
  const origin = parsed.origin;
  parsed.port = '5011'; parsed.pathname = ''; parsed.search = ''; parsed.hash = '';
  const store = options.configuredStore?.trim().replace(/\/+$/, '') || parsed.origin;
  return { api, origin, store };
}
