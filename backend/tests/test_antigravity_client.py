import asyncio
import base64
import json
import shlex
import sys
from datetime import date
from pathlib import Path

import pytest

from app.ai.antigravity import AGENT, MODEL, AntigravityClient, check_policy, store_images
from app.ai.contracts import AIProviderError
from app.scripts.check_ai import synthetic_keyboard_png


def image():
    return {'type': 'file', 'mime': 'image/png',
            'url': 'data:image/png;base64,' + base64.b64encode(synthetic_keyboard_png()).decode()}


def fake_cli(tmp_path, mode='success'):
    observed = tmp_path / 'observed.json'
    source = tmp_path / 'fake_cli.py'
    source.write_text('''
import json,sys,time,uuid
from pathlib import Path
args=sys.argv[1:]
mode=MODE
def emit(d):
    print(json.dumps(d),flush=True)
if '/config' in args:
    emit({'status':'SUCCESS','command':{'data':{'config':{
        'useG1Credits':mode=='credit','allowNonWorkspaceAccess':False,
        'toolPermission':'request-review','permissions':None,'modelProvider':''}}}})
elif 'models' in args:
    print(MODEL+'\\tGemini',flush=True)
else:
    incoming=json.loads(sys.stdin.readline())
    payload=json.loads(incoming['message']['content'])
    Path(OBSERVED).write_text(json.dumps({'args':args,'payload':payload,'cwd':str(Path.cwd())}))
    if mode=='sleep': time.sleep(20)
    emit({'event':'init','init':{'model':MODEL if mode!='identity' else 'wrong',
        'agent':AGENT,'cwd':str(Path.cwd()),'permission_mode':'request-review'}})
    if mode=='tool':
        emit({'event':'step_update','step_update':{'step_type':'tool','state':'ACTIVE','tool_name':'run_command'}})
    if mode=='outside':
        emit({'event':'step_update','step_update':{'step_type':'tool','state':'DONE','tool_name':'view_file',
            'tool_info':{'parameters':{'AbsolutePath':'/etc/passwd'}}}})
    if mode!='skip_images':
        for path in payload.get('attached_images',[]):
            assert Path(path).read_bytes().startswith(b'\\x89PNG')
            emit({'event':'step_update','step_update':{'step_type':'tool','state':'DONE',
                'tool_name':'view_file','tool_info':{'parameters':{'AbsolutePath':path}}}})
    result={'status':'SUCCESS','conversation_id':str(uuid.uuid4()),'response':'Xin chào chủ shop.'}
    if '--json-schema' in args:
        schema=json.loads(args[args.index('--json-schema')+1])
        if 'intent' in schema['properties']:
            result['structured_output']={'intent':'change_price','sku':'A001','new_price_vnd':500000,
                'inventory_scope':None,'day':None,'low_stock_threshold':None}
            if mode=='bad_sku': result['structured_output']['sku']='A 001'
        elif 'extraction' in schema['properties']:
            result['structured_output']={'extraction':{'topic':'strategy'},
                'answer':'Đề xuất: ưu tiên xử lý đơn chờ.'}
        elif 'answer' in schema['properties']:
            result['structured_output']={'answer':'Xin chào chủ shop.'}
        else:
            result['structured_output']={'name':'Bàn phím Demo','description':'Bàn phím màu đen cho góc làm việc.',
                'category_id':4,'price_vnd':500000,'stock':8,'price_evidence':'5 xị','stock_evidence':'8 chiếc'}
        # CLI free text may include internal finish metadata; consume structured_output instead.
        result['response']='internal toolAction metadata'
        emit({'event':'step_update','step_update':{'step_type':'tool','state':'ACTIVE','tool_name':'finish'}})
    if mode in ('quota','auth'):
        result={'status':'ERROR','error':'429 quota exceeded' if mode=='quota' else 'authentication required'}
    if mode=='denied': result['denied_actions']=['write_file']
    emit({'event':'result','result':result})
''')
    # Fixed test constants precede the script; no shell interpolation of seller input.
    source.write_text('MODE=' + repr(mode) + '\nMODEL=' + repr(MODEL) + '\nAGENT=' + repr(AGENT)
                      + '\nOBSERVED=' + repr(str(observed)) + '\n' + source.read_text())
    executable = tmp_path / 'fake-agy'
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' '
                          + shlex.quote(str(source)) + ' "$@"\n')
    executable.chmod(0o700)
    return AntigravityClient(str(executable), timeout=10), observed


