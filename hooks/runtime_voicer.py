#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Runtime hook for PyInstaller to prepare environment before the app starts.
- Prefer bundled external tools/models if present (ffmpeg, silero_vad.onnx)
- Improve onnxruntime native DLL discovery (especially on Windows)

This file is referenced by Voicer.spec via runtime_hooks=['hooks/runtime_voicer.py']
"""
from __future__ import annotations

import contextlib
import os
import sys
from pathlib import Path

# Resolve the app root (onedir folder when frozen; project root otherwise)
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).parent
else:
    ROOT = Path(__file__).resolve().parents[1]

# 1) Prefer bundled FFmpeg if present
FF_DIR = ROOT / "external" / "ffmpeg"
if os.name == "nt":
    _ffmpeg_bin = FF_DIR / "ffmpeg.exe"
    _ffprobe_bin = FF_DIR / "ffprobe.exe"
else:
    _ffmpeg_bin = FF_DIR / "ffmpeg"
    _ffprobe_bin = FF_DIR / "ffprobe"

if _ffmpeg_bin.exists() and _ffprobe_bin.exists():
    os.environ.setdefault("FFMPEG_PATH", str(_ffmpeg_bin))
    # Prepend bundled ffmpeg folder to PATH for subprocess discovery
    os.environ["PATH"] = str(FF_DIR) + os.pathsep + os.environ.get("PATH", "")

# 2) Prefer bundled Silero VAD model if present
VAD_MODEL = ROOT / "external" / "silero_vad" / "silero_vad.onnx"
if VAD_MODEL.exists():
    # The app reads VAD_MODEL_PATH from environment (per src/gui_wx/app.py)
    os.environ.setdefault("VAD_MODEL_PATH", str(VAD_MODEL))

# 3) onnxruntime native DLL search path (best-effort)
# Try typical locations in a PyInstaller onedir bundle
CANDIDATES: list[Path] = []
CANDIDATES.append(ROOT / "onnxruntime" / "capi")
CANDIDATES.append(ROOT / "Lib" / "site-packages" / "onnxruntime" / "capi")

# Allow user override via env
for k in ("ONNXRUNTIME_CAPI_DIR", "ONNXRUNTIME_DIR"):
    v = os.environ.get(k)
    if v:
        CANDIDATES.append(Path(v))

# Dedup while keeping order
_seen: set[str] = set()
uniq_candidates = []
for p in CANDIDATES:
    rp = str(Path(p).resolve())
    if rp not in _seen:
        _seen.add(rp)
        uniq_candidates.append(Path(rp))

if os.name == "nt":
    # Prefer add_dll_directory on Windows
    for p in uniq_candidates:
        if p.exists():
            with contextlib.suppress(Exception):
                os.add_dll_directory(str(p))  # type: ignore[attr-defined]
            # Also prepend PATH as a fallback for any child processes
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
            break
else:
    # Non-Windows: prepend PATH to help native libs be found by loader
    for p in uniq_candidates:
        if p.exists():
            os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
            break

