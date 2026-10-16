import { ChatData, ConversationDetail } from '../../api/types';
import { productDraftImageUrl } from '../../api/sellerPilot';

export type Message = { id: string; role: 'user' | 'assistant'; text: string; imageUris?: string[]; response?: ChatData };

export function latestProductCards(messages: Message[]): Set<string> {
  const cards = new Set<string>(), seen = new Set<number>();
  for (const message of [...messages].reverse()) {
    const draft = message.response?.product_draft;
    if (!draft || seen.has(draft.id) || !['create_product_draft', 'update_product_draft', 'prepare_product_publish', 'publish_product'].includes(message.response?.tool || '')) continue;
    seen.add(draft.id); cards.add(message.id);
  }
  return cards;
}

export function restoreMessages(turns: ConversationDetail['turns']): Message[] {
  // Upload is an internal request followed by the seller's actual caption.
  // Reopening history must not insert its temporary "what is the name?" reply.
  const followed = new Set(turns.filter(turn => turn.response.tool !== 'create_product_draft')
    .map(turn => turn.response.product_draft?.id).filter(id => id !== undefined));
  const shown = new Set<number>();
  return turns.flatMap((turn): Message[] => {
    const draft = turn.response.product_draft;
    if (draft && turn.response.tool === 'create_product_draft' && followed.has(draft.id)) return [];
    const imageUris = draft && draft.status !== 'cancelled' && !shown.has(draft.id)
      ? draft.preview_urls.map(productDraftImageUrl) : undefined;
    if (draft) shown.add(draft.id);
    return [
      { id: turn.response.run_id + ':u', role: 'user', text: turn.message, imageUris },
      { id: turn.response.run_id + ':a', role: 'assistant', text: turn.response.answer, response: turn.response },
    ];
  });
}
