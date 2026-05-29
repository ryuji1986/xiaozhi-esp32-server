import asyncio
import httpx
from core.utils.util import check_model_key
from core.providers.tts.base import TTSProviderBase
from config.logger import setup_logging

TAG = __name__
logger = setup_logging()


class TTSProvider(TTSProviderBase):
    TTS_PARAM_CONFIG = [
        ("ttsRate", "speed", 0.25, 4, 1, lambda v: round(float(v), 2)),
    ]
    _global_semaphore = None
    _semaphore_lock = asyncio.Lock()

    def __init__(self, config, delete_audio_file):
        super().__init__(config, delete_audio_file)
        self.api_key = config.get("api_key")
        self.api_url = config.get("api_url", "https://api.openai.com/v1/audio/speech")
        self.model = config.get("model", "tts-1")
        if config.get("private_voice"):
            self.voice = config.get("private_voice")
        else:
            self.voice = config.get("voice", "alloy")
        self.audio_file_type = config.get("format", "wav")

        speed = config.get("speed", "1.0")
        self.speed = float(speed) if speed else 1.0

        self._apply_percentage_params(config)

        self.output_file = config.get("output_dir", "tmp/")
        self.request_timeout = float(config.get("request_timeout", 30))
        self.max_concurrency = int(config.get("max_concurrency", 64))
        model_key_msg = check_model_key("TTS", self.api_key)
        if model_key_msg:
            logger.bind(tag=TAG).error(model_key_msg)

    async def _get_semaphore(self):
        if TTSProvider._global_semaphore is None:
            async with TTSProvider._semaphore_lock:
                if TTSProvider._global_semaphore is None:
                    TTSProvider._global_semaphore = asyncio.Semaphore(self.max_concurrency)
        return TTSProvider._global_semaphore

    async def text_to_speak(self, text, output_file):
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        data = {
            "model": self.model,
            "input": text,
            "voice": self.voice,
            "response_format": self.audio_file_type,
            "speed": self.speed,
        }
        timeout = httpx.Timeout(self.request_timeout)
        semaphore = await self._get_semaphore()

        async with semaphore:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(self.api_url, json=data, headers=headers)

        if response.status_code == 200:
            if output_file:
                with open(output_file, "wb") as audio_file:
                    audio_file.write(response.content)
                return None
            return response.content

        raise Exception(f"OpenAI TTS请求失败: {response.status_code} - {response.text}")
