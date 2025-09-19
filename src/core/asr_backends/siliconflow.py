from __future__ import annotations

from typing import Optional, Dict, Any

try:
    import requests
except Exception as e:  # pragma: no cover - handled at runtime
    requests = None  # type: ignore

from .base import IAsrBackend


class SiliconFlowBackend(IAsrBackend):
    """SiliconFlow audio transcription backend (whole-file upload).

    API doc (2025-09): POST {base_url}/v1/audio/transcriptions
      - headers: Authorization: Bearer <API Key>
      - multipart form fields: model, file
      - response JSON: { "text": "..." }
    """

    def __init__(self,
                 api_key: str,
                 model: str = "TeleAI/TeleSpeechASR",
                 base_url: str = "https://api.siliconflow.cn",
                 timeout: int = 180,
                 max_retries: int = 2):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_retries = max_retries

    def recognize(self,
                  audio_path: str,
                  context_prompt: Optional[str] = None,
                  language: str = "zh") -> Dict[str, Any]:
        if requests is None:
            return {
                "success": False,
                "error_message": "requests 库未安装，请先安装 requests",
            }

        url = f"{self.base_url}/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}
        data = {"model": self.model}

        for attempt in range(self.max_retries + 1):
            try:
                with open(audio_path, "rb") as f:
                    files = {"file": f}
                    resp = requests.post(url, headers=headers, data=data, files=files, timeout=self.timeout)
                if resp.status_code != 200:
                    err = f"HTTP {resp.status_code}: {resp.text[:400]}"
                    if attempt < self.max_retries:
                        continue
                    return {"success": False, "error_message": err, "raw_response": resp.text}

                try:
                    j = resp.json()
                except Exception:
                    j = {"raw": resp.text}

                text = (j.get("text") or "").strip() if isinstance(j, dict) else ""
                if not text:
                    return {"success": False, "error_message": "空结果", "raw_response": j}
                return {"success": True, "text": text, "raw_response": j}

            except Exception as e:
                if attempt < self.max_retries:
                    continue
                return {"success": False, "error_message": str(e)}

        return {"success": False, "error_message": "未知错误"}

