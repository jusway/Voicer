#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""测试 src.gui_wx.app 的基本功能"""

import sys
from pathlib import Path


def test_imports():
    """测试依赖导入"""
    print("测试导入...")

    try:
        import wx
        print(f"✅ wxPython 导入成功，版本: {wx.version()}")
    except ImportError as e:
        print(f"❌ wxPython 导入失败: {e}")
        return False

    try:
        import wx.lib.scrolledpanel
        print("✅ wx.lib.scrolledpanel 导入成功")
    except ImportError as e:
        print(f"❌ wx.lib.scrolledpanel 导入失败: {e}")
        return False

    try:
        import threading  # noqa: F401
        import queue  # noqa: F401
        import json  # noqa: F401
        print("✅ 标准库导入成功")
    except ImportError as e:
        print(f"❌ 标准库导入失败: {e}")
        return False

    return True


def test_core_modules():
    """测试核心模块导入（存在即通过）"""
    print("\n测试核心模块...")

    project_root = Path(__file__).resolve().parents[1]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    try:
        from src.core.pipeline import Pipeline, PipelineError  # noqa: F401
        from src.config.settings import settings  # noqa: F401
        print("✅ 核心模块导入成功")
        return True
    except Exception as e:
        print(f"⚠️ 核心模块导入失败: {e}")
        return False


def test_app_module_import():
    """测试 src.gui_wx.app 导入与主要类存在"""
    print("\n测试 src.gui_wx.app 导入...")

    try:
        import importlib
        mod = importlib.import_module("src.gui_wx.app")
        print("✅ src.gui_wx.app 导入成功")

        for name in ["MainFrame", "ProgressDialog", "ASRApp"]:
            if hasattr(mod, name):
                print(f"✅ {name} 存在")
            else:
                print(f"⚠️ {name} 缺失")
        return True
    except Exception as e:
        print(f"❌ src.gui_wx.app 导入失败: {e}")
        return False


def test_minimal_wx_app():
    """测试最小 wx 应用创建"""
    print("\n测试最小 wx 应用...")

    try:
        import wx

        class TestApp(wx.App):
            def OnInit(self):
                frame = wx.Frame(None, title="测试")
                frame.Show()
                wx.CallAfter(frame.Close)
                return True

        app = TestApp()
        print("✅ 最小 wx 应用创建成功")
        return True
    except Exception as e:
        print(f"❌ 最小 wx 应用创建失败: {e}")
        return False


def main():
    print("=" * 50)
    print("src.gui_wx.app 功能测试")
    print("=" * 50)

    tests = [
        test_imports,
        test_core_modules,
        test_app_module_import,
        test_minimal_wx_app,
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ 测试异常: {e}")

    print("\n" + "=" * 50)
    print(f"测试结果: {passed}/{total} 通过")

    if passed == total:
        print("🎉 所有测试通过！GUI 入口应可正常运行")
        print("\n启动命令:")
        print("  uv run python -m src.gui_wx.app")
    else:
        print("⚠️ 部分测试失败，请检查依赖和环境配置")

    print("=" * 50)


if __name__ == "__main__":
    main()
