#!/usr/bin/env python3
"""
Thin launcher for the wx GUI.
Usage:
    uv run python run_gui.py

On first run, this script ensures external dependencies exist:
- external/silero_vad/silero_vad.onnx (auto-download)
- ffmpeg (from PATH, or set FFMPEG_ZIP_URL to enable auto download on Windows)
"""
from src.gui_wx.app import main
from src.utils.external import ensure_external


if __name__ == "__main__":
    from multiprocessing import freeze_support
    freeze_support()  # Critical for PyInstaller + Windows multiprocessing
    ensure_external()
    main()
