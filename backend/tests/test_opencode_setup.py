import asyncio
import struct
import zlib

import pytest

from app.ai.factory import opencode_version
from app.scripts.check_ai import synthetic_keyboard_png


@pytest.mark.parametrize('version,valid', [('1.18.30', True), ('1.18.34', True), ('2.0.32', False), ('unknown', False)])
def test_server_protocol_check_rejects_incompatible_cli(monkeypatch, version, valid):
    class Process:
        returncode = 0
        async def communicate(self):
            return (version + '\n').encode(), None
    async def spawn(*args, **kwargs):
        assert args == ('synthetic-opencode', '--version')
        return Process()
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
    if valid:
        assert asyncio.run(opencode_version('synthetic-opencode')) == version
    else:
        with pytest.raises(RuntimeError, match='OpenCode 1.x'):
            asyncio.run(opencode_version('synthetic-opencode'))


def test_cancelling_version_probe_cleans_child_process(monkeypatch):
    async def run():
        started = asyncio.Event()
        class Process:
            returncode = None
            killed = False
            async def communicate(self):
                started.set()
                await asyncio.Event().wait()
            def kill(self):
                self.killed = True
            async def wait(self):
                self.returncode = -9
        process = Process()
        async def spawn(*args, **kwargs):
            return process
        monkeypatch.setattr(asyncio, 'create_subprocess_exec', spawn)
        task = asyncio.create_task(opencode_version('synthetic-opencode'))
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert process.killed and process.returncode == -9
    asyncio.run(run())


def test_diagnostic_image_is_a_valid_self_contained_png():
    image = synthetic_keyboard_png()
    assert image.startswith(b'\x89PNG\r\n\x1a\n')
    offset, compressed = 8, b''
    while offset < len(image):
        size = struct.unpack('!I', image[offset:offset + 4])[0]
        kind = image[offset + 4:offset + 8]
        data = image[offset + 8:offset + 8 + size]
        crc = struct.unpack('!I', image[offset + 8 + size:offset + 12 + size])[0]
        assert crc == zlib.crc32(kind + data)
        if kind == b'IHDR':
            assert struct.unpack('!2I5B', data) == (384, 200, 8, 2, 0, 0, 0)
        elif kind == b'IDAT':
            compressed += data
        offset += size + 12
    assert len(zlib.decompress(compressed)) == (384 * 3 + 1) * 200


@pytest.mark.parametrize('force', [True, False])
def test_windows_cleanup_uses_child_process_methods(monkeypatch, force):
    from types import SimpleNamespace
    from app.ai import factory
    actions = []
    process = SimpleNamespace(terminate=lambda: actions.append('terminate'), kill=lambda: actions.append('kill'))
    monkeypatch.setattr(factory, 'os', SimpleNamespace(name='nt'))
    factory.signal_opencode(process, force=force)
    assert actions == (['kill'] if force else ['terminate'])
