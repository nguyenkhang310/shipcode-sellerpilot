"""Keep complete recent seller messages within a predictable prompt budget."""


def bounded_history(rows, *, budget=18000, turns=24, assistant_limit=2000):
    selected, used = [], 0
    for row in reversed(rows[-turns:]):
        role = row.get('role')
        if role not in ('user', 'assistant') or not isinstance(row.get('content'), str):
            continue
        content = row['content'][:4000 if role == 'user' else assistant_limit]
        if used + len(content) > budget:
            break
        selected.append({'role': role, 'content': content})
        used += len(content)
    return list(reversed(selected))
