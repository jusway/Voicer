#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilities to ensure external runtime dependencies are present.
- silero_vad.onnx will be downloaded to external/silero_vad/
- ffmpeg: prefer system PATH; if missing and env FFMPEG_ZIP_URL is provided,
  download and extract ffmpeg.exe/ffprobe.exe into external/ffmpeg/

Environment variables:
- SILERO_VAD_URL: Optional override for silero VAD model download URL
- FFMPEG_ZIP_URL: Optional URL to a .zip that contains ffmpeg.exe and ffprobe.exe

This module only uses stdlib (urllib, zipfile) to avoid extra deps.
"""
from __future__ import annotations

import os
import sys
import shutil
import zipfile
import tempfile
from pathlib import Path
from urllib.request import urlopen

DEFAULT_SILERO_URL = (
    "https://www.modelscope.cn/models/manyeyes/silero-vad-onnx/file/view/master/"
    "silero_vad.onnx?status=2"
)

ROOT = Path(__file__).resolve().parents[2]
EXTERNAL_DIR = ROOT / "external"
FFMPEG_DIR = EXTERNAL_DIR / "ffmpeg"
SILERO_DIR = EXTERNAL_DIR / "silero_vad"


def _download(url: str, dest: Path, chunk_size: int = 1024 * 1024) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    print(f"Downloading: {url}\n  -> {dest}")
    with urlopen(url) as resp, open(dest, "wb") as f:
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            f.write(chunk)
    print(f"Downloaded: {dest} ({dest.stat().st_size} bytes)")


def _extract_ffmpeg_zip(zip_path: Path, target_dir: Path) -> bool:
    """
    Extract ffmpeg.exe and ffprobe.exe from a zip into target_dir.
    Returns True if both executables extracted, False otherwise.
    """
    ok = False
    target_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as zf:
        names = zf.namelist()
        cand_ffmpeg = [n for n in names if n.lower().endswith("/ffmpeg.exe")]
        cand_ffprobe = [n for n in names if n.lower().endswith("/ffprobe.exe")]
        if not cand_ffmpeg or not cand_ffprobe:
            print("Could not find ffmpeg.exe/ffprobe.exe in the provided ZIP.")
            return False
        zf.extract(cand_ffmpeg[0], target_dir)
        zf.extract(cand_ffprobe[0], target_dir)
        # Move from nested dirs to target_dir root if needed
        for src_name in (cand_ffmpeg[0], cand_ffprobe[0]):
            src = target_dir / src_name
            dst = target_dir / Path(src_name).name
            if src != dst:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), str(dst))
        ok = (target_dir / "ffmpeg.exe").exists() and (target_dir / "ffprobe.exe").exists()
    return ok


def ensure_silero() -> Path:
    SILERO_DIR.mkdir(parents=True, exist_ok=True)
    model_path = SILERO_DIR / "silero_vad.onnx"
    if model_path.exists():
        return model_path
    url = os.environ.get("SILERO_VAD_URL", DEFAULT_SILERO_URL)
    _download(url, model_path)
    return model_path


def ensure_ffmpeg() -> Path | None:
    """Ensure ffmpeg is available. Prefer PATH; else try external/ffmpeg/; else optional ZIP download.
    Returns path to ffmpeg executable if available, else None.
    """
    # 1) PATH
    which = shutil.which("ffmpeg")
    if which:
        return Path(which)

    # 2) external folder
    exe = FFMPEG_DIR / "ffmpeg.exe"
    probe = FFMPEG_DIR / "ffprobe.exe"
    if exe.exists() and probe.exists():
        return exe

    # 3) Try optional ZIP download on Windows if provided
    url = os.environ.get("FFMPEG_ZIP_URL")
    if url and sys.platform.startswith("win"):
        with tempfile.TemporaryDirectory() as td:
            zip_path = Path(td) / "ffmpeg.zip"
            _download(url, zip_path)
            ok = _extract_ffmpeg_zip(zip_path, FFMPEG_DIR)
            if ok:
                return FFMPEG_DIR / "ffmpeg.exe"
            print("FFMPEG_ZIP_URL did not contain expected executables.")

    # 4) Guidance
    msg = (
        "ffmpeg not found. Please either:\n"
        "  - Install ffmpeg and ensure it is in PATH, or\n"
        "  - On Windows, set environment variable FFMPEG_ZIP_URL to a ZIP containing ffmpeg.exe and ffprobe.exe,\n"
        "    then re-run. Files will be extracted into external/ffmpeg/.\n"
        "  - Or manually place ffmpeg.exe and ffprobe.exe into external/ffmpeg/.\n"
    )
    print(msg)
    return None


def ensure_external() -> None:
    EXTERNAL_DIR.mkdir(parents=True, exist_ok=True)
    # Ensure Silero VAD model
    try:
        ensure_silero()
    except Exception as e:
        print(f"Warning: failed to ensure silero_vad model: {e}")
    # Ensure FFMPEG
    try:
        ensure_ffmpeg()
    except Exception as e:
        print(f"Warning: failed to ensure ffmpeg: {e}")


if __name__ == "__main__":
    ensure_external()


def prepare_onnxruntime_dll_search_path() -> None:
    """Best-effort: make onnxruntime's native DLLs discoverable on Windows.

    In embedded Python deployments, the loader may not find DLLs under
    onnxruntime/capi. We add that directory to the DLL search path.

    This is a no-op on non-Windows platforms.
    """
    if os.name != "nt":
        return

    candidates: list[Path] = []

    # 1) Typical embedded layout under ROOT/Lib/site-packages/onnxruntime/capi
    candidates.append(ROOT / "Lib" / "site-packages" / "onnxruntime" / "capi")

    # 2) Virtualenv or normal installs
    try:
        import site  # type: ignore

        for base in site.getsitepackages():
            candidates.append(Path(base) / "onnxruntime" / "capi")
    except Exception:
        pass

    # 3) User override via env
    for env_key in ("ONNXRUNTIME_CAPI_DIR", "ONNXRUNTIME_DIR"):
        env_val = os.environ.get(env_key)
        if env_val:
            candidates.append(Path(env_val))

    # 4) Dedup and add the first existing path
    seen = set()
    for p in candidates:
        p = p.resolve()
        if str(p) in seen:
            continue
        seen.add(str(p))
        if p.exists():
            try:
                # Python 3.8+: preferred
                os.add_dll_directory(str(p))  # type: ignore[attr-defined]
            except Exception:
                # Fallback: prepend PATH
                os.environ["PATH"] = str(p) + os.pathsep + os.environ.get("PATH", "")
            break
