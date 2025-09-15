#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""wx GUI app entrypoint

Run with:
    uv run python -m src.gui_wx.app
"""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import sys

# Ensure project root on sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Default runtime paths (FFmpeg preferred; VAD model moved under src)
os.environ.setdefault("FFMPEG_PATH", str(PROJECT_ROOT / "external" / "ffmpeg"))
os.environ.setdefault("VAD_MODEL_PATH", str(PROJECT_ROOT / "external" / "silero_vad" / "silero_vad.onnx"))

# Centralize GUI config under project_root/config
CONFIG_DIR = PROJECT_ROOT / "config"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# --- Begin migrated implementation from WX_GUI.py ---
import wx
import wx.adv
import wx.lib.scrolledpanel as scrolled
import threading
import queue
import json
from pathlib import Path as _Path

# Try import core modules
try:
    from src.core.pipeline import Pipeline, PipelineError
    from src.config.settings import settings
    HAS_CORE_MODULES = True
except Exception as e:  # ImportError or others
    print(f"核心模块导入失败: {e}")
    HAS_CORE_MODULES = False


class ProgressDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="处理进度", style=wx.DEFAULT_DIALOG_STYLE)
        self.SetSize((400, 150))

        panel = wx.Panel(self)
        sizer = wx.BoxSizer(wx.VERTICAL)

        self.status_text = wx.StaticText(panel, label="准备开始处理...")
        sizer.Add(self.status_text, 0, wx.ALL | wx.EXPAND, 10)

        self.progress_bar = wx.Gauge(panel, range=100)
        sizer.Add(self.progress_bar, 0, wx.ALL | wx.EXPAND, 10)

        self.stop_btn = wx.Button(panel, label="停止处理")
        self.stop_btn.Bind(wx.EVT_BUTTON, self.on_stop)
        sizer.Add(self.stop_btn, 0, wx.ALL | wx.CENTER, 10)

        panel.SetSizer(sizer)
        self.Center()

        self.stop_event = None

    def set_stop_event(self, stop_event):
        self.stop_event = stop_event

    def on_stop(self, event):
        if self.stop_event:
            self.stop_event.set()
        self.EndModal(wx.ID_CANCEL)

    def update_progress(self, status, percentage):
        wx.CallAfter(self._update_progress_ui, status, percentage)

    def _update_progress_ui(self, status, percentage):
        self.status_text.SetLabel(status)
        self.progress_bar.SetValue(int(percentage))



class ManageAPIKeysDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="管理 API Keys", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetSize((420, 360))
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.items = self._load_items()
        self.list_box = wx.ListBox(panel, choices=[item.get('name', '') for item in self.items])
        vbox.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="添加")
        del_btn = wx.Button(panel, label="删除")
        ok_btn = wx.Button(panel, id=wx.ID_OK, label="使用所选")
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="取消")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add)
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete)
        btn_sizer.Add(add_btn, 0, wx.ALL, 5)
        btn_sizer.Add(del_btn, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(ok_btn, 0, wx.ALL, 5)
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)

        vbox.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(vbox)
        self.CenterOnParent()

    def _load_items(self):
        path = CONFIG_DIR / "wx_gui_api_keys.json"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"加载API Key列表失败: {e}")
        return []

    def _save_items(self):
        try:
            with open(CONFIG_DIR / "wx_gui_api_keys.json", 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存API Key列表失败: {e}")

    def on_add(self, event):
        name_dlg = wx.TextEntryDialog(self, "为此API Key起一个名字/标签：", "添加 API Key")
        if name_dlg.ShowModal() == wx.ID_OK:
            name = name_dlg.GetValue().strip()
            if not name:
                wx.MessageBox("名称不能为空", "提示", wx.OK | wx.ICON_WARNING)
                name_dlg.Destroy()
                return
            key_dlg = wx.TextEntryDialog(self, "请输入API Key：", "添加 API Key")
            if key_dlg.ShowModal() == wx.ID_OK:
                key = key_dlg.GetValue().strip()
                if key:
                    self.items.append({'name': name, 'key': key})
                    self._save_items()
                    self.list_box.Append(name)
            key_dlg.Destroy()
        name_dlg.Destroy()

    def on_delete(self, event):
        idx = self.list_box.GetSelection()
        if idx != wx.NOT_FOUND:
            del self.items[idx]
            self.list_box.Delete(idx)
            self._save_items()

    def get_selected(self):
        idx = self.list_box.GetSelection()
        if idx != wx.NOT_FOUND and 0 <= idx < len(self.items):
            return self.items[idx]
        return None


class PromptTextDialog(wx.Dialog):
    def __init__(self, parent, title="输入提示词内容", initial_text: str = ""):
        super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        # 设置更大的默认尺寸，支持用户拖拽调整
        self.SetSize((640, 480))

        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        label = wx.StaticText(panel, label="提示词内容：")
        self.text_ctrl = wx.TextCtrl(panel, value=initial_text, style=wx.TE_MULTILINE)

        vbox.Add(label, 0, wx.ALL, 8)
        vbox.Add(self.text_ctrl, 1, wx.ALL | wx.EXPAND, 8)

        btn_sizer = wx.StdDialogButtonSizer()
        ok_btn = wx.Button(panel, id=wx.ID_OK, label="确定")
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="取消")
        ok_btn.SetDefault()
        btn_sizer.AddButton(ok_btn)
        btn_sizer.AddButton(cancel_btn)
        btn_sizer.Realize()
        vbox.Add(btn_sizer, 0, wx.ALL | wx.ALIGN_RIGHT, 8)

        panel.SetSizer(vbox)
        self.CenterOnParent()

    def GetValue(self) -> str:
        return self.text_ctrl.GetValue()


class ManagePromptsDialog(wx.Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="管理提示词", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetSize((520, 420))
        panel = wx.Panel(self)
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.items = self._load_items()
        self.list_box = wx.ListBox(panel, choices=[item.get('name', '') for item in self.items])
        vbox.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        add_btn = wx.Button(panel, label="添加")
        del_btn = wx.Button(panel, label="删除")
        ok_btn = wx.Button(panel, id=wx.ID_OK, label="使用所选")
        cancel_btn = wx.Button(panel, id=wx.ID_CANCEL, label="取消")
        add_btn.Bind(wx.EVT_BUTTON, self.on_add)
        del_btn.Bind(wx.EVT_BUTTON, self.on_delete)
        btn_sizer.Add(add_btn, 0, wx.ALL, 5)
        btn_sizer.Add(del_btn, 0, wx.ALL, 5)
        btn_sizer.AddStretchSpacer()
        btn_sizer.Add(ok_btn, 0, wx.ALL, 5)
        btn_sizer.Add(cancel_btn, 0, wx.ALL, 5)

        vbox.Add(btn_sizer, 0, wx.EXPAND | wx.ALL, 5)
        panel.SetSizer(vbox)
        self.CenterOnParent()

    def _load_items(self):
        path = CONFIG_DIR / "wx_gui_prompts.json"
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
            except Exception as e:
                print(f"加载提示词列表失败: {e}")
        return []

    def _save_items(self):
        try:
            with open(CONFIG_DIR / "wx_gui_prompts.json", 'w', encoding='utf-8') as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存提示词列表失败: {e}")

    def on_add(self, event):
        name_dlg = wx.TextEntryDialog(self, "为此提示词起一个名字/标签：", "添加 提示词")
        if name_dlg.ShowModal() == wx.ID_OK:
            name = name_dlg.GetValue().strip()
            if not name:
                wx.MessageBox("名称不能为空", "提示", wx.OK | wx.ICON_WARNING)
                name_dlg.Destroy()
                return
            # 使用自定义对话框，提供更大的多行文本框
            text_dlg = PromptTextDialog(self, title="添加 提示词", initial_text="")
            if text_dlg.ShowModal() == wx.ID_OK:
                text = text_dlg.GetValue().strip()
                if text:
                    self.items.append({'name': name, 'text': text})
                    self._save_items()
                    self.list_box.Append(name)
            text_dlg.Destroy()
        name_dlg.Destroy()

    def on_delete(self, event):
        idx = self.list_box.GetSelection()
        if idx != wx.NOT_FOUND:
            del self.items[idx]
            self.list_box.Delete(idx)
            self._save_items()

    def get_selected(self):
        idx = self.list_box.GetSelection()
        if idx != wx.NOT_FOUND and 0 <= idx < len(self.items):
            return self.items[idx]
        return None

class MainFrame(wx.Frame):
    def __init__(self):
        super().__init__(None, title="🎙️ Qwen3 ASR API - 智能语音识别", size=(800, 700))

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
        main_panel = scrolled.ScrolledPanel(self)
        main_panel.SetupScrolling()

        main_sizer = wx.BoxSizer(wx.VERTICAL)

        title = wx.StaticText(main_panel, label="🎙️ Qwen3 ASR API - 智能语音识别")
        title_font = title.GetFont()
        title_font.PointSize += 6
        title_font = title_font.Bold()
        title.SetFont(title_font)
        main_sizer.Add(title, 0, wx.ALL | wx.CENTER, 15)

        api_box = wx.StaticBox(main_panel, label="⚙️ API 配置")
        api_sizer = wx.StaticBoxSizer(api_box, wx.VERTICAL)
        api_label = wx.StaticText(main_panel, label="DashScope API Key:")
        api_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.api_key_ctrl = wx.TextCtrl(main_panel, style=wx.TE_PASSWORD)
        self.api_key_ctrl.SetToolTip("请输入阿里云DashScope API密钥")
        self.api_key_ctrl.Bind(wx.EVT_TEXT, self.on_api_key_change)
        self.manage_api_btn = wx.Button(main_panel, label="管理API Key")
        self.manage_api_btn.Bind(wx.EVT_BUTTON, self.on_manage_api_keys)
        self.api_status = wx.StaticText(main_panel, label="⚠️ 请设置API Key")
        api_sizer.Add(api_label, 0, wx.ALL, 5)
        api_input_sizer.Add(self.api_key_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        api_input_sizer.Add(self.manage_api_btn, 0, wx.ALL, 5)
        api_sizer.Add(api_input_sizer, 0, wx.EXPAND)
        api_sizer.Add(self.api_status, 0, wx.ALL, 5)
        main_sizer.Add(api_sizer, 0, wx.ALL | wx.EXPAND, 10)

        file_box = wx.StaticBox(main_panel, label="📁 选择音频文件")
        file_sizer = wx.StaticBoxSizer(file_box, wx.VERTICAL)
        file_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.file_btn = wx.Button(main_panel, label="选择文件")
        self.file_btn.Bind(wx.EVT_BUTTON, self.on_select_file)
        self.file_label = wx.StaticText(main_panel, label="未选择文件")
        file_btn_sizer.Add(self.file_btn, 0, wx.ALL, 5)
        file_btn_sizer.Add(self.file_label, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        file_sizer.Add(file_btn_sizer, 0, wx.EXPAND)
        main_sizer.Add(file_sizer, 0, wx.ALL | wx.EXPAND, 10)

        output_box = wx.StaticBox(main_panel, label="📂 输出目录（可选）")
        output_sizer = wx.StaticBoxSizer(output_box, wx.VERTICAL)
        output_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.output_dir_ctrl = wx.TextCtrl(main_panel, value="")
        self.output_dir_ctrl.SetToolTip("可选：将结果保存到该目录；留空则默认保存到音频文件所在目录")
        self.output_dir_ctrl.Bind(wx.EVT_TEXT, self.on_output_dir_text)
        self.output_dir_btn = wx.Button(main_panel, label="浏览")
        self.output_dir_btn.Bind(wx.EVT_BUTTON, self.on_select_output_dir)
        output_btn_sizer.Add(self.output_dir_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        output_btn_sizer.Add(self.output_dir_btn, 0, wx.ALL, 5)
        output_sizer.Add(output_btn_sizer, 0, wx.EXPAND)
        main_sizer.Add(output_sizer, 0, wx.ALL | wx.EXPAND, 10)

        settings_box = wx.StaticBox(main_panel, label="⚙️ 识别设置")
        settings_sizer = wx.StaticBoxSizer(settings_box, wx.VERTICAL)

        lang_sizer = wx.BoxSizer(wx.HORIZONTAL)
        lang_label = wx.StaticText(main_panel, label="识别语言:")
        self.lang_choice = wx.Choice(main_panel, choices=["🇨🇳 中文", "🇺🇸 英文", "🇯🇵 日文", "🇰🇷 韩文"])
        self.lang_choice.SetSelection(0)
        self.lang_choice.SetToolTip("选择音频的主要语言")
        self.lang_choice.Bind(wx.EVT_CHOICE, self.on_language_change)
        lang_sizer.Add(lang_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        lang_sizer.Add(self.lang_choice, 1, wx.ALL, 5)

        vad_sizer = wx.BoxSizer(wx.HORIZONTAL)
        vad_label = wx.StaticText(main_panel, label="VAD阈值:")
        self.vad_slider = wx.Slider(main_panel, value=50, minValue=10, maxValue=90)
        self.vad_slider.SetToolTip("语音活动检测阈值，越高越严格")
        self.vad_value_label = wx.StaticText(main_panel, label="0.5")
        self.vad_slider.Bind(wx.EVT_SLIDER, self.on_vad_change)
        vad_sizer.Add(vad_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        vad_sizer.Add(self.vad_slider, 1, wx.ALL, 5)
        vad_sizer.Add(self.vad_value_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        context_label = wx.StaticText(main_panel, label="上下文提示（可选）:")
        context_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.context_ctrl = wx.TextCtrl(main_panel, style=wx.TE_MULTILINE, size=(-1, 80))
        self.context_ctrl.SetToolTip("描述音频内容的场景信息，如：会议录音、电话客服等")
        self.manage_prompts_btn = wx.Button(main_panel, label="管理提示词")
        self.manage_prompts_btn.Bind(wx.EVT_BUTTON, self.on_manage_prompts)

        settings_sizer.Add(lang_sizer, 0, wx.EXPAND)
        settings_sizer.Add(vad_sizer, 0, wx.EXPAND)
        settings_sizer.Add(context_label, 0, wx.ALL, 5)
        context_input_sizer.Add(self.context_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        context_input_sizer.Add(self.manage_prompts_btn, 0, wx.ALL, 5)
        settings_sizer.Add(context_input_sizer, 0, wx.EXPAND)

        main_sizer.Add(settings_sizer, 0, wx.ALL | wx.EXPAND, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(main_panel, label="🚀 开始语音识别")
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start_processing)
        self.test_btn = wx.Button(main_panel, label="🧪 测试API")
        self.test_btn.Bind(wx.EVT_BUTTON, self.on_test_api)
        self.open_output_btn = wx.Button(main_panel, label="📂 打开输出目录")
        self.open_output_btn.Bind(wx.EVT_BUTTON, self.on_open_output_dir)
        self.open_output_btn.Enable(False)
        btn_sizer.Add(self.start_btn, 1, wx.ALL, 5)
        btn_sizer.Add(self.test_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.open_output_btn, 0, wx.ALL, 5)
        main_sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        self.status_text = wx.StaticText(main_panel, label="就绪")
        main_sizer.Add(self.status_text, 0, wx.ALL, 10)

        main_panel.SetSizer(main_sizer)
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

    def on_api_key_change(self, event):
        self.api_key = self.api_key_ctrl.GetValue()
        if self.api_key:
            self.api_status.SetLabel("✅ API Key已设置")
            self.api_status.SetForegroundColour(wx.Colour(0, 128, 0))
        else:
            self.api_status.SetLabel("⚠️ 请设置API Key")
            self.api_status.SetForegroundColour(wx.Colour(255, 140, 0))

    def on_select_file(self, event):
        wildcard = "音频文件 (*.wav;*.mp3;*.flac;*.m4a;*.aac;*.ogg)|*.wav;*.mp3;*.flac;*.m4a;*.aac;*.ogg"
        dlg = wx.FileDialog(self, "选择音频文件", wildcard=wildcard, style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.uploaded_file_path = dlg.GetPath()
            filename = _Path(self.uploaded_file_path).name
            size_mb = _Path(self.uploaded_file_path).stat().st_size / 1024 / 1024
            self.file_label.SetLabel(f"✅ {filename} ({size_mb:.1f} MB)")
        dlg.Destroy()

    def on_select_output_dir(self, event):
        dlg = wx.DirDialog(self, "选择输出目录")
        if dlg.ShowModal() == wx.ID_OK:
            self.output_dir_override = dlg.GetPath()
            self.output_dir_ctrl.SetValue(self.output_dir_override)
        dlg.Destroy()

    def on_output_dir_text(self, event):
        self.output_dir_override = self.output_dir_ctrl.GetValue().strip()

    def on_language_change(self, event):
        lang_map = {0: 'zh', 1: 'en', 2: 'ja', 3: 'ko'}
        self.settings['language'] = lang_map[self.lang_choice.GetSelection()]

    def on_vad_change(self, event):
        value = self.vad_slider.GetValue() / 100.0
        self.settings['vad_threshold'] = value
        self.vad_value_label.SetLabel(f"{value:.1f}")
    def on_test_api(self, event):
        if not self.api_key:
            wx.MessageBox("请先设置API Key", "错误", wx.OK | wx.ICON_ERROR)
            return
        wx.MessageBox("✅ 连接正常", "测试结果", wx.OK | wx.ICON_INFORMATION)

    def on_manage_api_keys(self, event):
        dlg = ManageAPIKeysDialog(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            sel = dlg.get_selected()
            if sel and sel.get('key'):
                self.api_key = sel['key']
                self.api_key_ctrl.SetValue(self.api_key)
                self.api_status.SetLabel("✅ API Key已设置")
                self.api_status.SetForegroundColour(wx.Colour(0, 128, 0))
        dlg.Destroy()

    def on_manage_prompts(self, event):
        dlg = ManagePromptsDialog(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            sel = dlg.get_selected()
            if sel and sel.get('text'):
                self.context_ctrl.SetValue(sel['text'])
                self.settings['context'] = sel['text']
        dlg.Destroy()


    def on_start_processing(self, event):
        if not self.api_key:
            wx.MessageBox("请先设置API Key", "错误", wx.OK | wx.ICON_ERROR)
            return
        if not self.uploaded_file_path or not _Path(self.uploaded_file_path).exists():
            wx.MessageBox("请先选择有效的音频文件", "错误", wx.OK | wx.ICON_ERROR)
            return
        if not HAS_CORE_MODULES:
            wx.MessageBox("核心模块未加载，无法进行处理", "错误", wx.OK | wx.ICON_ERROR)
            return

        # 更新设置
        self.settings['context'] = self.context_ctrl.GetValue()

        # 禁用开始按钮
        self.start_btn.Enable(False)
        self.status_text.SetLabel("正在处理...")

        # 同步使用文本框中的输出目录（如有输入）
        text_path = self.output_dir_ctrl.GetValue().strip()
        if text_path:
            p = _Path(text_path)
            if p.exists() and p.is_dir():
                self.output_dir_override = str(p)
            else:
                wx.MessageBox("输出目录不存在或不可用，将使用默认目录（音频所在目录）", "提示", wx.OK | wx.ICON_WARNING)
                self.output_dir_override = ""

        progress_dlg = ProgressDialog(self)

        self.stop_event = threading.Event()
        self.progress_queue = queue.Queue()
        progress_dlg.set_stop_event(self.stop_event)

        self.processing_thread = threading.Thread(
            target=self.process_audio_background,
            args=(progress_dlg,),
            daemon=True,
        )
        self.processing_thread.start()

        result = progress_dlg.ShowModal()
        progress_dlg.Destroy()

        self.start_btn.Enable(True)

        if result == wx.ID_OK:
            self.status_text.SetLabel("处理完成")
            # 已在后台线程中通过 show_results 弹出详细的完成信息，这里不再重复弹窗
        elif result == wx.ID_CANCEL:
            self.status_text.SetLabel("处理已停止")
            wx.MessageBox("⏹️ 处理已停止", "提示", wx.OK | wx.ICON_WARNING)
        else:
            self.status_text.SetLabel("就绪")

    def process_audio_background(self, progress_dlg):
        try:
            # 更新全局配置
            from src.config.settings import settings as global_settings
            global_settings.DASHSCOPE_API_KEY = self.api_key
            global_settings.LANGUAGE = self.settings.get('language', 'zh')
            global_settings.VAD_THRESHOLD = self.settings.get('vad_threshold', 0.5)

            # 确定输出目录
            output_dir = self.output_dir_override if self.output_dir_override else str(_Path(self.uploaded_file_path).parent)
            pipeline = Pipeline(output_dir=output_dir, context_prompt=self.settings.get('context', ''))

            def progress_callback(step: str, current: int = 0, total: int = 100, percentage: float | None = None):
                if self.stop_event and self.stop_event.is_set():
                    return
                if percentage is None:
                    percentage = (current / total * 100) if total > 0 else 0
                progress_dlg.update_progress(step, percentage)

            results = pipeline.process_audio_file(
                input_path=self.uploaded_file_path,
                progress_callback=progress_callback,
                stop_event=self.stop_event,
            )

            if self.stop_event and self.stop_event.is_set():
                wx.CallAfter(progress_dlg.EndModal, wx.ID_CANCEL)
                return

            if results and 'output_files' in results:
                result_msg = "✅ 处理完成！\n\n输出文件：\n"
                for file_type, file_path in results['output_files'].items():
                    if _Path(file_path).exists():
                        result_msg += f"- {file_type}: {file_path}\n"
                wx.CallAfter(self.show_results, result_msg)

            wx.CallAfter(progress_dlg.EndModal, wx.ID_OK)

        except Exception as e:
            error_msg = f"处理失败: {str(e)}"
            wx.CallAfter(wx.MessageBox, error_msg, "错误", wx.OK | wx.ICON_ERROR)
            wx.CallAfter(progress_dlg.EndModal, wx.ID_CANCEL)



    def show_results(self, message):
        dlg = wx.MessageDialog(self, message, "处理完成", wx.OK | wx.ICON_INFORMATION)
        dlg.ShowModal()
        dlg.Destroy()
        self.open_output_btn.Enable(True)

    def on_open_output_dir(self, event):
        output_dir = self.output_dir_override if self.output_dir_override else str(_Path(self.uploaded_file_path).parent)
        if output_dir and _Path(output_dir).exists():
            import platform
            import subprocess
            try:
                if platform.system() == "Windows":
                    os.startfile(output_dir)
                elif platform.system() == "Darwin":
                    subprocess.run(["open", output_dir])
                else:
                    subprocess.run(["xdg-open", output_dir])
            except Exception as e:
                wx.MessageBox(f"\u65e0\u6cd5\u6253\u5f00\u76ee\u5f55: {str(e)}", "\u9519\u8bef", wx.OK | wx.ICON_ERROR)
        else:
            wx.MessageBox("\u8f93\u51fa\u76ee\u5f55\u4e0d\u5b58\u5728", "\u9519\u8bef", wx.OK | wx.ICON_ERROR)

    def on_about(self, event):
        info = wx.adv.AboutDialogInfo()
        info.SetName("Qwen3 ASR API")
        info.SetVersion("1.0")
        info.SetDescription("\u667a\u80fd\u8bed\u97f3\u8bc6\u522b\u684c\u9762\u5e94\u7528")
        info.SetCopyright("(C) 2025")
        wx.adv.AboutBox(info)

    def load_config(self):
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
            except Exception as e:
                print(f"\u52a0\u8f7d\u914d\u7f6e\u5931\u8d25: {e}")


    def save_config(self):
        config = {
            'output_dir': self.output_dir_override,
            'language': self.settings['language'],
            'vad_threshold': self.settings['vad_threshold'],
            'context': self.context_ctrl.GetValue(),
            'api_key': self.api_key,
        }

        try:
            with open(CONFIG_DIR / "wx_gui_config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"\u4fdd\u5b58\u914d\u7f6e\u5931\u8d25: {e}")

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
