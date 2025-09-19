import wx, json
from src.gui_wx.paths import CONFIG_DIR

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

