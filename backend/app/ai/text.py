"""Decode a complete answer envelope without rewriting ordinary seller text."""
import json
import re

RESPONSE_FIELDS = {'tool', 'tool_arguments', 'facts', 'intent', 'proposal', 'product_draft', 'run_id'}


def reply_format_issue(value: str) -> str | None:
    if not value.strip():
        return 'empty_answer'
    candidate = value.strip()
    fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', candidate, re.I)
    try:
        envelope = json.loads(fenced.group(1) if fenced else candidate)
    except (ValueError, TypeError):
        if re.match(r'^(?:```(?:json)?\s*)?\{\s*"(?:answer|tool|facts|intent|tool_arguments)"\s*:', candidate, re.I):
            return 'invalid_answer_envelope'
        return None
    if isinstance(envelope, str) and not envelope.strip():
        return 'empty_answer'
    if isinstance(envelope, dict) and set(envelope) == {'answer'}:
        if not isinstance(envelope['answer'], str) or not envelope['answer'].strip():
            return 'invalid_answer_envelope'
    elif isinstance(envelope, dict) and RESPONSE_FIELDS.intersection(envelope):
        return 'raw_tool_payload'
    return None


def conversational_text(value: str) -> str:
    """Keep one copy when a provider repeats the same paragraph consecutively."""
    text = assistant_text(value).strip()
    if '```' in text:
        return text
    parts = re.split(r'\n[ \t]*\n+', text)
    return '\n\n'.join(part for index, part in enumerate(parts)
                       if not index or parts[index - 1].strip() != part.strip())


def assistant_text(value: str) -> str:
    """Some CLI outputs nest serialized ChatAnswer inside its answer field.

    Decode only complete, answer-only objects (including JSON fences/string
    encoding). Never strip arbitrary object fields or replace literal escapes
    in plain prose, code examples or seller instructions.
    """
    text = value
    for _ in range(4):
        candidate = text.strip()
        fenced = re.fullmatch(r'```(?:json)?\s*([\s\S]*?)\s*```', candidate, re.I)
        if fenced:
            candidate = fenced.group(1).strip()
        if not candidate.startswith(('{', '"')):
            break
        try:
            envelope = json.loads(candidate)
            if isinstance(envelope, str):
                envelope = json.loads(envelope)
        except (ValueError, TypeError):
            break
        if (not isinstance(envelope, dict) or set(envelope) != {'answer'}
                or not isinstance(envelope['answer'], str) or not envelope['answer'].strip()):
            break
        text = envelope['answer']
    return text
