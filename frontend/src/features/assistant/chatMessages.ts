import { ChatData, ConversationDetail } from '../../api/types';
import { productDraftImageUrl } from '../../api/sellerPilot';

export type Message = { id: string; role: 'user' | 'assistant'; text: string; imageUris?: string[]; response?: ChatData };

/** Decode only a complete answer envelope, including replies saved by older backends. */
export function assistantText(value: string): string {
  let text = value;
  for (let depth = 0; depth < 4; depth += 1) {
    let candidate = text.trim();
    const fenced = /^```(?:json)?\s*([\s\S]*?)\s*```$/i.exec(candidate);
    if (fenced?.[1] !== undefined) candidate = fenced[1].trim();
    if (!candidate.startsWith('{') && !candidate.startsWith('"')) break;
    let envelope: unknown;
    try {
      envelope = JSON.parse(candidate);
      if (typeof envelope === 'string') envelope = JSON.parse(envelope);
    } catch { break; }
    if (!envelope || typeof envelope !== 'object' || Array.isArray(envelope)
        || Object.keys(envelope).length !== 1 || !('answer' in envelope)
        || typeof envelope.answer !== 'string' || !envelope.answer.trim()) break;
    text = envelope.answer;
  }
  return text;
}

export function assistantMessage(data: ChatData): Message {
  const text = assistantText(data.answer);
  return { id: data.run_id + ':a', role: 'assistant', text,
    response: text === data.answer ? data : { ...data, answer: text } };
}

export function latestProductCards(messages: Message[]): Set<string> {
  const cards = new Set<string>(), seen = new Set<number>();
  for (const message of [...messages].reverse()) {
    const draft = message.response?.product_draft;
    if (!draft || seen.has(draft.id) || !['create_product_draft', 'update_product_draft', 'prepare_product_publish', 'publish_product'].includes(message.response?.tool || '')) continue;
    seen.add(draft.id); cards.add(message.id);
  }
  return cards;
}

/** Select just the photos added in this upload, including recovered responses. */
export function uploadedImageUris(data: ChatData): string[] | undefined {
  const draft = data.product_draft;
  if (!draft || draft.status === 'cancelled') return undefined;
  const urls = draft.preview_urls;
  const indices = data.facts?.image_indices;
  if (Array.isArray(indices) && indices.every(index => Number.isInteger(index) && index >= 0 && index < urls.length)) {
    return indices.length ? Array.from(new Set(indices as number[])).map(index => productDraftImageUrl(urls[index]!)) : undefined;
  }
  const start = data.facts?.image_start_index, count = data.facts?.new_image_count;
  const selected = typeof start === 'number' && Number.isInteger(start) && start >= 0
    && typeof count === 'number' && Number.isInteger(count) && count >= 0
    ? urls.slice(start, start + count) : urls;
  return selected.length ? selected.map(productDraftImageUrl) : undefined;
}

export function restoreMessages(turns: ConversationDetail['turns']): Message[] {
  // Upload is an internal request followed by the seller's actual caption.
  // Reopening history must not insert its temporary "what is the name?" reply.
  const uploads = new Set(turns.filter(turn => turn.response.tool === 'create_product_draft')
    .map(turn => turn.response.product_draft?.id));
  const hidden = new Set<number>(), linked = new Map<number, ChatData>();
  turns.forEach((turn, index) => {
    const next = turns[index + 1];
    if (turn.response.tool === 'create_product_draft' && turn.response.product_draft && next
        && next.response.tool !== 'create_product_draft'
        && next.response.product_draft?.id === turn.response.product_draft.id) {
      hidden.add(index); linked.set(index + 1, turn.response);
    }
  });
  const shown = new Set<number>();
  return turns.flatMap((turn, index): Message[] => {
    const draft = turn.response.product_draft;
    if (hidden.has(index)) return [];
    const upload = linked.get(index) || (turn.response.tool === 'create_product_draft' ? turn.response : null);
    const imageUris = upload ? uploadedImageUris(upload)
      : draft && !uploads.has(draft.id) && draft.status !== 'cancelled' && !shown.has(draft.id)
        ? draft.preview_urls.map(productDraftImageUrl) : undefined;
    if (draft && imageUris?.length) shown.add(draft.id);
    return [
      { id: turn.response.run_id + ':u', role: 'user', text: turn.message, imageUris },
      assistantMessage(turn.response),
    ];
  });
}
