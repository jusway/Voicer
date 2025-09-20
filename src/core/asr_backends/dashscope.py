from __future__ import annotations

from pathlib import Path
from typing import Optional, Dict, Any

import dashscope

from .base import IAsrBackend


class DashScopeBackend(IAsrBackend):
    """DashScope (阿里百炼) 音频识别后端。

    - 使用 DashScope Python SDK 的 MultiModalConversation.call 接口
    - 统一将本地文件路径规范化为 file:// URL（Windows 使用正斜杠）
    - 使用 result_format="message" 与 asr_options 提升稳健性
    """

    def __init__(
        self,
        api_key: str,
        model: str = "qwen3-asr-flash",
        base_url: Optional[str] = None,
        timeout: int = 180,
        max_retries: int = 2,
        retry_delay: float = 1.0,
    ) -> None:
        dashscope.api_key = api_key
        # 国内 Key 默认端点即可；如需国际站可传入 https://dashscope-intl.aliyuncs.com/api/v1
        if base_url:
            dashscope.base_http_api_url = base_url
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

    def recognize(
        self,
        audio_path: str,
        context_prompt: Optional[str] = None,
        language: str = "zh",
    ) -> Dict[str, Any]:
        """识别音频文件，返回统一结果字典。

        Returns dict with at least:
          - success: bool
          - text: str (on success)
          - error_message: str (on failure)
          - raw_response: Any (optional)
        """
        try:
            # 1) 构造消息（含本地 file:// URL）
            p = Path(audio_path).resolve()
            audio_url = f"file://{p.as_posix()}"
            messages: list[dict] = []
            if context_prompt:
                messages.append({
                    "role": "system",
                    "content": [{"text": context_prompt}],
                })
            messages.append({
                "role": "user",
                "content": [{"audio": audio_url}],
            })

            # 2) 调用 SDK（使用 result_format + asr_options）
            response = dashscope.MultiModalConversation.call(
                model=self.model,
                messages=messages,
                result_format="message",
                asr_options={
                    "language": language,
                    "enable_itn": True,
                    "enable_lid": False,
                },
            )

            # 3) 解析响应
            status = getattr(response, "status_code", 200)
            if status != 200:
                return {
                    "success": False,
                    "error_message": f"API返回错误状态: {status}",
                    "raw_response": response,
                }

            output = getattr(response, "output", None)
            if not isinstance(output, dict) or "choices" not in output:
                return {
                    "success": False,
                    "error_message": "响应格式错误：缺少choices字段",
                    "raw_response": response,
                }
            choices = output.get("choices") or []
            if not choices:
                return {
                    "success": False,
                    "error_message": "响应格式错误：choices为空",
                    "raw_response": response,
                }
            first = choices[0] if isinstance(choices[0], dict) else {}
            message = first.get("message", {}) if isinstance(first, dict) else {}
            content = message.get("content", []) if isinstance(message, dict) else []

            text_parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    text_parts.append(item["text"])
            text = ("".join(text_parts)).strip()
            if not text:
                return {
                    "success": False,
                    "error_message": "识别结果为空",
                    "raw_response": response,
                }

            usage = getattr(response, "usage", {}) or {}
            return {
                "success": True,
                "text": text,
                "raw_response": response,
                "usage": usage,
            }

        except Exception as e:
            # 统一错误返回格式
            return {
                "success": False,
                "error_message": f"API调用失败: {e}",
            }

