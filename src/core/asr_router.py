from __future__ import annotations

from typing import Optional

from .asr_backends.siliconflow import SiliconFlowBackend
from .asr_backends.dashscope import DashScopeBackend


class AsrRouter:
    """Facade/router to pick the proper ASR backend by provider name."""

    def __init__(self,
                 provider: str,
                 model: str,
                 api_key: str,
                 base_url: Optional[str] = None):
        provider = (provider or "").lower()
        self.provider = provider
        if provider == "siliconflow":
            self.backend = SiliconFlowBackend(api_key=api_key, model=model, base_url=base_url or "https://api.siliconflow.cn")
        elif provider == "dashscope":
            # Use DashScope backend implementation via SDK
            self.backend = DashScopeBackend(api_key=api_key, model=model, base_url=base_url)
        else:
            raise ValueError(f"未知ASR提供商: {provider}")

    def recognize(self, audio_path: str, context_prompt: str | None = None, language: str = "zh"):
        return self.backend.recognize(audio_path, context_prompt, language)

