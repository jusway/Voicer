import wx
import json
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
        self.SetSize((420, 360))
        self.path = CONFIG_DIR / "wx_gui_textpolish_presets.json"
        self.items = self._load_items()
        self._build_ui()

    # ---------- UI ----------
    def _build_ui(self):
        vbox = wx.BoxSizer(wx.VERTICAL)

        self.list_box = wx.ListBox(self, choices=[it.get("name", "") for it in self.items])
        vbox.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 8)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        btn_row.AddStretchSpacer(1)
        self.ok_btn = wx.Button(self, wx.ID_OK, "使用所选")
        self.cancel_btn = wx.Button(self, wx.ID_CANCEL, "取消")
        btn_row.Add(self.ok_btn, 0, wx.ALL, 6)
        btn_row.Add(self.cancel_btn, 0, wx.ALL, 6)
        vbox.Add(btn_row, 0, wx.EXPAND | wx.RIGHT | wx.BOTTOM, 6)

        self.SetSizerAndFit(vbox)

        # Events
        self.list_box.Bind(wx.EVT_LISTBOX_DCLICK, self._on_accept)
        self.Bind(wx.EVT_BUTTON, self._on_accept, self.ok_btn)
        self.list_box.Bind(wx.EVT_CONTEXT_MENU, self._on_context_menu)
        # 常用快捷键
        self.list_box.Bind(wx.EVT_CHAR_HOOK, self._on_key)

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

    # ---------- Actions ----------
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

