from __future__ import annotations

import os
import threading
import queue
import json
from pathlib import Path as _Path

import wx
import wx.lib.scrolledpanel as scrolled

from src.gui_wx.dialogs.progress_dialog import ProgressDialog
from src.gui_wx.dialogs.manage_api_keys import ManageAPIKeysDialog
from src.gui_wx.dialogs.manage_prompts import ManagePromptsDialog
from src.gui_wx.paths import CONFIG_DIR

# Core pipeline
try:
    from src.core.pipeline import Pipeline
    from src.config.settings import settings as global_settings
    HAS_CORE_MODULES = True
except Exception as e:
    print(f"核心模块导入失败: {e}")
    HAS_CORE_MODULES = False


class ASRPanel(scrolled.ScrolledPanel):
    def __init__(self, parent):
        super().__init__(parent)
        self.SetupScrolling()

        # State
        self.api_key: str = ""
        self.uploaded_file_path: str = ""
        self.output_dir_override: str = ""
        self.settings: dict = {
            'language': 'zh',
            'context': '',
            'vad_threshold': 0.5,
        }
        self.stop_event: threading.Event | None = None
        self.progress_queue: queue.Queue | None = None
        self.processing_thread: threading.Thread | None = None

        # Build UI
        self._build_ui()
        self.load_config()

    def _build_ui(self):
        sizer = wx.BoxSizer(wx.VERTICAL)

        api_box = wx.StaticBox(self, label="⚙️ API 配置")
        api_sizer = wx.StaticBoxSizer(api_box, wx.VERTICAL)
        self.api_label = wx.StaticText(self, label="阿里百炼 API Key:")
        api_key_row = wx.BoxSizer(wx.HORIZONTAL)
        self.api_key_ctrl = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        self.api_key_ctrl.SetToolTip("请输入阿里百炼 API Key")
        self.api_key_ctrl.Bind(wx.EVT_TEXT, self.on_api_key_change)
        self.api_status = wx.StaticText(self, label="⚠️ 请设置API Key")
        # Base URL row（置于 KEY 之前）
        base_row = wx.BoxSizer(wx.HORIZONTAL)
        self.asr_base_url_label = wx.StaticText(self, label="Base URL:")
        base_row.Add(self.asr_base_url_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.asr_base_url_ctrl = wx.TextCtrl(self, value="")
        base_row.Add(self.asr_base_url_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        api_sizer.Add(base_row, 0, wx.EXPAND)
        # API Key 行（标签紧贴输入框，状态在右侧）
        api_key_row.Add(self.api_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        api_key_row.Add(self.api_key_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        api_key_row.Add(self.api_status, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        api_sizer.Add(api_key_row, 0, wx.EXPAND)
        sizer.Add(api_sizer, 0, wx.ALL | wx.EXPAND, 10)

        file_box = wx.StaticBox(self, label="📁 选择音频文件")
        file_sizer = wx.StaticBoxSizer(file_box, wx.VERTICAL)
        file_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.file_btn = wx.Button(self, label="选择文件")
        self.file_btn.Bind(wx.EVT_BUTTON, self.on_select_file)
        self.file_label = wx.StaticText(self, label="未选择文件")
        file_btn_sizer.Add(self.file_btn, 0, wx.ALL, 5)
        file_btn_sizer.Add(self.file_label, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        file_sizer.Add(file_btn_sizer, 0, wx.EXPAND)
        sizer.Add(file_sizer, 0, wx.ALL | wx.EXPAND, 10)

        output_box = wx.StaticBox(self, label="📂 输出目录（可选）")
        output_sizer = wx.StaticBoxSizer(output_box, wx.VERTICAL)
        output_btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.output_dir_ctrl = wx.TextCtrl(self, value="")
        self.output_dir_ctrl.SetToolTip("可选：将结果保存到该目录；留空则默认保存到音频文件所在目录")
        self.output_dir_ctrl.Bind(wx.EVT_TEXT, self.on_output_dir_text)
        self.output_dir_btn = wx.Button(self, label="浏览")
        self.output_dir_btn.Bind(wx.EVT_BUTTON, self.on_select_output_dir)
        output_btn_sizer.Add(self.output_dir_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        output_btn_sizer.Add(self.output_dir_btn, 0, wx.ALL, 5)
        output_sizer.Add(output_btn_sizer, 0, wx.EXPAND)
        sizer.Add(output_sizer, 0, wx.ALL | wx.EXPAND, 10)

        settings_box = wx.StaticBox(self, label="⚙️ 识别设置")
        settings_sizer = wx.StaticBoxSizer(settings_box, wx.VERTICAL)

        provider_sizer = wx.BoxSizer(wx.HORIZONTAL)
        provider_label = wx.StaticText(self, label="提供商:")
        self.provider_choice = wx.Choice(self, choices=["阿里百炼 (DashScope)", "硅基流动 (SiliconFlow)"])
        self.provider_choice.SetSelection(0)
        self.provider_choice.Bind(wx.EVT_CHOICE, self.on_provider_change)
        provider_sizer.Add(provider_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        provider_sizer.Add(self.provider_choice, 1, wx.ALL | wx.EXPAND, 5)

        model_sizer = wx.BoxSizer(wx.HORIZONTAL)
        model_label = wx.StaticText(self, label="模型:")
        self.DS_MODELS = ["qwen3-asr-flash"]
        self.SF_MODELS = ["TeleAI/TeleSpeechASR"]
        self.model_choice = wx.Choice(self, choices=self.DS_MODELS)
        self.model_choice.SetSelection(0)
        model_sizer.Add(model_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        model_sizer.Add(self.model_choice, 1, wx.ALL | wx.EXPAND, 5)

        api_sizer.Insert(0, provider_sizer, 0, wx.EXPAND)
        api_sizer.Add(model_sizer, 0, wx.EXPAND)

        lang_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.on_provider_change(None)

        lang_label = wx.StaticText(self, label="识别语言:")
        self.lang_choice = wx.Choice(self, choices=["🇨🇳 中文", "🇺🇸 英文", "🇯🇵 日文", "🇰🇷 韩文"])
        self.lang_choice.SetSelection(0)
        self.lang_choice.SetToolTip("选择音频的主要语言")
        self.lang_choice.Bind(wx.EVT_CHOICE, self.on_language_change)
        lang_sizer.Add(lang_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        lang_sizer.Add(self.lang_choice, 1, wx.ALL, 5)

        vad_sizer = wx.BoxSizer(wx.HORIZONTAL)
        vad_label = wx.StaticText(self, label="VAD阈值:")
        self.vad_slider = wx.Slider(self, value=50, minValue=10, maxValue=90)
        self.vad_slider.SetToolTip("语音活动检测阈值，越高越严格")
        self.vad_value_label = wx.StaticText(self, label="0.5")
        self.vad_slider.Bind(wx.EVT_SLIDER, self.on_vad_change)
        vad_sizer.Add(vad_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        vad_sizer.Add(self.vad_slider, 1, wx.ALL, 5)
        vad_sizer.Add(self.vad_value_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)

        context_label = wx.StaticText(self, label="上下文提示（可选）:")
        context_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.context_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 80))
        self.context_ctrl.SetToolTip("描述音频内容的场景信息，如：会议录音、电话客服等")
        self.manage_prompts_btn = wx.Button(self, label="管理提示词")
        self.manage_prompts_btn.Bind(wx.EVT_BUTTON, self.on_manage_prompts)

        settings_sizer.Add(lang_sizer, 0, wx.EXPAND)
        settings_sizer.Add(vad_sizer, 0, wx.EXPAND)
        settings_sizer.Add(context_label, 0, wx.ALL, 5)
        context_input_sizer.Add(self.context_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        context_input_sizer.Add(self.manage_prompts_btn, 0, wx.ALL, 5)
        settings_sizer.Add(context_input_sizer, 0, wx.EXPAND)

        sizer.Add(settings_sizer, 0, wx.ALL | wx.EXPAND, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(self, label="🚀 开始语音识别")
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start_processing)
        self.test_btn = wx.Button(self, label="🧪 测试API")
        self.test_btn.Bind(wx.EVT_BUTTON, self.on_test_api)
        self.open_output_btn = wx.Button(self, label="📂 打开输出目录")
        self.open_output_btn.Bind(wx.EVT_BUTTON, self.on_open_output_dir)
        self.open_output_btn.Enable(False)
        btn_sizer.Add(self.start_btn, 1, wx.ALL, 5)
        btn_sizer.Add(self.test_btn, 0, wx.ALL, 5)
        btn_sizer.Add(self.open_output_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        self.status_text = wx.StaticText(self, label="就绪")
        sizer.Add(self.status_text, 0, wx.ALL, 10)

        self.SetSizer(sizer)

    # ===== Event handlers & logic =====
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

    def on_provider_change(self, event):
        idx = self.provider_choice.GetSelection()
        if idx == 1:  # SiliconFlow
            self.model_choice.Set(self.SF_MODELS)
            self.model_choice.SetSelection(0)
            self.api_label.SetLabel("硅基流动 API Key:")
            self.api_key_ctrl.SetToolTip("请输入硅基流动 API Key")
            if hasattr(self, "asr_base_url_label"):
                self.asr_base_url_label.Show(True)
            if hasattr(self, "asr_base_url_ctrl"):
                if not self.asr_base_url_ctrl.GetValue().strip():
                    self.asr_base_url_ctrl.SetValue("https://api.siliconflow.cn")
                self.asr_base_url_ctrl.Show(True)
            if hasattr(self, "vad_slider"):
                self.vad_slider.Enable(False)
            if hasattr(self, "vad_value_label"):
                self.vad_value_label.Enable(False)
        else:  # DashScope
            self.model_choice.Set(self.DS_MODELS)
            self.model_choice.SetSelection(0)
            self.api_label.SetLabel("阿里百炼 API Key:")
            self.api_key_ctrl.SetToolTip("请输入阿里百炼 API Key")
            if hasattr(self, "asr_base_url_label"):
                self.asr_base_url_label.Show(False)
            if hasattr(self, "asr_base_url_ctrl"):
                self.asr_base_url_ctrl.Show(False)
            if hasattr(self, "vad_slider"):
                self.vad_slider.Enable(True)
            if hasattr(self, "vad_value_label"):
                self.vad_value_label.Enable(True)
        self.Layout()

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
        prov = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
        if prov == 'siliconflow' and (not self.asr_base_url_ctrl.GetValue().strip()):
            wx.MessageBox("请设置 SiliconFlow 的 Base URL", "提示", wx.OK | wx.ICON_WARNING)
            return
        try:
            base_dir = _Path(__file__).resolve().parents[2]  # src/gui_wx/panels -> src
            test_audio = base_dir / 'test_audio' / 'test.m4a'
        except Exception:
            test_audio = None
        if not test_audio or not test_audio.exists():
            wx.MessageBox("未找到测试音频：src/test_audio/test.m4a", "错误", wx.OK | wx.ICON_ERROR)
            return
        self.uploaded_file_path = str(test_audio)
        filename = test_audio.name
        try:
            size_mb = test_audio.stat().st_size / 1024 / 1024
        except Exception:
            size_mb = 0
        self.file_label.SetLabel(f"✅ {filename} ({size_mb:.1f} MB)")
        self.on_start_processing(None)



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

        self.settings['context'] = self.context_ctrl.GetValue()
        self.start_btn.Enable(False)
        self.status_text.SetLabel("正在处理...")

        # Text field output dir
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

        self.processing_thread = threading.Thread(target=self.process_audio_background, args=(progress_dlg,), daemon=True)
        self.processing_thread.start()

        result = progress_dlg.ShowModal()
        progress_dlg.Destroy()

        self.start_btn.Enable(True)

        if result == wx.ID_OK:
            self.status_text.SetLabel("处理完成")
        elif result == wx.ID_CANCEL:
            self.status_text.SetLabel("处理已停止")
            wx.MessageBox("⏹️ 处理已停止", "提示", wx.OK | wx.ICON_WARNING)
        else:
            self.status_text.SetLabel("就绪")

    def process_audio_background(self, progress_dlg: ProgressDialog):
        try:
            # 更新全局配置
            provider = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
            global_settings.ASR_PROVIDER = provider
            global_settings.ASR_MODEL = self.model_choice.GetStringSelection()
            if provider == 'siliconflow':
                global_settings.SILICONFLOW_API_KEY = self.api_key
            else:
                global_settings.DASHSCOPE_API_KEY = self.api_key
            if provider == 'siliconflow':
                try:
                    bu = (self.asr_base_url_ctrl.GetValue().strip() or "")
                    if bu:
                        bu = bu.rstrip('/')
                        if bu.endswith('/v1'):
                            bu = bu[:-3]
                        global_settings.SILICONFLOW_BASE_URL = bu
                except Exception:
                    pass

            global_settings.LANGUAGE = self.settings.get('language', 'zh')
            global_settings.VAD_THRESHOLD = self.settings.get('vad_threshold', 0.5)

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

    def show_results(self, message: str):
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
                wx.MessageBox(f"无法打开目录: {str(e)}", "错误", wx.OK | wx.ICON_ERROR)
        else:
            wx.MessageBox("输出目录不存在", "错误", wx.OK | wx.ICON_ERROR)

    # ===== Config =====
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
                print(f"加载配置失败: {e}")

    def save_config(self):
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
            print(f"保存配置失败: {e}")