def test_cli_policy_requires_no_credit_and_reviewed_workspace_only():
    valid = {'useG1Credits': False, 'allowNonWorkspaceAccess': False,
             'toolPermission': 'request-review', 'modelProvider': '', 'permissions': None}
    check_policy(valid)
    for field, value in [('useG1Credits', True), ('useG1Credits', None),
                         ('allowNonWorkspaceAccess', True), ('toolPermission', 'always-proceed'),
                         ('modelProvider', 'gemini-api-key'), ('permissions', {'allow': ['command(*)']})]:
        with pytest.raises(AIProviderError, match='provider_rejected'):
            check_policy(dict(valid, **{field: value}))


def test_prepared_advice_passes_shop_facts_and_memory_in_one_structured_turn(tmp_path):
    provider, observed = fake_cli(tmp_path)
    async def run():
        return await provider.prepare_advice('Hôm nay ưu tiên gì?', history=[],
            context={'seller_preferences':{'target_audience':'sinh viên'}},
            facts={'tasks':{'pending_orders':2}})
    result = asyncio.run(run())
    assert result.extraction.topic == 'strategy' and 'đơn chờ' in result.answer
    payload = json.loads(observed.read_text())['payload']
    assert payload['shop_facts']['tasks']['pending_orders'] == 2
    assert payload['memory']['seller_preferences']['target_audience'] == 'sinh viên'


def test_image_decoder_keeps_all_six_and_rejects_remote_or_mismatched_images(tmp_path):
    paths = store_images(tmp_path, [image()] * 6)
    assert len(paths) == 6 and all(path.exists() for path in paths)
    for images in ([image()] * 7, [{'mime': 'image/png', 'url': 'https://example.test/image.png'}],
                   [{'mime': 'image/png', 'url': 'data:image/png;base64,@@@'}],
                   [{'mime': 'image/png', 'url': 'data:image/png;base64,' + base64.b64encode(b'not PNG').decode()}]):
        with pytest.raises(AIProviderError):
            store_images(tmp_path, images)


def test_real_subprocess_protocol_reads_six_images_and_returns_validated_copy(tmp_path):
    provider, observed = fake_cli(tmp_path)
    async def run():
        await provider.initialize()
        assert (await provider.check_health()).model_available
        return await provider.compose_listing(facts={'current_message':'Bán 5 xị, kho 8 chiếc'},
                                               history=[], images=[image()] * 6)
    data = json.loads(asyncio.run(run()))
    assert data['name'] == 'Bàn phím Demo' and data['price_vnd'] == 500000 and data['stock'] == 8
    record = json.loads(observed.read_text())
    assert len(record['payload']['attached_images']) == 6
    assert not Path(record['cwd']).exists()
    assert not any('Bán 5 xị' in argument for argument in record['args'])
    assert '--dangerously-skip-permissions' not in record['args']
    assert '--continue' not in record['args'] and '--conversation' not in record['args']


@pytest.mark.parametrize('mode,reason', [
    ('skip_images','invalid_response'), ('tool','tool_not_allowed'), ('outside','tool_not_allowed'),
    ('identity','invalid_response'), ('quota','provider_rate_limited'),
    ('auth','provider_rejected'), ('denied','tool_not_allowed'),
])
def test_cli_failures_never_accept_an_unread_image_or_unapproved_tool(tmp_path, mode, reason):
    provider, observed = fake_cli(tmp_path, mode)
    async def run():
        with pytest.raises(AIProviderError) as caught:
            await provider.compose_listing(facts={}, history=[], images=[image()])
        assert caught.value.reason == reason
        assert (await provider.check_health()).model_available is False
    asyncio.run(run())
    assert not Path(json.loads(observed.read_text())['cwd']).exists()


