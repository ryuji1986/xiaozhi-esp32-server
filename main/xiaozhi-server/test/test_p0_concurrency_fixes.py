import os
import sys
import queue
import types
import importlib
import asyncio


def _prepare_env():
    os.makedirs("data", exist_ok=True)
    cfg = "data/.config.yaml"
    if not os.path.exists(cfg):
        with open(cfg, "w", encoding="utf-8") as f:
            f.write("server:\n  ip: 0.0.0.0\n")
    sys.modules.setdefault(
        "opuslib_next",
        types.SimpleNamespace(Encoder=object, Decoder=object, APPLICATION_AUDIO=2049, constants=types.SimpleNamespace(APPLICATION_AUDIO=2049)),
    )


class DummyLogger:
    def bind(self, **kwargs):
        return self

    def warning(self, *args, **kwargs):
        return None


def _get_connection_handler_class():
    _prepare_env()
    mod = importlib.import_module("core.connection")
    return mod.ConnectionHandler


def test_asr_queue_drop_oldest_when_full():
    ConnectionHandler = _get_connection_handler_class()
    conn = ConnectionHandler.__new__(ConnectionHandler)
    conn.asr_audio_queue_maxsize = 2
    conn.asr_audio_queue_drop_oldest = True
    conn.asr_audio_queue = queue.Queue(maxsize=2)
    conn.logger = DummyLogger()

    conn._enqueue_asr_audio(b"a")
    conn._enqueue_asr_audio(b"b")
    conn._enqueue_asr_audio(b"c")

    assert conn.asr_audio_queue.qsize() == 2
    assert conn.asr_audio_queue.get_nowait() == b"b"
    assert conn.asr_audio_queue.get_nowait() == b"c"


def test_asr_queue_drop_new_when_full():
    ConnectionHandler = _get_connection_handler_class()
    conn = ConnectionHandler.__new__(ConnectionHandler)
    conn.asr_audio_queue_maxsize = 2
    conn.asr_audio_queue_drop_oldest = False
    conn.asr_audio_queue = queue.Queue(maxsize=2)
    conn.logger = DummyLogger()

    conn._enqueue_asr_audio(b"a")
    conn._enqueue_asr_audio(b"b")
    conn._enqueue_asr_audio(b"c")

    assert conn.asr_audio_queue.qsize() == 2
    assert conn.asr_audio_queue.get_nowait() == b"a"
    assert conn.asr_audio_queue.get_nowait() == b"b"


def test_openai_tts_uses_async_http_client(monkeypatch):
    _prepare_env()
    TTSProvider = importlib.import_module("core.providers.tts.openai").TTSProvider
    cfg = {
        "api_key": "k",
        "model": "tts-1",
        "voice": "alloy",
        "format": "wav",
        "request_timeout": 5,
        "max_concurrency": 2,
    }
    provider = TTSProvider(cfg, delete_audio_file=True)

    called = {"post": 0}

    class FakeResponse:
        status_code = 200
        content = b"wavbytes"
        text = "ok"

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def post(self, *args, **kwargs):
            called["post"] += 1
            return FakeResponse()

    monkeypatch.setattr("core.providers.tts.openai.httpx.AsyncClient", FakeClient)

    out = asyncio.run(provider.text_to_speak("hello", None))
    assert out == b"wavbytes"
    assert called["post"] == 1
