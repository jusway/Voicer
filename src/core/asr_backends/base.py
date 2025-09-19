from __future__ import annotations

from typing import Optional, Dict, Any


class IAsrBackend:
    """ASR backend interface. Implementors should provide a recognize() method.

    The recognize() method returns a dict with at least:
      - success: bool
      - text: str (may be empty on failure)
      - raw_response: Any (optional)
    """

    def recognize(self,
                  audio_path: str,
                  context_prompt: Optional[str] = None,
                  language: str = "zh") -> Dict[str, Any]:
        raise NotImplementedError

