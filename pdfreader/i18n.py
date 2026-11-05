"""Small runtime translation layer for the reader UI.

The application follows the Windows display language: Chinese gets the
Simplified Chinese source strings, everything else gets English.  The
``PDFREADER_LANG`` environment variable can force ``zh`` or ``en`` for
testing and portable use.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import QLibraryInfo, QLocale, QTranslator

_LANGUAGE: str | None = None

_EN: dict[str, str] = {
    # Welcome page
    "轻量 PDF 阅读器 · 选中文字即可复制 · 全文搜索 · 多标签":
        "Lightweight PDF reader · Select text to copy · Full-text search · Tabs",
    "打开 PDF…": "Open PDF…",
    "把 PDF 拖到这里，或按 Ctrl+O 打开":
        "Drop a PDF here, or press Ctrl+O",
    "最近打开": "Recent files",
    "清空": "Clear",
    "配置文件：{path}（程序不写注册表）":
        "Settings file: {path} (the app writes nothing to the registry)",
    "还没有最近打开的文件": "No recent files yet",
    # Actions and menus
    "打开…": "Open…",
    "打印…": "Print…",
    "退出": "Quit",
    "复制": "Copy",
    "全选": "Select All",
    "复制本页文字": "Copy Page Text",
    "复制全文": "Copy All Text",
    "清除选择": "Clear Selection",
    "查找…": "Find…",
    "导航栏": "Navigation bar",
    "放大": "Zoom In",
    "缩小": "Zoom Out",
    "适应宽度": "Fit Width",
    "适应页面": "Fit Page",
    "实际大小": "Actual Size",
    "深色模式": "Dark Mode",
    "反色页面（夜间阅读）": "Invert Pages (Night Reading)",
    "全屏": "Full Screen",
    "快捷键": "Keyboard Shortcuts",
    "关于 pdfreader": "About pdfreader",
    "文件(&F)": "&File",
    "编辑(&E)": "&Edit",
    "视图(&V)": "&View",
    "帮助(&H)": "&Help",
    "主工具栏": "Main toolbar",
    # Toolbar and status bar
    "上一页（PageUp）": "Previous page (PageUp)",
    "下一页（PageDown）": "Next page (PageDown)",
    "输入页码后回车": "Enter a page number and press Enter",
    "缩小（Ctrl+-）": "Zoom out (Ctrl+-)",
    "缩放": "Zoom",
    "放大（Ctrl++）": "Zoom in (Ctrl++)",
    "在文档中搜索…": "Search in document…",
    "上一个结果（Shift+Enter）": "Previous result (Shift+Enter)",
    "下一个结果（Enter）": "Next result (Enter)",
    "就绪": "Ready",
    # Recent files
    "（没有最近文件）": "(No recent files)",
    "清空列表": "Clear list",
    # Opening files
    "打开 PDF": "Open PDF",
    "PDF 文件 (*.pdf);;所有文件 (*.*)": "PDF files (*.pdf);;All files (*.*)",
    "没有打开任何 PDF": "No PDF is open",
    "文件无法打开": "The file could not be opened",
    "打不开": "Cannot open",
    "文件不存在：\n{path}": "File does not exist:\n{path}",
    "需要密码": "Password required",
    "这个 PDF 已加密，请输入密码（{attempt}/3）：\n{name}":
        "This PDF is encrypted. Enter the password ({attempt}/3):\n{name}",
    "打开失败": "Could not open",
    "密码错误或已取消。": "The password is incorrect, or the operation was cancelled.",
    # Status messages and counters
    "已打开 {name} · {pages} 页 · {size}": "Opened {name} · {pages} pages · {size}",
    "{name} · {pages} 页 · {size}": "{name} · {pages} pages · {size}",
    "第 {page} / {total} 页": "Page {page} / {total}",
    "缩放 {percent}%": "Zoom {percent}%",
    "已选 {chars} 字": "{chars} characters selected",
    "打印任务已发送": "Print job sent",
    "搜索中…": "Searching…",
    "无结果": "No results",
    # Shortcuts dialog
    "Ctrl+O    打开 PDF\n"
    "Ctrl+P    打印\n"
    "Ctrl+F    查找（Esc 退出查找）\n"
    "Ctrl+C    复制选中文字\n"
    "Ctrl+A    全选\n"
    "Ctrl+0    适应宽度\n"
    "Ctrl+1    实际大小（100%）\n"
    "Ctrl+2    适应页面\n"
    "Ctrl++/-  放大 / 缩小\n"
    "Ctrl+滚轮 缩放\n"
    "F4        显示 / 隐藏导航栏\n"
    "F11       全屏\n"
    "PageUp/Down、空格  翻页 / 滚动\n"
    "Esc       清除选择":
        "Ctrl+O    Open PDF\n"
        "Ctrl+P    Print\n"
        "Ctrl+F    Find (Esc to exit search)\n"
        "Ctrl+C    Copy selected text\n"
        "Ctrl+A    Select all\n"
        "Ctrl+0    Fit width\n"
        "Ctrl+1    Actual size (100%)\n"
        "Ctrl+2    Fit page\n"
        "Ctrl++/-  Zoom in / out\n"
        "Ctrl+wheel  Zoom\n"
        "F4        Show / hide navigation bar\n"
        "F11       Full screen\n"
        "PageUp/Down, Space  Page / scroll\n"
        "Esc       Clear selection",
    # About dialog
    "轻量 PDF 阅读器：连续滚动、选中文字复制、全文搜索、目录与缩略图、"
    "多标签、深色模式、打印。<br><br>":
        "Lightweight PDF reader with continuous scrolling, text selection and "
        "copying, full-text search, outline and thumbnails, tabs, dark mode, "
        "and printing.<br><br>",
    "程序位置：{path}<br><br>": "Program location: {path}<br><br>",
    "图标与界面为原创设计，不使用 Adobe 商标。":
        "The icon and interface are original designs and do not use Adobe trademarks.",
    # Command line
    "轻量 PDF 阅读器：选中文字复制、搜索、目录、多标签。":
        "Lightweight PDF reader with text selection and copying, search, outline, and tabs.",
    "要打开的 PDF 文件": "PDF files to open",
    "运行内置自检": "Run the built-in self-test",
    "允许启动多个独立窗口": "Allow multiple independent windows",
    # Document errors
    "无法打开 PDF：{error}": "Cannot open PDF: {error}",
    "这个文件不是 PDF。": "This file is not a PDF.",
    "未命名": "Untitled",
    # Printing
    "打印 PDF": "Print PDF",
    "打印失败": "Print failed",
    "无法初始化打印机。": "Cannot initialize the printer.",
    "打印过程中出错：{error}": "An error occurred while printing: {error}",
    # Sidebar
    "目录": "Outline",
    "缩略图": "Thumbnails",
    "此 PDF 没有目录": "This PDF has no outline",
    # View and context menu
    "无法渲染此页": "Cannot render this page",
    "复制文字": "Copy Text",
    "这个 PDF 没有可选择的文字（可能是扫描件）":
        "This PDF has no selectable text (it may be a scanned document).",
    "此页没有可选择的文字（可能是扫描件）":
        "This page has no selectable text (it may be scanned).",
    "没有选中文字（扫描件需要 OCR，当前版本不支持）":
        "No text is selected. Scanned documents require OCR, which this version does not support.",
    "已复制 {count} 个字符": "Copied {count} characters",
    "此页没有可复制的文字（可能是扫描件）":
        "This page has no copyable text (it may be scanned).",
    "已复制第 {page} 页文字（{count} 个字符）":
        "Copied text from page {page} ({count} characters)",
    "这个 PDF 没有可复制的文字（可能是扫描件）":
        "This PDF has no copyable text (it may be scanned).",
    "已复制全文（{count} 个字符）": "Copied all text ({count} characters)",
    "没有搜索结果": "No search results",
    "已打开链接：{uri}": "Opened link: {uri}",
    # Crash dialog
    "pdfreader 启动失败。": "pdfreader failed to start.",
    "\n\n详细信息已写入：\n": "\n\nDetails were written to:\n",
}


def language_from_tags(tags: list[str] | tuple[str, ...]) -> str:
    """Return the UI language for a list of Windows UI locale tags."""

    for tag in tags:
        base = tag.replace("_", "-").split("-", 1)[0].lower()
        if base in ("c", "posix"):
            continue
        return "zh" if base == "zh" else "en"
    return ""


def _detect_language() -> str:
    override = os.environ.get("PDFREADER_LANG", "").strip().lower()
    if override.startswith("zh"):
        return "zh"
    if override.startswith("en"):
        return "en"

    locale = QLocale.system()
    detected = language_from_tags(list(locale.uiLanguages()))
    if detected:
        return detected
    return "zh" if locale.language() == QLocale.Language.Chinese else "en"


def current_language() -> str:
    global _LANGUAGE
    if _LANGUAGE is None:
        _LANGUAGE = _detect_language()
    return _LANGUAGE


def set_language(code: str | None) -> None:
    """Force a language for tests; pass ``None`` to detect again."""

    global _LANGUAGE
    if code is None:
        _LANGUAGE = None
    elif code.lower().startswith("zh"):
        _LANGUAGE = "zh"
    else:
        _LANGUAGE = "en"


def tr(text: str) -> str:
    if current_language() == "zh":
        return text
    return _EN.get(text, text)


def install_qt_translator(app) -> QTranslator | None:
    """Load Qt's Chinese strings for standard buttons and dialogs."""

    if current_language() != "zh":
        return None
    translator = QTranslator(app)
    candidates: list[Path] = []
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        candidates.append(Path(bundle) / "translations")
    candidates.append(Path(__file__).resolve().parent.parent / "translations")
    candidates.append(Path(QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)))
    for folder in candidates:
        if translator.load("qtbase_zh_CN", str(folder)):
            app.installTranslator(translator)
            return translator
    return None
