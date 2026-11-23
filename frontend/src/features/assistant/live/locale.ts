export type LiveLanguage = 'vi' | 'en';
export type LivePreferences = { voice: 'male' | 'female'; language: LiveLanguage };

export const DEFAULT_LIVE_PREFERENCES: LivePreferences = { voice: 'female', language: 'vi' };

export const LIVE_TEXT = {
  vi: {
    connecting: 'Đang kết nối', reconnecting: 'Đang nối lại', buffering: 'Đang giữ lời bạn', openingMic: 'Đang bật micro', retry: 'Mở lại Live',
    connectionTimeout: 'Kết nối Live quá lâu. Kiểm tra mạng rồi thử lại.',
    reconnectFailed: 'Mất kết nối Live. Bạn có thể mở lại để tiếp tục.',
    repeatAfterReconnect: 'Khi nối lại, bạn nói lại câu vừa rồi nhé.',
    uploading: 'Đang lưu ảnh', choosing: 'Đang chọn ảnh', speaking: 'Đang nói', interrupt: 'Ngắt lời',
    greeting: 'Đang chào',
    muted: 'Micro đã tắt', userSpeaking: 'Bạn đang nói', processing: 'Đang xử lý', listening: 'Đang nghe',
    send: 'Gửi lượt nói', addPhotos: 'Thêm ảnh', retryPhotos: 'Thử lưu ảnh lại', enableMic: 'Bật mic', disableMic: 'Tắt mic',
    finish: 'Kết thúc Live', published: 'Đã đăng sản phẩm', confirmPublish: 'Chờ bạn nói “xác nhận đăng”',
    confirmArchive: 'Nói “xác nhận xóa sản phẩm”',
    draft: 'Bản nháp sản phẩm', untitled: 'Sản phẩm mới', noPrice: 'Chưa có giá', stock: 'trong kho', photos: 'ảnh',
  },
  en: {
    connecting: 'Connecting', reconnecting: 'Reconnecting', buffering: 'Holding your audio', openingMic: 'Opening microphone', retry: 'Reconnect Live',
    connectionTimeout: 'Live took too long to connect. Check your connection and try again.',
    reconnectFailed: 'Live disconnected. Reopen it to continue.',
    repeatAfterReconnect: 'Please repeat your last sentence once Live reconnects.',
    uploading: 'Saving photos', choosing: 'Choosing photos', speaking: 'Speaking', interrupt: 'Interrupt',
    greeting: 'Greeting',
    muted: 'Microphone muted', userSpeaking: 'You’re speaking', processing: 'Processing', listening: 'Listening',
    send: 'Send voice turn', addPhotos: 'Add photos', retryPhotos: 'Retry saving photos', enableMic: 'Unmute', disableMic: 'Mute',
    finish: 'End Live', published: 'Product published', confirmPublish: 'Say “confirm publish”',
    confirmArchive: 'Say “confirm product removal”',
    draft: 'Product draft', untitled: 'New product', noPrice: 'No price yet', stock: 'in stock', photos: 'photos',
  },
};

const LIVE_PROVIDER_ENGLISH: Record<string, string> = {
  live_provider_billing: 'The available Gemini Live projects are out of prepaid credits. Check billing in AI Studio.',
  live_provider_rate_limited: 'Gemini Live has reached its usage limit. Try again later.',
  live_provider_rejected: 'Gemini rejected the API keys. Check Live API access in AI Studio.',
  live_provider_configuration: 'Gemini rejected the Live session configuration. Check model access in AI Studio.',
  live_provider_unavailable: 'Gemini Live is temporarily unavailable. Try again shortly.',
};

export function liveErrorMessage(language: LiveLanguage, code: unknown, fallback: string) {
  return language === 'en' && typeof code === 'string' && Object.prototype.hasOwnProperty.call(LIVE_PROVIDER_ENGLISH, code)
    ? LIVE_PROVIDER_ENGLISH[code]! : fallback;
}

export function parseLivePreferences(raw: string | null): LivePreferences {
  try {
    const saved = raw ? JSON.parse(raw) : null;
    return {
      voice: saved?.voice === 'male' || saved?.voice === 'female' ? saved.voice
        : saved?.language === 'en' ? 'male' : DEFAULT_LIVE_PREFERENCES.voice,
      language: saved?.language === 'en' ? 'en' : 'vi',
    };
  } catch {
    return DEFAULT_LIVE_PREFERENCES;
  }
}
