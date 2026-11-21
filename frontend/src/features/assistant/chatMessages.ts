import { ChatData, ChatReport, ConversationDetail } from '../../api/types';
import { productDraftImageUrl } from '../../api/sellerPilot';
import type { LiveShopResult } from './live/LiveConversation';
import type { LiveLanguage } from './live/locale';
import { liveMessageKey, type LiveCaption } from './live/timeline';

export type Message = {
  id: string; role: 'user' | 'assistant'; text: string; imageUris?: string[]; response?: ChatData;
  livePending?: boolean; liveResults?: LiveShopResult[];
};

export function liveShopResults(data?: ChatData): LiveShopResult[] {
  const results = data?.facts?.live_results;
  return Array.isArray(results) ? results : [];
}

/** Keep the assistant row's key from the first caption or tool result through saving. */
export function chatTimeline(saved: Message[], captions: LiveCaption[], results: LiveShopResult[]): Message[] {
  if (!captions.length && !results.length) return saved;
  const savedIds = new Set(saved.map(message => message.id));
  const savedResults = new Set(saved.flatMap(message => liveShopResults(message.response).map(result => result.id)));
  const turns = new Map<string, { user?: string; assistant?: string; results: LiveShopResult[] }>();
  const turn = (id: string) => {
    let value = turns.get(id);
    if (!value) { value = { results: [] }; turns.set(id, value); }
    return value;
  };
  for (const caption of captions) {
    if (!savedIds.has(liveMessageKey(caption.turnId, caption.role))) turn(caption.turnId)[caption.role] = caption.text;
  }
  for (const [index, result] of results.entries()) {
    if (result.id && savedResults.has(result.id)) continue;
    const id = result.turn_id || 'result:' + (result.id ?? index);
    if (!savedIds.has(liveMessageKey(id, 'assistant'))) turn(id).results.push(result);
  }
  return [...saved, ...Array.from(turns).flatMap(([id, pending]): Message[] => {
    const rows: Message[] = [];
    if (pending.user) rows.push({ id: liveMessageKey(id, 'user'), role: 'user', text: pending.user, livePending: true });
    if (pending.results.length || pending.assistant && pending.user) rows.push({
      id: liveMessageKey(id, 'assistant'), role: 'assistant', text: pending.assistant || '',
      livePending: true, liveResults: pending.results,
    });
    return rows;
  })];
}

function reportKey(report: ChatReport) {
  // Repeated tool calls can refresh a snapshot during a single turn.
  return JSON.stringify([report.title, report.subtitle, report.metrics.map(metric => [metric.label, metric.unit]),
    report.charts.map(chart => [chart.title, chart.kind, chart.unit]), report.table?.title]);
}

export function assistantContent(message: Message) {
  const response = message.response;
  const results = message.liveResults ?? liveShopResults(response);
  const reports = new Map<string, { key: string; report: ChatReport; language?: LiveLanguage }>();
  const responseLanguage = response?.facts?.live_language === 'en' ? 'en' : undefined;
  if (response?.report) {
    const key = reportKey(response.report);
    reports.set(key, { key, report: response.report, language: responseLanguage });
  }
  for (const result of results) {
    if (!result.report) continue;
    const key = reportKey(result.report);
    reports.set(key, { key, report: result.report, language: result.language ?? responseLanguage });
  }
  const summaryResult = results.findLast(result => result.report && result.sales_context);
  const sales = summaryResult?.sales_context ?? response?.facts;
  const detailed = results.filter(result => result.spoken_summary && result.language !== 'en')
    .map(result => assistantText(result.answer))
    .filter(answer => answer.trim() && answer.trim() !== message.text.trim());
  const originalText = message.text.trim() || assistantText(results[0]?.answer ?? '').trim();
  const preferences = response?.facts?.seller_preferences as { response_style?: string } | undefined;
  const knownSummary = summaryResult || (response?.tool === 'get_shop_summary' && response.provider === 'deterministic_parser');
  const compactSummary = knownSummary && reports.size === 1 && !sales?.sales_metric && !sales?.compare_yesterday
    && !detailed.length && !preferences?.response_style;
  const text = compactSummary
    ? summaryResult?.language === 'en' ? 'Here’s how your shop performed during this period.'
      : 'Mình đã tổng hợp kết quả bán hàng trong kỳ bạn hỏi.'
    : originalText;
  return { text, originalText, details: [...new Set(detailed.filter(answer => answer.trim() !== originalText))],
    reports: [...reports.values()], results };
}

export function messageKey(data: ChatData, role: Message['role']) {
  const id = data.facts?.live_turn_id;
  return typeof id === 'string' ? liveMessageKey(id, role) : data.run_id + (role === 'user' ? ':u' : ':a');
}

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
  return { id: messageKey(data, 'assistant'), role: 'assistant', text,
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
      { id: messageKey(turn.response, 'user'), role: 'user', text: turn.message, imageUris },
      assistantMessage(turn.response),
    ];
  });
}
