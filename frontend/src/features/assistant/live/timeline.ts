export type LiveCaption = {
  turnId: string;
  role: 'user' | 'assistant';
  text: string;
  final?: boolean;
};

export function liveMessageKey(turnId: string, role: LiveCaption['role']) {
  return 'live:' + turnId + (role === 'user' ? ':u' : ':a');
}

export function upsertCaption(items: LiveCaption[], caption: LiveCaption): LiveCaption[] {
  const index = items.findIndex(item => item.turnId === caption.turnId && item.role === caption.role);
  if (index >= 0) {
    if (items[index]?.text === caption.text) return items;
    return items.map((item, i) => i === index ? caption : item);
  }
  // A final input transcript may arrive after the first assistant words.
  const assistant = caption.role === 'user'
    ? items.findIndex(item => item.turnId === caption.turnId && item.role === 'assistant') : -1;
  if (assistant >= 0) return [...items.slice(0, assistant), caption, ...items.slice(assistant)];
  return [...items, caption].slice(-8);
}
