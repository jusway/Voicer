from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ProviderKeys:
    dashscope: Optional[str] = None
    siliconflow: Optional[str] = None


@dataclass
class ProviderEndpoints:
    dashscope: Optional[str] = None
    siliconflow: Optional[str] = None


@dataclass
class PipelineConfig:
    """Configuration object injected into Pipeline to avoid global mutable state.

    - provider: 'dashscope' | 'siliconflow'
    - model: model name for the selected provider
    - language: ISO-like short code (e.g., 'zh', 'en')
    - keys: API keys per provider
    - base_urls: optional base URLs per provider (e.g., SiliconFlow API base)
    - vad_threshold: kept for future use (VADProcessor can read from here later)
    - context: optional context prompt for ASR
    """
    provider: str
    model: str
    language: str = "zh"
    keys: ProviderKeys = field(default_factory=ProviderKeys)
    base_urls: ProviderEndpoints = field(default_factory=ProviderEndpoints)
    vad_threshold: float = 0.5
    context: Optional[str] = None

