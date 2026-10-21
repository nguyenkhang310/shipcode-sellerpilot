import { apiRequest, API_URL } from './client';
import { ChatData, PriceProposal, ProductDraft, ProductEditProposal, ManagementData, StorePage, StoreProduct, StoreOrder, OrderDetail, OrderChanges, ConversationSummary, ConversationDetail } from './types';
import { createMessageId, recoverChatRequest } from './chatRequests';
import type { ProductDetail, ProductChanges } from './types';

export function decideProductEdit(id: number, decision: 'confirm' | 'reject') {
  return apiRequest<ProductEditProposal>(`/product-edits/${id}/${decision}`, { method: 'POST' });
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function sendSellerMessage(message: string, signal?: AbortSignal, conversationId?: string | null, requestId = createMessageId(), retry = false) {
  if (retry) {
    const recovered = await recoverChatRequest(requestId, signal);
    if (recovered) return recovered;
  }
  return apiRequest<ChatData>('/chat', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({ message, conversation_id: conversationId || null, request_id: requestId }),
    signal,
    // The first inference can include loading Qwen from the external HDD.
    timeoutMs: 320_000,
  });
}

export const getManagement = (days: number, signal?: AbortSignal, date?: string | null) => apiRequest<ManagementData>('/management/dashboard?' + new URLSearchParams({days: String(days), ...(date ? {date} : {})}), { signal });
export const getProduct = (id: number, signal?: AbortSignal) => apiRequest<ProductDetail>('/management/products/' + id, {signal});
export const updateProduct = (id: number, changes: ProductChanges, version: string, requestId: string, variantId: number | null) => apiRequest<ProductDetail>('/management/products/' + id, {
  method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify({...changes, expected_version: version, request_id: requestId, variant_id: variantId}), timeoutMs: 20000,
});
export const getProducts = (q = '', low = false, offset = 0, signal?: AbortSignal) => apiRequest<StorePage<StoreProduct>>('/management/products?' + new URLSearchParams({ q, low: String(low), offset: String(offset), sort: 'newest' }), { signal });
export const getOrders = (status = 'all', q = '', offset = 0, signal?: AbortSignal) => apiRequest<StorePage<StoreOrder>>('/management/orders?' + new URLSearchParams({ status, q, offset: String(offset) }), { signal });
export const getOrder = (id: number, signal?: AbortSignal) => apiRequest<OrderDetail>('/management/orders/' + id, {signal});
export const updateOrder = (id: number, changes: OrderChanges, version: string, requestId: string) => apiRequest<OrderDetail>('/management/orders/' + id, {
  method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify({...changes, expected_version: version, request_id: requestId}), timeoutMs: 20000,
});
export const getConversations = (signal?: AbortSignal) => apiRequest<{ items: ConversationSummary[] }>('/conversations', { signal });
export const getConversation = (id: string, signal?: AbortSignal) => apiRequest<ConversationDetail>('/conversations/' + encodeURIComponent(id), { signal });
export const pinConversation = (id: string, isPinned: boolean) => apiRequest<{ id: string; is_pinned: boolean }>('/conversations/' + encodeURIComponent(id), { method: 'PATCH', headers: JSON_HEADERS, body: JSON.stringify({ is_pinned: isPinned }) });
export const deleteConversation = (id: string) => apiRequest<{ id: string; deleted: boolean }>('/conversations/' + encodeURIComponent(id), { method: 'DELETE' });

export async function decidePriceProposal(
  proposalId: number,
  decision: 'confirm' | 'reject',
  signal?: AbortSignal,
) {
  return apiRequest<PriceProposal>(`/proposals/${proposalId}/${decision}`, {
    method: 'POST',
    signal,
    timeoutMs: 20_000,
  });
}

export type PickedProductImage = { uri: string; fileName?: string | null; mimeType?: string | null; base64?: string | null };

export async function uploadProductImages(
  images: PickedProductImage[],
  conversationId?: string | null,
  signal?: AbortSignal,
  requestId = createMessageId(),
) {
  if (!images.length || images.length > 6 || images.some(image => !image.base64)) {
    throw new Error('product_image_gallery_invalid');
  }
  return apiRequest<ChatData>('/product-drafts/images-data', {
    method: 'POST',
    headers: JSON_HEADERS,
    body: JSON.stringify({
      images_base64: images.map(image => image.base64),
      request_id: requestId,
      conversation_id: conversationId || null,
    }),
    signal,
    timeoutMs: 90_000,
  });
}

export function decideProductDraft(
  draftId: number,
  decision: 'publish' | 'cancel',
  signal?: AbortSignal,
) {
  return apiRequest<ProductDraft>(`/product-drafts/${draftId}/${decision}`, {
    method: 'POST', signal, timeoutMs: 30_000,
  });
}

export const productDraftImageUrl = (path: string) => path.startsWith('http') || path.startsWith('data:image/') ? path : API_URL + path;
