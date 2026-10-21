import { apiRequest, ApiError } from './client';
import { ChatData } from './types';

export type ChatRequestState = {
  request_id: string;
  conversation_id: string | null;
  status: 'queued' | 'running' | 'completed' | 'cancelled' | 'failed';
  response: { data: ChatData } | null;
  error: { status: number; detail: string | { code?: string; message?: string } } | null;
};

// This identifies messages, not credentials. It remains stable across retries.
export function createMessageId(): string {
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, character => {
    const value = Math.floor(Math.random() * 16);
    return (character === 'x' ? value : (value & 3) | 8).toString(16);
  });
}

export const getChatRequest = (id: string, signal?: AbortSignal) =>
  apiRequest<ChatRequestState>(`/chat/requests/${encodeURIComponent(id)}`, { signal });

export const cancelChatRequest = (id: string) =>
  apiRequest<ChatRequestState>(`/chat/requests/${encodeURIComponent(id)}/cancel`, {
    method: 'POST', timeoutMs: 20_000,
  });

export const isTerminalChatError = (error: unknown): error is ApiError =>
  error instanceof ApiError && ['chat_cancelled', 'chat_interrupted', 'chat_failed', 'chat_timeout', 'conversation_deleted'].includes(error.code || '');

export async function recoverChatRequest(id: string, signal?: AbortSignal) {
  try {
    const { data } = await getChatRequest(id, signal);
    if (data.status === 'completed' && data.response) return data.response;
    if (data.status === 'cancelled') throw new ApiError(409, 'Tin nhắn đã được dừng.', 'chat_cancelled');
    if (data.error) {
      const detail = data.error.detail;
      throw new ApiError(data.error.status,
        typeof detail === 'string' ? detail : detail.message || 'Yêu cầu đã dừng.',
        typeof detail === 'string' ? undefined : detail.code);
    }
    return null; // Re-POST joins the running request; it does not start another.
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) return null;
    throw error;
  }
}
