import os
import json
import threading
from pathlib import Path as _Path

import wx
import wx.lib.scrolledpanel as scrolled
from openai import OpenAI

from src.utils.text_diff import generate_html_diff_dmp
from src.gui_wx.paths import CONFIG_DIR
from src.gui_wx.dialogs.manage_presets import ManageTextPolishPresetsDialog


class TextPolishPanel(wx.Panel):
    """
    文本规范/文本润色 独立面板：
    - 选择 txt 输入/输出
    - OpenAI 兼容模型列表获取
    - 系统提示词、温度、few-shot 历史（成对）
    - 流式生成 + 输出文件 + 差异浏览 HTML
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.gemini_api_key = ""
        self.input_txt_path = ""
        self.output_dir_override = ""
        self.current_system_instruction = None
        self._saved_model_name = None

        vbox = wx.BoxSizer(wx.VERTICAL)

        # 标题
        title = wx.StaticText(self, label="📝 文本规范/文本润色")
        font = title.GetFont(); font.PointSize += 3; title.SetFont(font)
        vbox.Add(title, 0, wx.ALL, 10)

        # OpenAI 兼容中转 + 模型
        api_box = wx.StaticBox(self, label="� OpenAI 兼容中转")
        api_sizer = wx.StaticBoxSizer(api_box, wx.VERTICAL)

        base_row = wx.BoxSizer(wx.HORIZONTAL)
        base_row.Add(wx.StaticText(self, label="Base URL:"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.base_url_ctrl = wx.TextCtrl(self, value="")
        base_row.Add(self.base_url_ctrl, 1, wx.ALL | wx.EXPAND, 5)

        api_sizer.Add(base_row, 0, wx.EXPAND)

        api_key_row = wx.BoxSizer(wx.HORIZONTAL)
        api_key_row.Add(wx.StaticText(self, label="API Key:"), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.openai_api_key_ctrl = wx.TextCtrl(self, style=wx.TE_PASSWORD)
        api_key_row.Add(self.openai_api_key_ctrl, 1, wx.ALL | wx.EXPAND, 5)
        api_sizer.Add(api_key_row, 0, wx.EXPAND)

        model_row = wx.BoxSizer(wx.HORIZONTAL)
        model_row.Add(wx.StaticText(self, label="模型："), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.model_choice = wx.Choice(self, choices=["加载中..."])
        model_row.Add(self.model_choice, 1, wx.ALL | wx.EXPAND, 5)
        self.refresh_models_btn = wx.Button(self, label="刷新模型列表")
        self.refresh_models_btn.Bind(wx.EVT_BUTTON, self.on_refresh_models)
        model_row.Add(self.refresh_models_btn, 0, wx.ALL, 5)
        api_sizer.Add(model_row, 0, wx.EXPAND)

        vbox.Add(api_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # 系统提示词
        sys_box = wx.StaticBox(self, label="� 文本规范配置")
        sys_sizer = wx.StaticBoxSizer(sys_box, wx.VERTICAL)
        sys_sizer.Add(wx.StaticText(self, label="系统提示词"), 0, wx.LEFT | wx.TOP, 5)
        self.sys_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE, size=(-1, 90))
        sys_sizer.Add(self.sys_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        # 配置保存/读取
        btns = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_save_preset = wx.Button(self, label="保存当前配置")
        self.btn_load_preset = wx.Button(self, label="读取已保存配置")
        self.btn_save_preset.Bind(wx.EVT_BUTTON, self.on_save_current_preset)
        self.btn_load_preset.Bind(wx.EVT_BUTTON, self.on_load_saved_preset)
        btns.Add(self.btn_save_preset, 0, wx.ALL, 5)
        btns.Add(self.btn_load_preset, 0, wx.ALL, 5)
        sys_sizer.Add(btns, 0, wx.EXPAND)
        vbox.Add(sys_sizer, 1, wx.ALL | wx.EXPAND, 10)

        # 生成参数（并入“文本规范配置”）
        temp_row = wx.BoxSizer(wx.HORIZONTAL)
        temp_row.Add(wx.StaticText(self, label="温度 (0.0-1.0)："), 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        self.temp_slider = wx.Slider(self, value=10, minValue=0, maxValue=100)
        self.temp_label = wx.StaticText(self, label="0.10")
        self.temp_slider.Bind(wx.EVT_SLIDER, self.on_temp_change)
        temp_row.Add(self.temp_slider, 1, wx.ALL | wx.EXPAND, 5)
        temp_row.Add(self.temp_label, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        sys_sizer.Add(temp_row, 0, wx.EXPAND)

        # 输入/输出
        io_box = wx.StaticBox(self, label="📁 输入/输出")
        io_sizer = wx.StaticBoxSizer(io_box, wx.VERTICAL)

        in_row = wx.BoxSizer(wx.HORIZONTAL)
        self.input_label = wx.StaticText(self, label="未选择 txt 文件")
        self.btn_select_input = wx.Button(self, label="选择 txt 文件")
        self.btn_select_input.Bind(wx.EVT_BUTTON, self.on_select_input)
        in_row.Add(self.btn_select_input, 0, wx.ALL, 5)
        in_row.Add(self.input_label, 1, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 5)
        io_sizer.Add(in_row, 0, wx.EXPAND)


        vbox.Add(io_sizer, 0, wx.ALL | wx.EXPAND, 10)

        # 历史对话对（user→assistant）编辑器
        pairs_hdr = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_pair = wx.Button(self, label="新增一组 (user→assistant)")
        self.btn_add_pair.Bind(wx.EVT_BUTTON, self.on_add_pair)
        pairs_hdr.Add(self.btn_add_pair, 0, wx.ALL, 5)
        sys_sizer.Add(pairs_hdr, 0, wx.EXPAND)

        self.pairs_container = scrolled.ScrolledPanel(self)
        self.pairs_sizer = wx.BoxSizer(wx.VERTICAL)
        self.pairs_container.SetSizer(self.pairs_sizer)
        self.pairs_container.SetupScrolling(scroll_x=False, scroll_y=True)
        sys_sizer.Add(self.pairs_container, 1, wx.ALL | wx.EXPAND, 5)

        # 生成预览（流式）
        preview_box = wx.StaticBox(self, label="生成预览")
        preview_sizer = wx.StaticBoxSizer(preview_box, wx.VERTICAL)
        self.preview_ctrl = wx.TextCtrl(self, style=wx.TE_MULTILINE | wx.TE_READONLY, size=(-1, 44))
        preview_sizer.Add(self.preview_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        vbox.Add(preview_sizer, 0, wx.ALL | wx.EXPAND, 10)
        wx.CallAfter(lambda: (self.preview_ctrl.SetMinSize((-1, self.preview_ctrl.GetCharHeight()*2 + 8)), self.Layout()))

        # 开始按钮
        self.run_btn = wx.Button(self, label="🚀 开始文本规范")
        self.run_btn.Bind(wx.EVT_BUTTON, self.on_start_polish)
        vbox.Add(self.run_btn, 0, wx.ALL | wx.ALIGN_RIGHT, 10)

        self.SetSizer(vbox)

    # ---------- 交互逻辑 ----------
    def on_temp_change(self, event):
        self.temp_label.SetLabel(f"{self.temp_slider.GetValue()/100.0:.2f}")

    def on_model_change(self, event):
        return

    def on_add_pair(self, event):
        self._add_history_pair()

    def _add_history_pair(self, user_text: str = "", assistant_text: str = ""):
        if not hasattr(self, "history_pairs"):
            self.history_pairs = []
        panel = wx.Panel(self.pairs_container)
        box = wx.StaticBox(panel, label="对话组")
        s = wx.StaticBoxSizer(box, wx.VERTICAL)

        s.Add(wx.StaticText(panel, label="User"), 0, wx.LEFT | wx.TOP, 5)
        user_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 80))
        user_ctrl.SetValue(user_text or "")
        s.Add(user_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        s.Add(wx.StaticText(panel, label="Assistant"), 0, wx.LEFT | wx.TOP, 5)
        assistant_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 80))
        assistant_ctrl.SetValue(assistant_text or "")
        s.Add(assistant_ctrl, 0, wx.ALL | wx.EXPAND, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        del_btn = wx.Button(panel, label="删除本组")
        def _on_del(evt, p=panel):
            self._remove_history_pair(p)
        del_btn.Bind(wx.EVT_BUTTON, _on_del)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(del_btn, 0, wx.ALL, 5)
        s.Add(btn_row, 0, wx.EXPAND)

        panel.SetSizer(s)
        self.pairs_sizer.Add(panel, 0, wx.ALL | wx.EXPAND, 5)
        self.pairs_container.Layout()
        self.pairs_container.SetupScrolling()
        self.Layout()
        try:
            wx.CallAfter(lambda: self.pairs_container.ScrollChildIntoView(panel))
        except Exception:
            pass
        self.history_pairs.append({"panel": panel, "user": user_ctrl, "assistant": assistant_ctrl})

    def _remove_history_pair(self, panel: wx.Panel):
        if not hasattr(self, "history_pairs"):
            return
        idx = None
        for i, item in enumerate(self.history_pairs):
            if item.get("panel") is panel:
                idx = i; break
        if idx is not None:
            item = self.history_pairs.pop(idx)
            try:
                item["panel"].Destroy()
            except Exception:
                pass
            self.pairs_container.Layout()
            self.pairs_container.SetupScrolling()
            self.Layout()

    def _clear_history_pairs(self):
        if not hasattr(self, "history_pairs"):
            self.history_pairs = []
            return
        while self.history_pairs:
            item = self.history_pairs.pop()
            try:
                item["panel"].Destroy()
            except Exception:
                pass
        self.pairs_container.Layout()
        self.pairs_container.SetupScrolling()
        self.Layout()

    def _get_history_messages_from_pairs(self) -> list:
        msgs = []
        if not hasattr(self, "history_pairs"):
            return msgs
        for item in self.history_pairs:
            ut = (item["user"].GetValue() or "").strip()
            at = (item["assistant"].GetValue() or "").strip()
            if ut:
                msgs.append({"role": "user", "content": ut})
            if at:
                msgs.append({"role": "assistant", "content": at})
        return msgs

    def _apply_history_list(self, hist: list):
        self._clear_history_pairs()
        if not isinstance(hist, list):
            return
        i = 0
        n = len(hist)
        while i < n:
            h = hist[i] or {}
            role = (h.get("role") or "").lower()
            txt = h.get("text") or h.get("content") or ""
            user_text, assistant_text = "", ""
            if role == "user":
                user_text = txt
                if i + 1 < n:
                    h2 = hist[i + 1] or {}
                    role2 = (h2.get("role") or "").lower()
                    if role2 in ("assistant", "model"):
                        assistant_text = h2.get("text") or h2.get("content") or ""
                        i += 2
                    else:
                        i += 1
                else:
                    i += 1
            elif role in ("assistant", "model"):
                assistant_text = txt
                i += 1
            else:
                i += 1
                continue
            self._add_history_pair(user_text, assistant_text)

    def _pairs_to_history(self) -> list:
        hist = []
        if hasattr(self, "history_pairs"):
            for it in self.history_pairs:
                u = (it["user"].GetValue() or "").strip()
                a = (it["assistant"].GetValue() or "").strip()
                if u:
                    hist.append({"role": "user", "text": u})
                if a:
                    hist.append({"role": "assistant", "text": a})
        return hist

    def _normalize_openai_base_url(self, base: str) -> str:
        """Normalize user-entered Base URL to ensure it ends with '/v1'.
        Accepts inputs with or without trailing slash or '/v1/'.
        Returns empty string if input is empty.
        """
        b = (base or "").strip().rstrip("/")
        if not b:
            return ""
        return b if b.endswith("/v1") else (b + "/v1")


    def on_save_current_preset(self, event):
        try:
            name = wx.GetTextFromUser("名称：", "保存配置").strip()
            if not name:
                return
            item = {
                "name": name,
                "system": self.sys_ctrl.GetValue(),
                "temperature": self.temp_slider.GetValue() / 100.0,
                "history": self._pairs_to_history(),
            }
            path = CONFIG_DIR / "wx_gui_textpolish_presets.json"
            items = []
            if path.exists():
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        items = json.load(f) or []
                    if not isinstance(items, list):
                        items = []
                except Exception:
                    items = []
            exists = any((i.get("name") == name) for i in items)
            if exists:
                dlg = wx.MessageDialog(self, f"已存在同名配置“{name}”，是否覆盖？", "确认", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
                res = dlg.ShowModal()
                dlg.Destroy()
                if res != wx.ID_YES:
                    return
                items = [i for i in items if i.get("name") != name]
            items.append(item)
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            wx.MessageBox("已保存", "提示")
        except Exception as e:
            wx.MessageBox(f"保存失败: {e}", "错误", wx.OK | wx.ICON_ERROR)

    def on_load_saved_preset(self, event):
        path = CONFIG_DIR / "wx_gui_textpolish_presets.json"
        items = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    items = json.load(f) or []
                if not isinstance(items, list):
                    items = []
            except Exception:
                items = []
        if not items:
            wx.MessageBox("暂无已保存配置", "提示", wx.OK | wx.ICON_INFORMATION)
            return
        names = [i.get("name", "") for i in items]
        dlg = wx.SingleChoiceDialog(self, "选择配置：", "读取已保存配置", names)
        sel = None
        if dlg.ShowModal() == wx.ID_OK:
            idx = dlg.GetSelection()
            if 0 <= idx < len(items):
                sel = items[idx]
        dlg.Destroy()
        if not sel:
            return
        actions = ["读取", "重命名", "删除", "取消"]
        dlg2 = wx.SingleChoiceDialog(self, "选择操作：", "已保存配置", actions)
        act = None
        if dlg2.ShowModal() == wx.ID_OK:
            idx2 = dlg2.GetSelection()
            if 0 <= idx2 < len(actions):
                act = actions[idx2]
        dlg2.Destroy()
        if not act or act == "取消":
            return
        path = CONFIG_DIR / "wx_gui_textpolish_presets.json"
        items2 = []
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    items2 = json.load(f) or []
                if not isinstance(items2, list):
                    items2 = []
            except Exception:
                items2 = []
        name_sel = sel.get("name", "")
        if act == "删除":
            dlgc = wx.MessageDialog(self, f"确定删除配置“{name_sel}”吗？", "确认删除", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
            res = dlgc.ShowModal(); dlgc.Destroy()
            if res != wx.ID_YES:
                return
            items2 = [i for i in items2 if i.get("name") != name_sel]
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(items2, f, ensure_ascii=False, indent=2)
                wx.MessageBox("已删除", "提示")
            except Exception as e:
                wx.MessageBox(f"删除失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
            return
        if act == "重命名":
            new_name = wx.GetTextFromUser("新名称：", "重命名").strip()
            if not new_name:
                return
            if new_name != name_sel and any(i.get("name") == new_name for i in items2):
                dlgc = wx.MessageDialog(self, f"已存在同名“{new_name}”，是否覆盖？", "确认", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_QUESTION)
                res = dlgc.ShowModal(); dlgc.Destroy()
                if res != wx.ID_YES:
                    return
                items2 = [i for i in items2 if i.get("name") != new_name]
            sel["name"] = new_name
            items2 = [i for i in items2 if i.get("name") != name_sel]
            items2.append(sel)
            try:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(items2, f, ensure_ascii=False, indent=2)
                wx.MessageBox("已重命名", "提示")
            except Exception as e:
                wx.MessageBox(f"重命名失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
        try:
            self.sys_ctrl.SetValue(sel.get("system", ""))
            temp = float(sel.get("temperature", 0.2))
            self.temp_slider.SetValue(int(max(0, min(1, temp)) * 100))
            self.temp_label.SetLabel(f"{self.temp_slider.GetValue()/100.0:.2f}")
            self._apply_history_list(sel.get("history", []))
        except Exception:
            pass

    def on_select_input(self, event):
        dlg = wx.FileDialog(self, "选择 txt 文件", wildcard="文本文件 (*.txt)|*.txt", style=wx.FD_OPEN)
        if dlg.ShowModal() == wx.ID_OK:
            self.input_txt_path = dlg.GetPath()
            self.input_label.SetLabel(f"✅ {os.path.basename(self.input_txt_path)}")
        dlg.Destroy()


    def on_refresh_models(self, event):
        raw_base = (self.base_url_ctrl.GetValue().strip() or "")
        base_url = self._normalize_openai_base_url(raw_base)
        key = (self.openai_api_key_ctrl.GetValue().strip() or "")
        if not base_url or not key:
            wx.MessageBox("请先填写 Base URL 与 API Key", "提示", wx.OK | wx.ICON_INFORMATION)
            self.model_choice.Set(["<无可用模型>"])
            return
        names = []
        try:
            client = OpenAI(base_url=base_url, api_key=key)
            resp = client.models.list()
            names = [getattr(m, "id", "") for m in getattr(resp, "data", []) if getattr(m, "id", "")]
        except Exception:
            names = []
        if not names:
            names = ["<无可用模型>"]
        self.model_choice.Set(names)
        if names and names[0] != "<无可用模型>":
            idx = 0
            try:
                if getattr(self, "_saved_model_name", None) and self._saved_model_name in names:
                    idx = names.index(self._saved_model_name)
            except Exception:
                idx = 0
            self.model_choice.SetSelection(idx)

    # ===== Config (persist base_url, api_key, model) =====
    def load_config(self):
        path = CONFIG_DIR / "wx_gui_textpolish_config.json"
        if path.exists():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cfg = json.load(f) or {}
                self.base_url_ctrl.SetValue(cfg.get("base_url", "") or "")
                self.openai_api_key_ctrl.SetValue(cfg.get("api_key", "") or "")
                self._saved_model_name = (cfg.get("model", "") or None)
                try:
                    if self._saved_model_name:
                        self.model_choice.SetStringSelection(self._saved_model_name)
                except Exception:
                    pass
            except Exception as e:
                print(f"加载文本规范配置失败: {e}")

    def save_config(self):
        cfg = {
            "base_url": self.base_url_ctrl.GetValue().strip(),
            "api_key": self.openai_api_key_ctrl.GetValue().strip(),
            "model": (self.model_choice.GetStringSelection() or ""),
        }
        try:
            with open(CONFIG_DIR / "wx_gui_textpolish_config.json", "w", encoding="utf-8") as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存文本规范配置失败: {e}")




    def on_manage_presets(self, event):
        dlg = ManageTextPolishPresetsDialog(self)
        sel = None
        if dlg.ShowModal() == wx.ID_OK:
            sel = dlg.get_selected()
        dlg.Destroy()
        if sel:
            self.sys_ctrl.SetValue(sel.get("system", ""))
            try:
                temp = float(sel.get("temperature", 0.2))
            except Exception:
                temp = 0.2
            self.temp_slider.SetValue(int(max(0.0, min(1.0, temp)) * 100))
            self.temp_label.SetLabel(f"{self.temp_slider.GetValue()/100.0:.2f}")
            try:
                hist = sel.get("history", [])
                self._apply_history_list(hist)
            except Exception:
                pass

    # ---------- 运行 ----------
    def _build_output_path(self, in_path: str, out_dir: str | None) -> str:
        p = _Path(in_path)
        d = _Path(out_dir) if out_dir else p.parent
        return str(d / f"{p.stem}(校对后).txt")

    def on_start_polish(self, event):
        base_url = self.base_url_ctrl.GetValue().strip()
        norm_base_url = self._normalize_openai_base_url(base_url)
        key = self.openai_api_key_ctrl.GetValue().strip()
        if not norm_base_url or not key:
            wx.MessageBox("请填写 Base URL 与 API Key", "错误", wx.OK | wx.ICON_ERROR)
            return
        if not self.input_txt_path or not _Path(self.input_txt_path).exists():
            wx.MessageBox("请先选择有效的 txt 文件", "错误", wx.OK | wx.ICON_ERROR)
            return
        model = self.model_choice.GetStringSelection() or ""
        temperature = self.temp_slider.GetValue() / 100.0
        sys_inst = self.sys_ctrl.GetValue().strip() or None
        try:
            with open(self.input_txt_path, "r", encoding="utf-8") as f:
                file_text = f.read()
        except Exception as e:
            wx.MessageBox(f"读取输入失败: {e}", "错误", wx.OK | wx.ICON_ERROR)
            return
        messages = []
        if sys_inst:
            messages.append({"role": "system", "content": sys_inst})
        messages.extend(self._get_history_messages_from_pairs())
        messages.append({"role": "user", "content": file_text})
        try:
            self.run_btn.Enable(False)
        except Exception:
            pass
        if hasattr(self, "preview_ctrl") and self.preview_ctrl:
            self.preview_ctrl.SetValue("")
        out_dir = None
        out_path = self._build_output_path(self.input_txt_path, out_dir)

        def worker():
            out_chunks = []
            try:
                client = OpenAI(base_url=norm_base_url, api_key=key)
                stream = client.chat.completions.create(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    stream=True,
                    timeout=60,
                )
                for chunk in stream:
                    try:
                        delta = getattr(chunk.choices[0].delta, "content", None)
                    except Exception:
                        delta = None
                    if delta:
                        out_chunks.append(delta)
                        if hasattr(self, "preview_ctrl") and self.preview_ctrl:
                            wx.CallAfter(self.preview_ctrl.AppendText, delta)
                out_text = "".join(out_chunks)
                try:
                    _Path(out_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(out_path, "w", encoding="utf-8") as f:
                        f.write(out_text)
                    in_path = self.input_txt_path
                    p_in = _Path(in_path)
                    d_dir = _Path(out_dir) if out_dir else p_in.parent
                    diff_path = str(d_dir / f"{p_in.stem}(差异浏览).html")
                    try:
                        generate_html_diff_dmp(
                            file1_path=str(p_in),
                            file2_path=str(out_path),
                            output_path=diff_path,
                            fromdesc=p_in.name,
                            todesc=_Path(out_path).name,
                            cleanup='none',
                            use_line_mode=False,
                        )
                        wx.CallAfter(lambda: wx.MessageBox(
                            f"✅ 完成，已输出：\n{out_path}\n\n并生成差异浏览：\n{diff_path}",
                            "成功", wx.OK | wx.ICON_INFORMATION))
                    except Exception as ediff:
                        wx.CallAfter(lambda: wx.MessageBox(
                            f"✅ 文本已输出，但生成差异浏览失败：{ediff}\n\n输出：{out_path}",
                            "部分成功", wx.OK | wx.ICON_WARNING))
                except Exception as e2:
                    wx.CallAfter(lambda: wx.MessageBox(f"写出失败: {e2}", "错误", wx.OK | wx.ICON_ERROR))
            except Exception as e:
                wx.CallAfter(lambda: wx.MessageBox(f"调用模型失败: {e}", "错误", wx.OK | wx.ICON_ERROR))
            finally:
                wx.CallAfter(lambda: self.run_btn.Enable(True))

        threading.Thread(target=worker, daemon=True).start()
        return

