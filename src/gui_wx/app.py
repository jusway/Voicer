#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wx GUI app entrypoint

Run with:
    uv run python -m src.gui_wx.app
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import json


# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Default runtime paths (FFmpeg preferred; VAD model moved under src)
os.environ.setdefault("FFMPEG_PATH", str(PROJECT_ROOT / "external" / "ffmpeg"))
from src.gui_wx.paths import CONFIG_DIR

os.environ.setdefault("VAD_MODEL_PATH", str(PROJECT_ROOT / "external" / "silero_vad" / "silero_vad.onnx"))



# --- Begin migrated implementation from WX_GUI.py ---
import wx
import wx.adv

from src.gui_wx.panels.text_polish_panel import TextPolishPanel
from src.gui_wx.panels.asr_panel import ASRPanel


class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="🎙️ 声稿师 Voicer", size=(800, 1000))

        self.api_key = ""
        self.uploaded_file_path = ""
        self.output_dir_override = ""
        self.settings = {
            'language': 'zh',
            'context': '',
            'vad_threshold': 0.5,
        }
        self.processing = False
        self.progress_queue = None
        self.stop_event = None
        self.processing_thread = None

        self.init_ui()
        self.load_config()
        self.Center()
        self.Bind(wx.EVT_CLOSE, self.on_close)

    def init_ui(self):
        # Notebook with two tabs: ASR (existing) and TextPolish (new)
        notebook = wx.Notebook(self)

        # --- ASR Tab ---
        asr_panel = ASRPanel(notebook)
        self.asr_panel = asr_panel

        # --- TextPolish Tab ---
        self.polish_panel = TextPolishPanel(notebook)

        # Add pages
        notebook.AddPage(asr_panel, "语音识别")
        notebook.AddPage(self.polish_panel, "文本规范/文本润色")

        # Set frame sizer
        root_sizer = wx.BoxSizer(wx.VERTICAL)
        root_sizer.Add(notebook, 1, wx.EXPAND)
        self.SetSizer(root_sizer)

        self.create_menu()

    def create_menu(self):
        menubar = wx.MenuBar()
        file_menu = wx.Menu()
        exit_item = file_menu.Append(wx.ID_EXIT, "退出\tCtrl+Q")
        self.Bind(wx.EVT_MENU, self.on_exit, exit_item)
        help_menu = wx.Menu()
        about_item = help_menu.Append(wx.ID_ABOUT, "关于")
        self.Bind(wx.EVT_MENU, self.on_about, about_item)
        menubar.Append(file_menu, "文件")
        menubar.Append(help_menu, "帮助")
        self.SetMenuBar(menubar)








    def on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("Qwen3 ASR API")
        info.SetVersion("1.0")
        info.SetDescription("\u667a\u80fd\u8bed\u97f3\u8bc6\u522b\u684c\u9762\u5e94\u7528")
        info.SetCopyright("(C) 2025")
        wx.adv.AboutBox(info)

    def load_config_legacy(self):
        config_file = CONFIG_DIR / "wx_gui_config.json"
        if config_file.exists():
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                if 'api_key' in config:
                    self.api_key = config['api_key'] or ""
                    self.api_key_ctrl.SetValue(self.api_key)
                    if self.api_key:
                        self.api_status.SetLabel("✅ API Key已设置")
                        self.api_status.SetForegroundColour(wx.Colour(0, 128, 0))

                if 'output_dir' in config:
                    self.output_dir_override = config['output_dir']
                    self.output_dir_ctrl.SetValue(self.output_dir_override)
                if 'language' in config:
                    lang_map = {'zh': 0, 'en': 1, 'ja': 2, 'ko': 3}
                    if config['language'] in lang_map:
                        self.lang_choice.SetSelection(lang_map[config['language']])
                        self.settings['language'] = config['language']
                if 'vad_threshold' in config:
                    value = int(config['vad_threshold'] * 100)
                    self.vad_slider.SetValue(value)
                    self.settings['vad_threshold'] = config['vad_threshold']
                    self.vad_value_label.SetLabel(f"{config['vad_threshold']:.1f}")
                if 'context' in config:
                    self.context_ctrl.SetValue(config['context'])
                    self.settings['context'] = config['context']
                if 'asr_provider' in config:
                    self.provider_choice.SetSelection(1 if config['asr_provider'] == 'siliconflow' else 0)
                    self.on_provider_change(None)
                if 'asr_model' in config:
                    try:
                        self.model_choice.SetStringSelection(config['asr_model'])
                    except Exception:
                        pass
                if 'asr_base_url' in config:
                    self.asr_base_url_ctrl.SetValue(config.get('asr_base_url') or "")

            except Exception as e:
                print(f"\u52a0\u8f7d\u914d\u7f6e\u5931\u8d25: {e}")


    def load_config(self):
        try:
            if hasattr(self, "asr_panel") and hasattr(self.asr_panel, "load_config"):
                self.asr_panel.load_config()
            if hasattr(self, "polish_panel") and hasattr(self.polish_panel, "load_config"):
                self.polish_panel.load_config()
        except Exception as e:
            print(f"加载配置失败: {e}")


    def save_config_legacy(self):
        config = {
            'output_dir': self.output_dir_override,
            'language': self.settings['language'],
            'vad_threshold': self.settings['vad_threshold'],
            'context': self.context_ctrl.GetValue(),
            'api_key': self.api_key,
            'asr_provider': 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope',
            'asr_model': self.model_choice.GetStringSelection(),
            'asr_base_url': (self.asr_base_url_ctrl.GetValue().strip() if hasattr(self, 'asr_base_url_ctrl') else ''),
        }

        try:
            with open(CONFIG_DIR / "wx_gui_config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"\u4fdd\u5b58\u914d\u7f6e\u5931\u8d25: {e}")

    def save_config(self):
        try:
            if hasattr(self, "asr_panel") and hasattr(self.asr_panel, "save_config"):
                self.asr_panel.save_config()
            if hasattr(self, "polish_panel") and hasattr(self.polish_panel, "save_config"):
                self.polish_panel.save_config()
        except Exception as e:
            print(f"保存配置失败: {e}")


    def on_close(self, event):
        self.save_config()
        self.Destroy()

    def on_exit(self, event):
        self.Close()


class ASRApp(wx.App):
    def OnInit(self):
        frame = MainFrame()
        frame.Show()
        return True




def main() -> None:
    """Start wx GUI application."""
    app = ASRApp()
    app.MainLoop()


if __name__ == "__main__":
    main()
