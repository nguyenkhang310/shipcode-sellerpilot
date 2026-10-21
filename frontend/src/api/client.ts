import Constants from 'expo-constants';
import { Platform } from 'react-native';
import { ApiResponse } from './types';

import { resolveApiUrls } from './urls';
import { inExtension, extensionRequest } from '../integrations/extension';

const urls = resolveApiUrls({
  configuredApi: process.env.EXPO_PUBLIC_API_URL,
  configuredStore: process.env.EXPO_PUBLIC_STORE_URL,
  metroHost: Constants.expoConfig?.hostUri ?? Constants.expoGoConfig?.debuggerHost,
  nativeDevelopment: __DEV__ && Platform.OS !== 'web',
  android: Platform.OS === 'android',
});
export const API_URL = urls.api;
export const API_ORIGIN = urls.origin;
export const STORE_URL = urls.store;
export const productImageUrl = (value: string | null) => {
  if (!value) return undefined;
  if (value.startsWith('/static/')) return `${API_ORIGIN}/store-static/${value.slice('/static/'.length)}`;
  if (value.startsWith('/')) return STORE_URL + value;
  return value;
};

export class ApiError extends Error {
  constructor(public readonly status: number, message: string, public readonly code?: string) {
    super(message);
    this.name = 'ApiError';
  }
}

// Credentials remain in memory. Native persistence is owned by SecureStore;
// browser localStorage/sessionStorage must never receive this token.
let accessToken: string | null = null;
let unauthorized: (() => void) | undefined;
export const setAccessToken = (token: string | null) => { accessToken = token; };
export const onUnauthorized = (handler?: () => void) => { unauthorized = handler; };
export const privateMediaHeaders = (uri: string): Record<string, string> =>
  accessToken && uri.startsWith(API_URL + '/product-drafts/') ? { Authorization: 'Bearer ' + accessToken } : {};

export type ApiRequestOptions = RequestInit & {
  /** Local models loaded from an HDD can need considerably longer than normal API calls. */
  timeoutMs?: number;
};

/** One HTTP entry point; no platform credentials or demo admin key in the app. */
export async function apiRequest<T>(path: string, options: ApiRequestOptions = {}): Promise<ApiResponse<T>> {
  const { timeoutMs = 8000, ...requestOptions } = options;
  const controller = new AbortController();
  let timedOut = false;
  const cancel = () => controller.abort();
  if (options.signal?.aborted) cancel();
  options.signal?.addEventListener('abort', cancel, { once: true });
  const timeout = setTimeout(() => {
    timedOut = true;
    cancel();
  }, timeoutMs);
  try {
    const sentToken = accessToken;
    if (inExtension()) {
      try { return await extensionRequest(path, { ...requestOptions, headers: sentToken ? { Authorization: 'Bearer ' + sentToken } : undefined }, controller.signal) as ApiResponse<T>; }
      catch (error) {
        if (error instanceof Error && 'status' in error && error.status === 401 && !path.startsWith('/auth/') && sentToken === accessToken) unauthorized?.();
        if (error instanceof Error && 'status' in error) throw new ApiError(Number(error.status), error.message);
        throw error;
      }
    }
    const headers = new Headers(options.headers);
    headers.set('Accept', 'application/json');
    if (sentToken) headers.set('Authorization', 'Bearer ' + sentToken);
    const response = await fetch(`${API_URL}${path}`, { ...requestOptions, headers, signal: controller.signal });
    if (!response.ok) {
      let message = `API trả lỗi HTTP ${response.status}`;
      let code: string | undefined;
      try {
        const payload = await response.json() as { detail?: string | { message?: string; code?: string } };
        const detail = payload.detail;
        if (typeof detail === 'string') message = detail;
        if (typeof detail === 'object' && detail?.message) message = detail.message;
        if (typeof detail === 'object') code = detail?.code;
      } catch {
        // Keep the HTTP status message when the server does not return JSON.
      }
      if (response.status === 401 && !path.startsWith('/auth/') && sentToken === accessToken) unauthorized?.();
      throw new ApiError(response.status, message, code);
    }
    return await response.json() as ApiResponse<T>;
  } catch (error) {
    if (timedOut) {
      throw new ApiError(408, path === '/chat' ? 'AI phản hồi lâu hơn dự kiến. Bạn thử lại nhé.' : 'Kết nối mất quá nhiều thời gian. Vui lòng thử lại.');
    }
    throw error;
  } finally {
    clearTimeout(timeout);
    options.signal?.removeEventListener('abort', cancel);
  }
}
