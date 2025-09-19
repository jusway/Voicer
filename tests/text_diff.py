"""
使用 diff-match-patch 生成可视化的 HTML 文本差异报告。

依赖：pip install diff-match-patch
用法：
  1) 默认使用 dmp：    python text_diff.py
  2) 指定使用 dmp：    python text_diff.py dmp 源文件 目标文件 输出.html
"""

import sys


try:
    from diff_match_patch import diff_match_patch  # pip install diff-match-patch
    _DMP_AVAILABLE = True
except Exception:
    _DMP_AVAILABLE = False




def generate_html_diff_dmp(file1_path: str, file2_path: str, output_path: str,
                            fromdesc: str = '听打稿.txt', todesc: str = '校对稿.txt',
                            cleanup: str = 'semantic', use_line_mode: bool = False) -> None:
    """使用 diff-match-patch 生成紧凑高亮的 HTML 差异。

    参数：
      - cleanup: 'semantic' | 'efficiency' | 'none'
      - use_line_mode: True 时先按行压缩再 diff，适合长文本
    """
    if not _DMP_AVAILABLE:
        raise RuntimeError('未安装 diff-match-patch，请先执行: pip install diff-match-patch')

    with open(file1_path, 'r', encoding='utf-8') as f1:
        text1 = f1.read()
    with open(file2_path, 'r', encoding='utf-8') as f2:
        text2 = f2.read()

    dmp = diff_match_patch()
    dmp.Diff_Timeout = 0.0          # 0 表示不超时（或设为 5.0 增大到 5 秒）

    if use_line_mode:
        text1c, text2c, line_array = dmp.diff_linesToChars(text1, text2)
        diffs = dmp.diff_main(text1c, text2c, False)
        dmp.diff_charsToLines(diffs, line_array)
    else:
        diffs = dmp.diff_main(text1, text2, False)

    if cleanup == 'semantic':
        dmp.diff_cleanupSemantic(diffs)
    elif cleanup == 'efficiency':
        dmp.diff_cleanupEfficiency(diffs)
    # else: 不做 cleanup，尽量保留原始差异块

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
    /* diff_prettyHtml 会带内联样式；以下是兜底样式 */
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

    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    print(f"差异报告已生成: {output_path}")


if __name__ == "__main__":
    # CLI: python text_diff.py [dmp] src dst out.html
    args = sys.argv[1:]

    # 默认使用 dmp，且不覆盖现有报告文件，输出为 diff_report_dmp.html
    default_src = r'src/地藏菩萨本愿经讲解2语音识别稿.txt'
    default_dst = r'src/地藏菩萨本愿经讲解2语音识别稿.re.txt'
    default_out = r'src/diff_report_dmp.html'
    clean_up=None

    if not args:
        if _DMP_AVAILABLE:
            generate_html_diff_dmp(default_src, default_dst, default_out,
                                   fromdesc='听打稿.txt', todesc='校对稿.txt',
                                   cleanup=clean_up,
                                     use_line_mode=False,
                                     )
        else:
            print('未检测到 diff-match-patch，请先安装: pip install diff-match-patch')
            sys.exit(1)
    else:
        engine = args[0].lower()
        if engine in ('dmp', 'diff-match-patch'):
            try:
                src = args[1] if len(args) > 1 else default_src
                dst = args[2] if len(args) > 2 else default_dst
                out = args[3] if len(args) > 3 else default_out
                generate_html_diff_dmp(src, dst, out,
                                       fromdesc='听打稿.txt', todesc='校对稿.txt',
                                       cleanup=clean_up, use_line_mode=False)
            except RuntimeError as e:
                print(str(e))
                sys.exit(1)
        else:
            print('参数错误，用法: python text_diff.py [dmp] 源文件 目标文件 输出.html')
            sys.exit(2)
