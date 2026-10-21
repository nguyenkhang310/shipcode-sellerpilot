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

// A durable failed record is terminal even when its business-specific code
// differs from chat_failed (for example a shop database outage).
class EndedChatRequestError extends ApiError {}

export const isTerminalChatError = (error: unknown): error is ApiError =>
  error instanceof EndedChatRequestError || error instanceof ApiError && (
    error.status === 422 || error.status === 413 ||
    ['chat_cancelled', 'chat_interrupted', 'chat_failed', 'chat_timeout', 'conversation_deleted', 'active_product_draft'].includes(error.code || ''));

export async function recoverChatRequest(id: string, signal?: AbortSignal) {
  try {
    const { data } = await getChatRequest(id, signal);
    if (data.status === 'completed' && data.response) return data.response;
    if (data.status === 'cancelled') throw new EndedChatRequestError(409, 'Tin nhắn đã được dừng.', 'chat_cancelled');
    if (data.error) {
      const detail = data.error.detail;
      const ErrorType = data.status === 'failed' ? EndedChatRequestError : ApiError;
      throw new ErrorType(data.error.status,
        typeof detail === 'string' ? detail : detail.message || 'Yêu cầu đã dừng.',
        typeof detail === 'string' ? undefined : detail.code);
    }
    return null; // Re-POST joins the running request; it does not start another.
  } catch (error) {
    if (error instanceof ApiError && error.status === 404 && !(error instanceof EndedChatRequestError)) return null;
    throw error;
  }
}
