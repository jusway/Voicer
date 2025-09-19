import wx

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

