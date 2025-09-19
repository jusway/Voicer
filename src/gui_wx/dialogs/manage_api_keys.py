import wx, json
from src.gui_wx.paths import CONFIG_DIR

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

