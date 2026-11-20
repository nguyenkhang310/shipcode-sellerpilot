"""Persist completed Live turns in the existing seller chat history."""
import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import text

from app.ai.money import plain
from app.models.agent_run import AgentRun
from app.services.auth import verify_seller
from app.services.conversation_state import ensure_conversation_open
from app.services.conversations import conversation_memory, conversation_product, history_messages, turn_data
from app.services.live_language import merge_transcript, REPEAT_QUESTION


@dataclass
class SpokenTurn:
    id: str
    user: str
    assistant: str
    results: list[dict]
    decision: tuple | None
    delegated: int | None
    product_selection: dict


class LiveHistory:
    def __init__(self, state, token, conversation_id, model, language='vi'):
        self.state = state
        self.token = token
        self.conversation_id = str(conversation_id)
        self.model = model
        self.language = language
        self.turn_id = str(uuid4())
        self.unclear = False
        self.user = self.assistant = ''
        self.results = []
        self.delegated: int | None = None
        self.decision = None
        self.product_selection = {}
        self.contextual_advice: dict | None = None

    def initial_context(self):
        shop = self.state.shop_repository
        with self.state.session_factory() as session:
            verify_seller(shop, session, self.token)
            ensure_conversation_open(session, shop.seller_shop_slug or 'local', self.conversation_id)
            runs, since = conversation_memory(session, shop, self.conversation_id)
            messages = [{**row, 'content': row['content'][:420]} for row in history_messages(runs[-4:])]
            facts = conversation_product(session, shop, self.conversation_id, runs, since)
        selected = facts.get('selected_product')
        if selected and selected.get('found') is not False:
            focus = {key: selected[key] for key in ('sku', 'product_name', 'price_vnd', 'stock') if key in selected}
        else:
            draft = facts.get('draft_context')
            focus = ({'product_name': draft['name'], 'price_vnd': draft['selling_price_vnd'],
                      'stock': draft['stock'], 'status': 'draft'} if draft and draft['name'] else {})
        return messages, focus

    def transcript(self, role, value, final=False):
        attr, limit = ('user', 4000) if role == 'user' else ('assistant', 6000)
        previous = getattr(self, attr)
        merged = merge_transcript(previous, value, final=final)
        setattr(self, attr, merged[:limit])

    def result(self, result, facts):
        if len(self.results) < 4:
            self.results.append(result)
        selection = {key: facts[key] for key in ('selected_product', 'sku', 'found', 'items') if key in facts}
        if selection:
            self.product_selection = selection

    def take(self):
        user, assistant, results = self.user.strip(), self.assistant.strip(), self.results
        delegated, decision, unclear = self.delegated, self.decision, self.unclear
        selection = self.product_selection
        advice = self.contextual_advice
        identifier = self.turn_id
        self.turn_id = str(uuid4())
        self.user = self.assistant = ''
        self.results = []
        self.delegated = None
        self.decision = None
        self.unclear = False
        self.product_selection = {}
        self.contextual_advice = None
        user = user or (results[0]['question'] if results else '')
        if not user and not delegated:
            return None
        if unclear and not decision:
            user, assistant = 'Lời nói chưa rõ', REPEAT_QUESTION
        elif decision:
            assistant = decision[2]
        elif advice:
            facts = advice.get('facts', {})
            focus = (facts.get('business_advisory') or {}).get('focus_product') or {}
            name = focus.get('name')
            if facts.get('product_reference_missing'):
                assistant = (advice['answer'] if self.language == 'vi'
                             else 'Which product would you like to work on? You can say its name or SKU.')
            elif name and assistant and plain(name).casefold() not in plain(assistant).casefold():
                assistant = f'**{name}**\n\n{assistant}'
            elif not assistant and not delegated:
                assistant = advice.get('answer') or advice.get('message') or ''
        elif not assistant and not delegated:
            assistant = ('\n\n'.join(result['answer'] for result in results) if results else
                         'Live ended before a reply.' if self.language == 'en' else 'Phiên Live đã kết thúc trước khi có câu trả lời.')
        return SpokenTurn(identifier, user, assistant, results, decision, delegated, selection)

    def save(self, pending: SpokenTurn):
        shop = self.state.shop_repository
        tenant = shop.seller_shop_slug or 'local'
        facts = {'voice': True, 'live_turn_id': pending.id, 'live_language': self.language, 'live_results': pending.results}
        if pending.product_selection:
            facts['live_product_selection'] = pending.product_selection
        order = next((result['order_id'] for result in pending.results if result.get('order_id')), None)
        if order:
            facts['order_action'] = {'id': order}
            facts['order_lookup'] = {'id': order}
        with self.state.session_factory() as session:
            if session.bind.dialect.name == 'sqlite':
                session.execute(text('BEGIN IMMEDIATE'))
            verify_seller(shop, session, self.token)
            ensure_conversation_open(session, tenant, self.conversation_id)
            run = session.get(AgentRun, pending.delegated) if pending.delegated else None
            if run and run.conversation_id == self.conversation_id and run.shop_slug == tenant:
                facts = {**json.loads(run.facts_json), **facts}
                # Keep the original tool instruction for follow-ups and show the
                # words actually spoken in the voice timeline.
                if pending.user:
                    facts['live_spoken_message'] = pending.user
                if pending.assistant:
                    facts['live_spoken_answer'] = pending.assistant[:6000]
            else:
                run = AgentRun(conversation_id=self.conversation_id, shop_slug=tenant,
                    message=pending.user, answer=pending.assistant[:6000], intent='unknown', mode='ai', status='completed',
                    provider='gemini', model=self.model, tool_name='live_conversation', elapsed_ms=0)
            if pending.decision:
                kind, identifier, _ = pending.decision
                if kind in ('publish', 'cancel_draft'):
                    run.product_draft_id = identifier
                    if kind == 'publish' and not pending.delegated:
                        run.tool_name = 'publish_product'
                elif kind == 'price':
                    run.proposal_id = identifier
                elif kind == 'edit':
                    run.product_edit_proposal_id = identifier
            run.facts_json = json.dumps(facts, ensure_ascii=False)
            session.add(run)
            session.commit()
            return turn_data(session, run)
