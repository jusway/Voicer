import wx, json
from src.gui_wx.paths import CONFIG_DIR

class ManageOpenAIEndpointsDialog(wx.Dialog):
    """管理 OpenAI 兼容中转（base_url + key）"""
    def __init__(self, parent):
        super().__init__(parent, title="管理中转站（base_url + API Key）")
        self.path = CONFIG_DIR / "wx_gui_openai_endpoints.json"
        self.items = self._load_items()

        vbox = wx.BoxSizer(wx.VERTICAL)
        self.list_box = wx.ListBox(self, choices=[it.get("name", "") for it in self.items])
        vbox.Add(self.list_box, 1, wx.ALL | wx.EXPAND, 5)

        btn_row = wx.BoxSizer(wx.HORIZONTAL)
        self.btn_add = wx.Button(self, label="添加")
        self.btn_del = wx.Button(self, label="删除")
        self.btn_ok = wx.Button(self, label="使用所选")
        self.btn_cancel = wx.Button(self, label="取消")
        self.btn_add.Bind(wx.EVT_BUTTON, self.on_add)
        self.btn_del.Bind(wx.EVT_BUTTON, self.on_delete)
        self.btn_ok.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_OK))
        self.btn_cancel.Bind(wx.EVT_BUTTON, lambda e: self.EndModal(wx.ID_CANCEL))
        btn_row.Add(self.btn_add, 0, wx.ALL, 5)
        btn_row.Add(self.btn_del, 0, wx.ALL, 5)
        btn_row.AddStretchSpacer(1)
        btn_row.Add(self.btn_ok, 0, wx.ALL, 5)
        btn_row.Add(self.btn_cancel, 0, wx.ALL, 5)
        vbox.Add(btn_row, 0, wx.EXPAND | wx.ALL, 5)

        self.SetSizerAndFit(vbox)

    def _load_items(self):
        try:
            if self.path.exists():
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return data
        except Exception:
            pass
        return []

    def _save_items(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
        except Exception:
            wx.MessageBox("保存失败", "错误", wx.OK | wx.ICON_ERROR)

    def on_add(self, event):
        name_dlg = wx.TextEntryDialog(self, "名称：", "添加 中转站")
        if name_dlg.ShowModal() == wx.ID_OK:
            name = (name_dlg.GetValue() or "").strip()
            if not name:
                wx.MessageBox("名称不能为空", "提示", wx.OK | wx.ICON_WARNING)
                name_dlg.Destroy(); return
            base_dlg = wx.TextEntryDialog(self, "Base URL（例如：http://89.116.64.179:7890/v1）：", "添加 中转站")
            if base_dlg.ShowModal() == wx.ID_OK:
                base_url = (base_dlg.GetValue() or "").strip()
                key_dlg = wx.TextEntryDialog(self, "API Key：", "添加 中转站")
                if key_dlg.ShowModal() == wx.ID_OK:
                    key = (key_dlg.GetValue() or "").strip()
                    self.items.append({"name": name, "base_url": base_url, "key": key})
                    self._save_items()
                    self.list_box.Append(name)
                key_dlg.Destroy()
            base_dlg.Destroy()
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

