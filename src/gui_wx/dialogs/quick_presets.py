import wx
import json
import wx.lib.scrolledpanel as scrolled

from src.gui_wx.paths import CONFIG_DIR


class QuickPresetsDialog(wx.Dialog):
    """
    单层快速选择/管理 文本规范配置 预设：
    - 列表：双击/回车/“使用所选” = 直接返回所选项
    - 右键菜单：重命名 / 删除（删除带确认）
    存储文件：config/wx_gui_textpolish_presets.json
    """

    def __init__(self, parent):
        super().__init__(parent, title="选择配置", style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.SetSize((960, 640))
        self.path = CONFIG_DIR / "wx_gui_textpolish_presets.json"
        self.items = self._load_items()
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        hsplit = wx.BoxSizer(wx.HORIZONTAL)
        self.list_box = wx.ListBox(self, choices=[it.get("name", "") for it in self.items])
        hsplit.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 8)

        # Right side: Edit layout only
        right_panel = wx.Panel(self)
        ed = right_panel
        ed_sizer = wx.BoxSizer(wx.VERTICAL)
        # Name
        row1 = wx.BoxSizer(wx.HORIZONTAL)
        row1.Add(wx.StaticText(ed, label="名称"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.name_ctrl = wx.TextCtrl(ed)
        row1.Add(self.name_ctrl, 1, wx.EXPAND)
        ed_sizer.Add(row1, 0, wx.ALL | wx.EXPAND, 4)
        # Temperature: Slider + Label (0.00~1.00)
        row2 = wx.BoxSizer(wx.HORIZONTAL)
        row2.Add(wx.StaticText(ed, label="温度"), 0, wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.temp_slider = wx.Slider(ed, minValue=0, maxValue=100)
        row2.Add(self.temp_slider, 1, wx.EXPAND)
        self.temp_label = wx.StaticText(ed, label="0.20")
        row2.Add(self.temp_label, 0, wx.LEFT | wx.ALIGN_CENTER_VERTICAL, 8)
        ed_sizer.Add(row2, 0, wx.ALL | wx.EXPAND, 4)
        # System prompt
        ed_sizer.Add(wx.StaticText(ed, label="系统提示词"), 0, wx.LEFT | wx.TOP, 4)
        self.sys_edit = wx.TextCtrl(ed, style=wx.TE_MULTILINE, size=(-1, 120))
        ed_sizer.Add(self.sys_edit, 0, wx.ALL | wx.EXPAND, 4)
        # History pairs scrolled panel
        self.pairs_container = scrolled.ScrolledPanel(ed)
        self.pairs_sizer = wx.BoxSizer(wx.VERTICAL)
        self.pairs_container.SetSizer(self.pairs_sizer)
        self.pairs_container.SetupScrolling(scroll_x=False, scroll_y=True)
        ed_sizer.Add(self.pairs_container, 1, wx.ALL | wx.EXPAND, 4)
        # Buttons at bottom of edit page
        edit_btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add_pair = wx.Button(ed, label="新增对话组")
        self.btn_save_edit = wx.Button(ed, label="保存修改")
        self.btn_reset_edit = wx.Button(ed, label="重置未保存")
        edit_btn_row.Add(self.btn_add_pair, 0, wx.ALL, 4)
        edit_btn_row.Add(self.btn_save_edit, 0, wx.ALL, 4)
        edit_btn_row.Add(self.btn_reset_edit, 0, wx.ALL, 4)
        edit_btn_row.AddStretchSpacer(1)
        ed_sizer.Add(edit_btn_row, 0, wx.EXPAND | wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)
        ed.SetSizer(ed_sizer)

        hsplit.Add(right_panel, 2, wx.ALL | wx.EXPAND, 8)

        vbox.Add(hsplit, 1, wx.EXPAND)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_rename = wx.Button(self, label="重命名")
        self.btn_delete = wx.Button(self, label="删除")
        btn_row.Add(self.btn_rename, 0, wx.ALL, 6)
        btn_row.Add(self.btn_delete, 0, wx.ALL, 6)
        btn_row.AddStretchSpacer(1)
        self.ok_btn = wx.Button(self, wx.ID_OK, "使用所选")
        self.cancel_btn = wx.Button(self, wx.ID_CANCEL, "取消")
        btn_row.Add(self.ok_btn, 0, wx.ALL, 6)
        btn_row.Add(self.cancel_btn, 0, wx.ALL, 6)
        vbox.Add(btn_row, 0, wx.EXPAND | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizerAndFit(vbox)
        # Ensure dialog starts reasonably large and resizable
        try:
            self.SetMinSize((880, 600))
            self.SetSize((960, 640))
        except Exception:
            pass


        # Events
        self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        self.Bind(wx.EVT_BUTTON, self._on_accept, self.ok_btn)
        # self.list_box.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)  # disabled: use explicit buttons instead
        # 常用快捷键
        self.list_box.Bind(wx.EVT_CHAR_HOOK, self._on_key)
        # 列表选中变化时刷新预览；新增按钮：重命名、删除
        self.list_box.Bind(wx.EVT_LISTBOX, self._on_select_changed)
        self.Bind(wx.EVT_BUTTON, lambda e: (self.list_box.GetSelection() != wx.NOT_FOUND) and self._rename(self.list_box.GetSelection()), self.btn_rename)
        self.Bind(wx.EVT_BUTTON, lambda e: (self.list_box.GetSelection() != wx.NOT_FOUND) and self._delete(self.list_box.GetSelection()), self.btn_delete)
        # Edit page events
        self.name_ctrl.Bind(wx.EVT_TEXT, self._mark_dirty)
        self.sys_edit.Bind(wx.EVT_TEXT, self._mark_dirty)
        self.temp_slider.Bind(wx.EVT_SLIDER, self._on_temp_slider)
        self.btn_add_pair.Bind(wx.EVT_BUTTON, lambda evt: (self._edit_add_pair(), self._mark_dirty()))
        self.btn_save_edit.Bind(wx.EVT_BUTTON, self._on_save_edit)
        self.btn_reset_edit.Bind(wx.EVT_BUTTON, self._on_reset_edit)
        # 初始禁用保存/重置按钮，待有改动时启用
        try:
            self.btn_save_edit.Enable(False)
            self.btn_reset_edit.Enable(False)
        except Exception:
            pass


        # 默认选中第一项并显示预览
        if self.items:
            self.list_box.SetSelection(0)
            self._last_selection = 0

            self._load_edit_from_selected()
            self._edit_dirty = False

    # ---------- Events ----------
    def _on_key(self, event: wx.KeyEvent):
        code = event.GetKeyCode()
        if code in (wx.WXK_RETURN, wx.WXK_NUMPAD_ENTER):
            self._on_accept()
            return
        if code == wx.WXK_DELETE:
            idx = self.list_box.GetSelection()
            if idx != wx.NOT_FOUND:
                self._delete(idx)
                return
        if code == wx.WXK_F2:
            idx = self.list_box.GetSelection()
            if idx != wx.NOT_FOUND:
                self._rename(idx)
                return
        event.Skip()

    def _on_accept(self, event: wx.Event | None = None):
        if self.list_box.GetSelection() != wx.NOT_FOUND:
            self.EndModal(wx.ID_OK)

    def _on_context_menu(self, event: wx.ContextMenuEvent):
        # 使用当前选中项；若无选中，则不弹菜单（简化处理）
        idx = self.list_box.GetSelection()
        if idx == wx.NOT_FOUND:
            return
        menu = wx.Menu()
        mi_rename = menu.Append(-1, "重命名")
        mi_delete = menu.Append(-1, "删除")
        self.Bind(wx.EVT_MENU, lambda e: self._rename(idx), mi_rename)
        self.Bind(wx.EVT_MENU, lambda e: self._delete(idx), mi_delete)
        self.PopupMenu(menu)
        menu.Destroy()

    # ---------- Edit Tab helpers ----------
    def _mark_dirty(self, *_):
        if getattr(self, "_suspend_dirty", False):
            return
        self._edit_dirty = True
        try:
            self.btn_save_edit.Enable(True); self.btn_reset_edit.Enable(True)
        except Exception:
            pass

    def _on_temp_slider(self, event: wx.Event):
        try:
            self.temp_label.SetLabel(f"{self.temp_slider.GetValue()/100.0:.2f}")
        except Exception:
            pass
        self._mark_dirty()

    def _edit_pairs_to_history(self) -> list:
        hist = []
        pairs = getattr(self, "_edit_pairs", [])
        for it in pairs:
            u = (it["user"].GetValue() or "").strip()
            a = (it["assistant"].GetValue() or "").strip()
            if u:
                hist.append({"role": "user", "text": u})
            if a:
                hist.append({"role": "assistant", "text": a})
        return hist

    def _edit_clear_pairs(self):
        if not hasattr(self, "_edit_pairs"):
            self._edit_pairs = []
            return
        while self._edit_pairs:
            item = self._edit_pairs.pop()
            try:
                item["panel"].Destroy()
            except Exception:
                pass
        try:
            self.pairs_container.Layout(); self.pairs_container.SetupScrolling()
            self.Layout()
        except Exception:
            pass

    def _edit_remove_pair(self, panel: wx.Panel):
        if not hasattr(self, "_edit_pairs"):
            return
        idx = None
        for i, item in enumerate(self._edit_pairs):
            if item.get("panel") is panel:
                idx = i; break
        if idx is not None:
            item = self._edit_pairs.pop(idx)
            try:
                item["panel"].Destroy()
            except Exception:
                pass
            try:
                self.pairs_container.Layout(); self.pairs_container.SetupScrolling(); self.Layout()
            except Exception:
                pass

    def _edit_add_pair(self, user_text: str = "", assistant_text: str = ""):
        if not hasattr(self, "_edit_pairs"):
            self._edit_pairs = []
        panel = wx.Panel(self.pairs_container)
        box = wx.StaticBox(panel, label="对话组")
        s = wx.StaticBoxSizer(box, wx.VERTICAL)
        s.Add(wx.StaticText(panel, label="用户"), 0, wx.LEFT | wx.TOP, 5)
        user_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 120))
        if user_text:
            user_ctrl.SetValue(user_text)
        s.Add(user_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        s.Add(wx.StaticText(panel, label="助手"), 0, wx.LEFT | wx.TOP, 5)
        assistant_ctrl = wx.TextCtrl(panel, style=wx.TE_MULTILINE, size=(-1, 120))
        if assistant_text:
            assistant_ctrl.SetValue(assistant_text)
        s.Add(assistant_ctrl, 0, wx.ALL | wx.EXPAND, 5)
        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        del_btn = wx.Button(panel, label="删除本组")
        def _on_del(evt, p=panel):
            self._edit_remove_pair(p); self._mark_dirty()
        del_btn.Bind(wx.EVT_BUTTON, _on_del)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(del_btn, 0, wx.ALL, 5)
        s.Add(btn_row, 0, wx.EXPAND)
        panel.SetSizer(s)
        self.pairs_sizer.Add(panel, 0, wx.ALL | wx.EXPAND, 5)
        try:
            self.pairs_container.Layout(); self.pairs_container.SetupScrolling(); self.Layout()
            wx.CallAfter(lambda: self.pairs_container.ScrollChildIntoView(panel))
        except Exception:
            pass
        self._edit_pairs.append({"panel": panel, "user": user_ctrl, "assistant": assistant_ctrl})
        user_ctrl.Bind(wx.EVT_TEXT, self._mark_dirty)
        assistant_ctrl.Bind(wx.EVT_TEXT, self._mark_dirty)

    def _edit_apply_history_list(self, hist: list):
        self._edit_clear_pairs()
        if not isinstance(hist, list):
            return
        i, n = 0, len(hist)
        while i < n:
            h = hist[i] or {}
            role = (h.get("role") or "").strip().lower()
            txt = h.get("text") or h.get("content") or ""
            user_text, assistant_text = "", ""
            if role == "user":
                user_text = txt
                if i + 1 < n:
                    h2 = hist[i + 1] or {}
                    role2 = (h2.get("role") or "").strip().lower()
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
            self._edit_add_pair(user_text, assistant_text)

    def _load_edit_from_selected(self):
        it = self.get_selected()
        if not it:
            return
        self._suspend_dirty = True
        try:
            # Use ChangeValue to avoid EVT_TEXT during programmatic set
            try:
                self.name_ctrl.ChangeValue(it.get("name", ""))
            except Exception:
                self.name_ctrl.SetValue(it.get("name", ""))
            t = 0.2
            try:
                t = float(it.get("temperature", 0.2))
            except Exception:
                t = 0.2
            try:
                self.temp_slider.SetValue(int(round(t * 100)))
            except Exception:
                pass
            try:
                self.temp_label.SetLabel(f"{t:.2f}")
            except Exception:
                pass
            try:
                self.sys_edit.ChangeValue(it.get("system", "") or "")
            except Exception:
                self.sys_edit.SetValue(it.get("system", "") or "")
            self._edit_apply_history_list(it.get("history", []) or [])
            self._edit_dirty = False
            try:
                self.btn_save_edit.Enable(False); self.btn_reset_edit.Enable(False)
            except Exception:
                pass
        except Exception:
            pass
        finally:
            self._suspend_dirty = False

    def _collect_edit_to_item(self) -> dict:
        name = self.name_ctrl.GetValue() or ""
        t = 0.2
        try:
            t = max(0.0, min(1.0, float(self.temp_slider.GetValue()) / 100.0))
        except Exception:
            pass
        sys_text = self.sys_edit.GetValue() or ""
        hist = self._edit_pairs_to_history()
        return {"name": name, "temperature": t, "system": sys_text, "history": hist}

    def _on_save_edit(self, event: wx.Event | None = None):
        idx = self.list_box.GetSelection()
        if idx == wx.NOT_FOUND or not (0 <= idx < len(self.items)):
            return
        new_it = self._collect_edit_to_item()
        self.items[idx].update(new_it)
        try:
            self.list_box.SetString(idx, new_it.get("name", ""))
        except Exception:
            pass
        self._save_items()
        self._edit_dirty = False
        try:
            self.btn_save_edit.Enable(False); self.btn_reset_edit.Enable(False)
        except Exception:
            pass

    def _on_reset_edit(self, event: wx.Event | None = None):
        self._load_edit_from_selected()
        self._edit_dirty = False
        try:
            self.btn_save_edit.Enable(False); self.btn_reset_edit.Enable(False)
        except Exception:
            pass

    def _on_select_changed(self, event: wx.Event):
        new_idx = self.list_box.GetSelection()
        if new_idx == wx.NOT_FOUND:
            return
        if getattr(self, "_edit_dirty", False):
            dlg = wx.MessageDialog(self, "当前编辑未保存，是否保存？", "提示", wx.YES_NO | wx.CANCEL | wx.ICON_QUESTION)
            res = dlg.ShowModal()
            dlg.Destroy()
            if res == wx.ID_YES:
                self._on_save_edit()
            elif res == wx.ID_CANCEL:
                # revert selection
                prev = getattr(self, "_last_selection", -1)
                if prev is not None and prev != -1 and prev != wx.NOT_FOUND:
                    try:
                        self.list_box.SetSelection(prev)
                    except Exception:
                        pass
                return
            else:
                # NO: discard changes
                pass
        self._last_selection = new_idx
        self._load_edit_from_selected()
        self._edit_dirty = False
        try:
            self.btn_save_edit.Enable(False); self.btn_reset_edit.Enable(False)
        except Exception:
            pass
    def _rename(self, idx: int):
        old = self.items[idx].get("name", "")
        new_name = wx.GetTextFromUser("新名称：", "重命名", value=old).strip()
        if not new_name:
            return
        # 允许重名；如需唯一性可在此处校验并提示
        self.items[idx]["name"] = new_name
        self.list_box.SetString(idx, new_name)
        self._save_items()

    def _delete(self, idx: int):
        name = self.items[idx].get("name", "")
        dlg = wx.MessageDialog(self, f"确定删除配置“{name}”吗？", "确认删除", wx.YES_NO | wx.NO_DEFAULT | wx.ICON_WARNING)
        res = dlg.ShowModal()
        dlg.Destroy()
        if res != wx.ID_YES:
            return
        del self.items[idx]
        self.list_box.Delete(idx)
        self._save_items()
        # 调整选中项
        if self.items:
            self.list_box.SetSelection(min(idx, len(self.items) - 1))
        self._load_edit_from_selected()
        try:
            self.btn_save_edit.Enable(False); self.btn_reset_edit.Enable(False)
        except Exception:
            pass

    # ---------- Persistence ----------
    def _load_items(self) -> list:
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f) or []
                if isinstance(data, list):
                    return data
        except Exception:
            pass
        return []

    def _save_items(self) -> None:
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except Exception:
            wx.MessageBox("保存失败", "错误", wx.OK | wx.ICON_ERROR)

    # ---------- API ----------
    def get_selected(self) -> dict | None:
        idx = self.list_box.GetSelection()
        if idx != wx.NOT_FOUND and 0 <= idx < len(self.items):
            return self.items[idx]
        return None

