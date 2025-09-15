#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CLI helper: ensure external runtime dependencies are present.
- Downloads silero_vad.onnx to external/silero_vad if missing
- Ensures ffmpeg (via PATH or external/ffmpeg; optional FFMPEG_ZIP_URL for Windows)
"""
from src.utils.external import ensure_external


def main() -> None:
    ensure_external()


if __name__ == "__main__":
    main()

