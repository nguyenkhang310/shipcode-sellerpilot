export type LiveLanguage = 'vi' | 'en';
export type LivePreferences = { voice: 'male' | 'female'; language: LiveLanguage };

export const DEFAULT_LIVE_PREFERENCES: LivePreferences = { voice: 'female', language: 'vi' };

export const LIVE_TEXT = {
  vi: {
    connecting: 'Đang kết nối', reconnecting: 'Đang nối lại', buffering: 'Đang giữ lời bạn', openingMic: 'Đang bật micro', retry: 'Mở lại Live',
    uploading: 'Đang lưu ảnh', choosing: 'Đang chọn ảnh', speaking: 'Đang nói', interrupt: 'Ngắt lời',
    muted: 'Micro đã tắt', userSpeaking: 'Bạn đang nói', processing: 'Đang xử lý', listening: 'Đang nghe',
    send: 'Gửi lượt nói', addPhotos: 'Thêm ảnh', retryPhotos: 'Thử lưu ảnh lại', enableMic: 'Bật mic', disableMic: 'Tắt mic',
    finish: 'Kết thúc Live', published: 'Đã đăng sản phẩm', confirmPublish: 'Chờ bạn nói “xác nhận đăng”',
    confirmArchive: 'Nói “xác nhận xóa sản phẩm”',
    draft: 'Bản nháp sản phẩm', untitled: 'Sản phẩm mới', noPrice: 'Chưa có giá', stock: 'trong kho', photos: 'ảnh',
  },
  en: {
    connecting: 'Connecting', reconnecting: 'Reconnecting', buffering: 'Holding your audio', openingMic: 'Opening microphone', retry: 'Reconnect Live',
    uploading: 'Saving photos', choosing: 'Choosing photos', speaking: 'Speaking', interrupt: 'Interrupt',
    muted: 'Microphone muted', userSpeaking: 'You’re speaking', processing: 'Processing', listening: 'Listening',
    send: 'Send voice turn', addPhotos: 'Add photos', retryPhotos: 'Retry saving photos', enableMic: 'Unmute', disableMic: 'Mute',
    finish: 'End Live', published: 'Product published', confirmPublish: 'Say “confirm publish”',
    confirmArchive: 'Say “confirm product removal”',
    draft: 'Product draft', untitled: 'New product', noPrice: 'No price yet', stock: 'in stock', photos: 'photos',
  },
};

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