def test_cli_credit_opt_in_is_rejected_before_model_request(tmp_path):
    provider, observed = fake_cli(tmp_path, 'credit')
    async def run():
        with pytest.raises(AIProviderError, match='provider_rejected'):
            await provider.respond('Synthetic', history=[], facts={})
    asyncio.run(run())
    assert not observed.exists()


def test_classifier_rejects_invalid_parameters_without_leaking_validation_error(tmp_path):
    provider, _ = fake_cli(tmp_path, 'bad_sku')
    async def run():
        with pytest.raises(AIProviderError) as caught:
            await provider.classify('Đổi giá A001 thành 5 xị', today=date(2026,10,18))
        assert caught.value.reason == 'invalid_response'
        assert caught.value.stage == 'command_parameters'
        assert (await provider.check_health()).model_available is False
    asyncio.run(run())


def test_cli_timeout_stops_process_and_cleans_images(tmp_path):
    provider, observed = fake_cli(tmp_path, 'sleep')
    async def run():
        await provider.initialize()
        provider.timeout = 2
        with pytest.raises(AIProviderError, match='provider_timeout'):
            await provider.compose_listing(facts={}, history=[], images=[image()])
    asyncio.run(run())
    assert not Path(json.loads(observed.read_text())['cwd']).exists()


def test_cli_explicit_cancel_cleans_owned_process_and_temporary_images(tmp_path):
    provider, observed = fake_cli(tmp_path, 'sleep')
    async def run():
        task = asyncio.create_task(provider.compose_listing(facts={}, history=[], images=[image()]))
        async with asyncio.timeout(5):
            while not observed.exists():
                await asyncio.sleep(.02)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert not Path(json.loads(observed.read_text())['cwd']).exists()


def test_policy_cache_skips_unchanged_config_but_rechecks_changes_and_expiry(tmp_path, monkeypatch):
    provider, _ = fake_cli(tmp_path)
    stamp = [1]
    monkeypatch.setattr(provider, '_config_stamp', lambda: tuple(stamp))
    calls = []
    capture = provider._capture
    async def tracked(args, *a, **kw):
        calls.append(args[0])
        return await capture(args, *a, **kw)
    monkeypatch.setattr(provider, '_capture', tracked)
    async def run():
        await provider.initialize()
        await provider.respond('Chào', history=[], facts={})
        await provider.respond('Cảm ơn', history=[], facts={})
        assert calls.count('-p') == 1
        stamp[0] = 2
        await provider.respond('Chào', history=[], facts={})
        assert calls.count('-p') == 2
        provider._policy_checked_at -= 61
        await provider.respond('Chào', history=[], facts={})
        assert calls.count('-p') == 3
    asyncio.run(run())


def test_cached_policy_does_not_hide_credit_enabled_after_settings_change(tmp_path, monkeypatch):
    provider, observed = fake_cli(tmp_path)
    stamp = [1]
    monkeypatch.setattr(provider, '_config_stamp', lambda: tuple(stamp))
    async def run():
        await provider.initialize()
        stamp[0] = 2
        async def denied(*args, **kwargs):
            return json.dumps({'status':'SUCCESS','command':{'data':{'config':{
                'useG1Credits': True, 'allowNonWorkspaceAccess': False,
                'toolPermission':'request-review','modelProvider':'','permissions':None}}}})
        monkeypatch.setattr(provider, '_capture', denied)
        with pytest.raises(AIProviderError, match='provider_rejected'):
            await provider.respond('Chào', history=[], facts={})
    asyncio.run(run())
    assert not observed.exists()
