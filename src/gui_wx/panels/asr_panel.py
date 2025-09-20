from __future__ import annotations

import os
import threading
import queue
import json
from pathlib import Path as _Path

import wx
import wx.lib.scrolledpanel as scrolled

try:
    import requests  # 用于 SiliconFlow 连通性测试
except Exception:
    requests = None

from src.gui_wx.dialogs.progress_dialog import ProgressDialog
from src.gui_wx.dialogs.manage_api_keys import ManageAPIKeysDialog
from src.gui_wx.dialogs.manage_prompts import ManagePromptsDialog
from src.gui_wx.paths import CONFIG_DIR

# Core pipeline
try:
    from src.core.pipeline import Pipeline
    from src.core.pipeline_config import PipelineConfig, ProviderKeys, ProviderEndpoints
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

        # Per-provider in-memory config (for 2A UX)
        self.api_keys = {'dashscope': '', 'siliconflow': ''}
        self.base_urls = {'siliconflow': 'https://api.siliconflow.cn'}

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
        self.test_btn = wx.Button(self, label="🧪 测试API")
        self.test_btn.Bind(wx.EVT_BUTTON, self.on_test_api)
        api_key_row.Add(self.test_btn, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)


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

        self.lang_label = wx.StaticText(self, label="识别语言:")
        self.lang_choice = wx.Choice(self, choices=["🇨🇳 中文", "🇺🇸 英文", "🇯🇵 日文", "🇰🇷 韩文"])
        self.lang_choice.SetSelection(0)
        self.lang_choice.SetToolTip("选择音频的主要语言")
        self.lang_choice.Bind(wx.EVT_CHOICE, self.on_language_change)
        lang_sizer.Add(self.lang_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
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

        self.context_label = wx.StaticText(self, label="上下文提示（可选）:")
        context_input_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.context_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 80))
        self.context_ctrl.SetToolTip("描述音频内容的场景信息，如：会议录音、电话客服等")
        self.manage_prompts_btn = wx.Button(self, label="管理提示词")
        self.manage_prompts_btn.Bind(wx.EVT_BUTTON, self.on_manage_prompts)

        settings_sizer.Add(lang_sizer, 0, wx.EXPAND)
        settings_sizer.Add(vad_sizer, 0, wx.EXPAND)
        settings_sizer.Add(self.context_label, 0, wx.ALL, 5)
        context_input_sizer.Add(self.context_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        context_input_sizer.Add(self.manage_prompts_btn, 0, wx.ALL, 5)
        settings_sizer.Add(context_input_sizer, 0, wx.EXPAND)

        sizer.Add(settings_sizer, 0, wx.ALL | wx.EXPAND, 10)

        btn_sizer = wx.BoxSizer(wx.HORIZONTAL)
        self.start_btn = wx.Button(self, label="🚀 开始语音识别")
        self.start_btn.Bind(wx.EVT_BUTTON, self.on_start_processing)
        self.open_output_btn = wx.Button(self, label="📂 打开输出目录")
        self.open_output_btn.Bind(wx.EVT_BUTTON, self.on_open_output_dir)
        self.open_output_btn.Enable(False)
        btn_sizer.Add(self.start_btn, 1, wx.ALL, 5)
        btn_sizer.Add(self.open_output_btn, 0, wx.ALL, 5)
        sizer.Add(btn_sizer, 0, wx.ALL | wx.EXPAND, 10)

        self.status_text = wx.StaticText(self, label="就绪")
        sizer.Add(self.status_text, 0, wx.ALL, 10)

        self.SetSizer(sizer)

    # ===== Event handlers & logic =====
    def on_api_key_change(self, event):
        prov = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
        self.api_key = self.api_key_ctrl.GetValue()
        self.api_keys[prov] = self.api_key

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
            # Disable unsupported settings for SiliconFlow
            if hasattr(self, "lang_choice"):
                self.lang_choice.Enable(False)
            if hasattr(self, "lang_label"):
                self.lang_label.Enable(False)
            if hasattr(self, "context_ctrl"):
                self.context_ctrl.Enable(False)
            if hasattr(self, "manage_prompts_btn"):
                self.manage_prompts_btn.Enable(False)
            if hasattr(self, "context_label"):
                self.context_label.Enable(False)
            if hasattr(self, "test_btn"):
                self.test_btn.Show(True)
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
            # Re-enable settings for DashScope
            if hasattr(self, "lang_choice"):
                self.lang_choice.Enable(True)
            if hasattr(self, "lang_label"):
                self.lang_label.Enable(True)
            if hasattr(self, "context_ctrl"):
                self.context_ctrl.Enable(True)
            if hasattr(self, "manage_prompts_btn"):
                self.manage_prompts_btn.Enable(True)
            if hasattr(self, "context_label"):
                self.context_label.Enable(True)
            if hasattr(self, "test_btn"):
                self.test_btn.Show(False)
        # After switching provider, auto-fill fields from per-provider memory
        prov = 'siliconflow' if idx == 1 else 'dashscope'
        if prov == 'siliconflow' and hasattr(self, 'asr_base_url_ctrl'):
            self.asr_base_url_ctrl.SetValue(self.base_urls.get('siliconflow', '') or 'https://api.siliconflow.cn')
        self.api_key_ctrl.SetValue(self.api_keys.get(prov, '') or '')
        self.api_key = self.api_key_ctrl.GetValue()
        self.Layout()



    def on_language_change(self, event):
        lang_map = {0: 'zh', 1: 'en', 2: 'ja', 3: 'ko'}
        self.settings['language'] = lang_map[self.lang_choice.GetSelection()]

    def on_vad_change(self, event):
        value = self.vad_slider.GetValue() / 100.0
        self.settings['vad_threshold'] = value
        self.vad_value_label.SetLabel(f"{value:.1f}")

    def on_test_api(self, event):
        prov = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
        key = self.api_keys.get(prov, '') if hasattr(self, 'api_keys') else (self.api_key or '')
        if not key:
            wx.MessageBox("请先设置API Key", "错误", wx.OK | wx.ICON_ERROR)
            return
        if prov == 'siliconflow':
            # 规范化 Base URL
            if 'asr_base_url_ctrl' in self.__dict__:
                base = (self.asr_base_url_ctrl.GetValue().strip() or "https://api.siliconflow.cn").rstrip('/')
            else:
                base = "https://api.siliconflow.cn"
            if base.endswith('/v1'):
                base = base[:-3]
            url = f"{base}/v1/models"

            # 依赖 requests；缺失时给出提示
            if requests is None:
                wx.MessageBox("requests 库未安装，无法进行连通性测试", "错误", wx.OK | wx.ICON_ERROR)
                self.status_text.SetLabel("测试失败：缺少 requests")
                return

            # 更新 UI 状态并后台执行
            self.test_btn.Enable(False)
            self.test_btn.SetLabel("测试中…")
            self.status_text.SetLabel("测试中…")

            def run():
                try:
                    r = requests.get(url, headers={"Authorization": f"Bearer {key}"}, timeout=8)
                    if r.status_code == 200:
                        try:
                            data = r.json()
                            cnt = len(data.get("data", [])) if isinstance(data, dict) else None
                        except Exception:
                            cnt = None
                        wx.CallAfter(self.status_text.SetLabel, "连通正常")
                        msg = f"✅ 连通正常{f'（API有{cnt}个模型）' if cnt is not None else ''}"
                        wx.CallAfter(wx.MessageBox, msg, "测试API", wx.OK | wx.ICON_INFORMATION)
                    else:
                        wx.CallAfter(self.status_text.SetLabel, "测试失败")
                        wx.CallAfter(wx.MessageBox, f"❌ {r.status_code}: {r.text[:200]}", "测试API", wx.OK | wx.ICON_ERROR)
                except Exception as e:
                    wx.CallAfter(self.status_text.SetLabel, "测试失败")
                    wx.CallAfter(wx.MessageBox, f"请求失败: {e}", "测试API", wx.OK | wx.ICON_ERROR)
                finally:
                    wx.CallAfter(self.test_btn.SetLabel, "🧪 测试API")
                    wx.CallAfter(self.test_btn.Enable, True)

            threading.Thread(target=run, daemon=True).start()
        else:
            wx.MessageBox("DashScope 暂无连通性测试，请直接用音频执行一次识别验证。", "提示", wx.OK | wx.ICON_INFORMATION)
            self.status_text.SetLabel("已提示：DashScope 无测试接口")



    def on_manage_api_keys(self, event):
        dlg = ManageAPIKeysDialog(self)
        result = dlg.ShowModal()
        if result == wx.ID_OK:
            sel = dlg.get_selected()
            if sel and sel.get('key'):
                prov = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
                self.api_key = sel['key']
                self.api_keys[prov] = self.api_key
                self.api_key_ctrl.SetValue(self.api_key)
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
        prov = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
        key = self.api_keys.get(prov, '') if hasattr(self, 'api_keys') else (self.api_key or '')
        if not key:
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
            # 构造 Pipeline 配置（依赖注入，避免写全局）
            provider = 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope'
            # SiliconFlow Base URL（可选）
            siliconflow_base = None
            if provider == 'siliconflow' and hasattr(self, 'asr_base_url_ctrl'):
                try:
                    bu = (self.asr_base_url_ctrl.GetValue().strip() or "")
                    if bu:
                        bu = bu.rstrip('/')
                        if bu.endswith('/v1'):
                            bu = bu[:-3]
                        siliconflow_base = bu
                except Exception:
                    siliconflow_base = None
            # Persist in-memory base URL for SiliconFlow
            if siliconflow_base:
                self.base_urls['siliconflow'] = siliconflow_base

            cfg = PipelineConfig(
                provider=provider,
                model=self.model_choice.GetStringSelection(),
                language=self.settings.get('language', 'zh'),
                keys=ProviderKeys(
                    dashscope=self.api_keys.get('dashscope'),
                    siliconflow=self.api_keys.get('siliconflow'),
                ),
                base_urls=ProviderEndpoints(
                    siliconflow=siliconflow_base,
                ),
                vad_threshold=self.settings.get('vad_threshold', 0.5),
                context=self.settings.get('context', ''),
            )

            output_dir = self.output_dir_override if self.output_dir_override else str(_Path(self.uploaded_file_path).parent)
            pipeline = Pipeline(output_dir=output_dir, context_prompt=None, config=cfg)

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
                # Load per-provider keys and base URLs (with backward compatibility)
                prov_in_cfg = 'siliconflow' if config.get('asr_provider') == 'siliconflow' else 'dashscope'
                if not hasattr(self, 'api_keys'):
                    self.api_keys = {'dashscope': '', 'siliconflow': ''}
                if not hasattr(self, 'base_urls'):
                    self.base_urls = {'siliconflow': 'https://api.siliconflow.cn'}
                self.api_keys['dashscope'] = config.get('ds_api_key', '') or (config.get('api_key', '') if prov_in_cfg == 'dashscope' else '')
                self.api_keys['siliconflow'] = config.get('sf_api_key', '') or (config.get('api_key', '') if prov_in_cfg == 'siliconflow' else '')
                self.base_urls['siliconflow'] = config.get('sf_base_url', config.get('asr_base_url', '')) or 'https://api.siliconflow.cn'

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
                # Base URL is applied on provider change from in-memory store

            except Exception as e:
                print(f"加载配置失败: {e}")

    def save_config(self):
        config = {
            'language': self.settings['language'],
            'vad_threshold': self.settings['vad_threshold'],
            'context': self.context_ctrl.GetValue(),
            'ds_api_key': self.api_keys.get('dashscope', ''),
            'sf_api_key': self.api_keys.get('siliconflow', ''),
            'sf_base_url': self.base_urls.get('siliconflow', ''),
            'asr_provider': 'siliconflow' if self.provider_choice.GetSelection() == 1 else 'dashscope',
            'asr_model': self.model_choice.GetStringSelection(),
        }
        try:
            with open(CONFIG_DIR / "wx_gui_config.json", 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存配置失败: {e}")

