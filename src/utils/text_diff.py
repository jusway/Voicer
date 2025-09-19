"""
文本差异 HTML 生成（diff-match-patch 版）

依赖：pip install diff-match-patch
提供函数：generate_html_diff_dmp
"""
from __future__ import annotations

from pathlib import Path

try:
    from diff_match_patch import diff_match_patch  # type: ignore
    _DMP_AVAILABLE = True
except Exception:
    _DMP_AVAILABLE = False


def generate_html_diff_dmp(
    file1_path: str,
    file2_path: str,
    output_path: str,
    *,
    fromdesc: str = "源文件",
    todesc: str = "目标文件",
    cleanup: str = "none",
    use_line_mode: bool = False,
) -> None:
    """使用 diff-match-patch 生成紧凑高亮的 HTML 差异报告。

    参数：
      - cleanup: 'semantic' | 'efficiency' | 'none'（'none' 最精细，可能更碎片化）
      - use_line_mode: True 时先按行压缩再 diff，适合超长文本（牺牲精细度）
    """
    if not _DMP_AVAILABLE:
        raise RuntimeError("未安装 diff-match-patch，请先执行: pip install diff-match-patch")

    file1_path = str(file1_path)
    file2_path = str(file2_path)
    output_path = str(output_path)

    with open(file1_path, "r", encoding="utf-8") as f1:
        text1 = f1.read()
    with open(file2_path, "r", encoding="utf-8") as f2:
        text2 = f2.read()

    dmp = diff_match_patch()
    dmp.Diff_Timeout = 0.0  # 0 表示不超时

    if use_line_mode:
        text1c, text2c, line_array = dmp.diff_linesToChars(text1, text2)
        diffs = dmp.diff_main(text1c, text2c, False)
        dmp.diff_charsToLines(diffs, line_array)
    else:
        diffs = dmp.diff_main(text1, text2, False)

    if cleanup == "semantic":
        dmp.diff_cleanupSemantic(diffs)
    elif cleanup == "efficiency":
        dmp.diff_cleanupEfficiency(diffs)
    # cleanup == 'none' 则不做 cleanup，尽量保留细粒度差异

    body_html = dmp.diff_prettyHtml(diffs)

    html = f"""<!DOCTYPE html>
<html lang=\"zh-CN\">
<head>
  <meta charset=\"utf-8\" />
  <title>文本差异报告 - diff-match-patch</title>
  <style>
    body {{
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans SC', 'PingFang SC', 'Microsoft YaHei', Arial, sans-serif;
      margin: 24px;
      line-height: 1.6;
    }}
    .hdr {{ background:#f7f7f7; border:1px solid #eee; padding:10px 12px; border-radius:6px; margin-bottom:12px; }}
    .hdr b {{ color:#333 }}
    .legend {{ color:#666; font-size:12px; margin-bottom:12px; }}
    .content {{ white-space: pre-wrap; word-break: break-word; }}
    ins {{ background:#aaffaa; text-decoration:none; }}
    del {{ background:#ffaaaa; text-decoration:none; }}
  </style>
</head>
<body>
  <div class=\"hdr\">
    <b>源文件:</b> {fromdesc} &nbsp; → &nbsp; <b>目标文件:</b> {todesc}
  </div>
  <div class=\"legend\">绿色=新增，红色=删除；黄色(若有)=修改。</div>
  <div class=\"content\">{body_html}</div>
</body>
</html>"""

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

