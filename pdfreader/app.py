"""Main window, welcome page and application entry point."""

from __future__ import annotations

import argparse
import getpass
import json
import os
import subprocess
import sys
from typing import Optional

from PySide6.QtCore import QByteArray, QSettings, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QAction,
    QDesktopServices,
    QFont,
    QIcon,
    QKeySequence,
)
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QStatusBar,
    QTabWidget,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from . import __version__
from .assoc import (
    AssocError,
    app_executable,
    default_apps_hint,
    register,
    registration_status,
    resource_path,
    unregister,
)
from .document import PasswordRequired, PdfDocument, PdfError
from .i18n import install_qt_translator, tr
from .printing import print_document
from .sidebar import PdfSidebar
from .theme import palette, stylesheet
from .view import PdfView

APP_NAME = "pdfreader"
ORG_NAME = "pdfreader"
SETTINGS_RECENT = "recent/files"
MAX_RECENT = 15
SINGLE_INSTANCE_KEY = f"pdfreader-{getpass.getuser() or 'user'}"


# --------------------------------------------------------------------------- helpers
def _settings_bool(settings: QSettings, key: str, default: bool = False) -> bool:
    value = settings.value(key, default)
    if isinstance(value, bool):
        return value
    return str(value).lower() in ("1", "true", "yes", "on")


def _settings_int(
    settings: QSettings,
    key: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(settings.value(key, default))
    except (TypeError, ValueError):
        value = default
    return max(minimum, min(maximum, value))


def _natural_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024.0
    return f"{size} B"


class SearchEdit(QLineEdit):
    escape_pressed = Signal()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.escape_pressed.emit()
            event.accept()
            return
        super().keyPressEvent(event)


# --------------------------------------------------------------------------- welcome
class WelcomePage(QWidget):
    open_requested = Signal()
    register_requested = Signal()
    open_path_requested = Signal(str)
    clear_recent_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("WelcomePage")

        card = QFrame(self)
        card.setObjectName("WelcomeCard")
        card.setMaximumWidth(780)
        card.setMinimumWidth(460)

        title = QLabel("pdfreader")
        title.setObjectName("Title")
        subtitle = QLabel(tr("轻量 PDF 阅读器 · 选中文字即可复制 · 全文搜索 · 多标签"))
        subtitle.setObjectName("Subtitle")
        subtitle.setWordWrap(True)

        open_button = QPushButton(tr("打开 PDF…"))
        open_button.setObjectName("primary")
        open_button.setMinimumWidth(150)
        open_button.clicked.connect(self.open_requested)

        assoc_button = QPushButton(tr("注册文件关联…"))
        assoc_button.clicked.connect(self.register_requested)

        drop_hint = QLabel(
            tr("把 PDF 拖到这里，或从资源管理器右键 → 打开方式 → pdfreader")
        )
        drop_hint.setObjectName("DropHint")
        drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        drop_hint.setWordWrap(True)

        recent_header = QHBoxLayout()
        recent_title = QLabel(tr("最近打开"))
        recent_title.setObjectName("SectionTitle")
        clear_button = QPushButton(tr("清空"))
        clear_button.setFlat(True)
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.clicked.connect(self.clear_recent_requested)
        recent_header.addWidget(recent_title)
        recent_header.addStretch(1)
        recent_header.addWidget(clear_button)

        self.recent_list = QListWidget()
        self.recent_list.setObjectName("RecentList")
        self.recent_list.setMaximumHeight(230)
        self.recent_list.setMinimumHeight(110)
        self.recent_list.itemClicked.connect(self._recent_activated)

        hint = QLabel(
            tr(
                "提示：注册后首次使用，请在 Windows 11 的“设置 → 应用 → 默认应用”中"
                "把 .pdf 交给 pdfreader；系统不允许程序静默抢走默认应用。"
            )
        )
        hint.setObjectName("Hint")
        hint.setWordWrap(True)

        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(34, 30, 34, 28)
        card_layout.setSpacing(14)
        card_layout.addWidget(title)
        card_layout.addWidget(subtitle)
        buttons = QHBoxLayout()
        buttons.setSpacing(10)
        buttons.addWidget(open_button)
        buttons.addWidget(assoc_button)
        buttons.addStretch(1)
        card_layout.addLayout(buttons)
        card_layout.addSpacing(6)
        card_layout.addWidget(drop_hint)
        card_layout.addSpacing(6)
        card_layout.addLayout(recent_header)
        card_layout.addWidget(self.recent_list)
        card_layout.addWidget(hint)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(40, 34, 40, 34)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        row.addWidget(card)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def set_recent(self, paths: list[str]) -> None:
        self.recent_list.clear()
        if not paths:
            item = QListWidgetItem(tr("还没有最近打开的文件"))
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self.recent_list.addItem(item)
            return
        for path in paths:
            name = os.path.basename(path)
            folder = os.path.dirname(path)
            item = QListWidgetItem(f"{name}    {folder}")
            item.setData(Qt.ItemDataRole.UserRole, path)
            item.setToolTip(path)
            self.recent_list.addItem(item)

    def _recent_activated(self, item: QListWidgetItem) -> None:
        path = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(path, str) and path:
            self.open_path_requested.emit(path)


# --------------------------------------------------------------------------- tab
class PdfTab(QWidget):
    sidebar_width_changed = Signal(int)

    def __init__(
        self,
        document: PdfDocument,
        sidebar_width: int = 280,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.document = document
        self.view = PdfView(document, self)
        self.sidebar = PdfSidebar(document, self)
        self.sidebar.setObjectName("SidebarTabs")
        self.sidebar_width = max(
            self.sidebar.minimumWidth(),
            min(self.sidebar.maximumWidth(), int(sidebar_width)),
        )

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self.sidebar)
        self.splitter.addWidget(self.view)
        self.splitter.setStretchFactor(0, 0)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([self.sidebar_width, 980])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.splitter)

        self.sidebar.page_requested.connect(self.view.goto_page)
        self.view.page_changed.connect(self.sidebar.set_current_page)

    @property
    def path(self) -> str:
        return self.document.path

    @property
    def name(self) -> str:
        return os.path.basename(self.document.path)

    def _on_splitter_moved(self, _pos: int, _index: int) -> None:
        width = self.splitter.sizes()[0]
        if width <= 0:
            return
        self.sidebar_width = width
        self.sidebar_width_changed.emit(width)

    def set_sidebar_width(self, width: int) -> None:
        width = max(
            self.sidebar.minimumWidth(),
            min(self.sidebar.maximumWidth(), int(width)),
        )
        self.sidebar_width = width
        total = sum(self.splitter.sizes())
        if total <= 0:
            total = self.splitter.width()
        if total <= 0:
            return
        self.splitter.setSizes([width, max(1, total - width)])

    def set_sidebar_visible(self, visible: bool) -> None:
        self.sidebar.setVisible(visible)
        if visible:
            self.set_sidebar_width(self.sidebar_width)

    def shutdown(self) -> None:
        self.sidebar.shutdown()
        self.view.shutdown()
        self.document.close()


# --------------------------------------------------------------------------- dialogs
class AssociationDialog(QDialog):
    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(tr("文件关联"))
        self.setMinimumWidth(560)

        title = QLabel(tr("让 pdfreader 出现在“打开方式”里"))
        title.setObjectName("SectionTitle")
        body = QLabel(
            tr(
                "注册信息只写入当前用户（HKCU），不需要管理员权限。"
                "注册后，右键任意 PDF →「打开方式」就能看到 pdfreader。\n\n"
            )
            + default_apps_hint()
        )
        body.setWordWrap(True)

        self.status_label = QLabel("")
        self.status_label.setObjectName("StatusStrong")
        self.status_label.setWordWrap(True)

        self.path_label = QLabel(app_executable())
        self.path_label.setObjectName("Hint")
        self.path_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.path_label.setWordWrap(True)

        self.register_button = QPushButton(tr("注册 / 更新关联"))
        self.register_button.setObjectName("primary")
        self.remove_button = QPushButton(tr("移除关联"))
        settings_button = QPushButton(tr("打开默认应用设置"))
        close_button = QPushButton(tr("关闭"))

        self.register_button.clicked.connect(self._register)
        self.remove_button.clicked.connect(self._remove)
        settings_button.clicked.connect(self._open_default_settings)
        close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.register_button)
        buttons.addWidget(self.remove_button)
        buttons.addWidget(settings_button)
        buttons.addStretch(1)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 22, 24, 20)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(body)
        layout.addWidget(self.status_label)
        layout.addWidget(self.path_label)
        layout.addSpacing(6)
        layout.addLayout(buttons)

        self._refresh()

    def _refresh(self) -> None:
        registered, detail = registration_status()
        self.status_label.setText(("● " if registered else "○ ") + detail)
        self.remove_button.setEnabled(True)

    def _register(self) -> None:
        try:
            register()
        except AssocError as exc:
            QMessageBox.critical(self, tr("注册失败"), str(exc))
            return
        self._refresh()
        QMessageBox.information(
            self,
            tr("已注册"),
            tr("完成。现在右键 PDF →「打开方式」里会出现 pdfreader。\n\n")
            + default_apps_hint(),
        )

    def _remove(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("移除文件关联"),
            tr(
                "移除 pdfreader 写入注册表的所有内容？\n\n"
                "这不会删除 pdfreader.exe 本身。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            unregister()
        except AssocError as exc:
            QMessageBox.critical(self, tr("移除失败"), str(exc))
            return
        self._refresh()
        QMessageBox.information(self, tr("已移除"), tr("注册表关联已删除。"))

    def _open_default_settings(self) -> None:
        if not QDesktopServices.openUrl(QUrl("ms-settings:defaultapps")):
            subprocess.Popen(
                ["control", "/name", "Microsoft.DefaultPrograms"],
                shell=False,
            )


# --------------------------------------------------------------------------- main window
class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon(str(resource_path("assets/pdfreader.ico"))))
        self.resize(1260, 840)
        self.setMinimumSize(760, 520)
        self.setAcceptDrops(True)

        self.settings = QSettings(ORG_NAME, APP_NAME)
        self.dark_mode = _settings_bool(self.settings, "ui/dark", False)
        self.invert_pages = _settings_bool(self.settings, "ui/invert", False)
        self.sidebar_visible = _settings_bool(self.settings, "ui/sidebar", True)
        self.sidebar_width = _settings_int(
            self.settings, "ui/sidebar_width", 280, 220, 560
        )
        self._syncing_sidebar_width = False
        self._updating_ui = False
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(True)
        self._search_timer.setInterval(420)
        self._search_timer.timeout.connect(lambda: self._start_search())

        self._build_ui()
        self._build_actions()
        self._build_menus()
        self._build_toolbar()
        self._build_statusbar()
        self._restore_settings()

        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._show_welcome()

    # ------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        self.stack = QStackedWidget(self)
        self.welcome = WelcomePage(self)
        self.welcome.open_requested.connect(self.choose_files)
        self.welcome.register_requested.connect(self.show_association_dialog)
        self.welcome.open_path_requested.connect(self.open_path)
        self.welcome.clear_recent_requested.connect(self._clear_recent)
        self.stack.addWidget(self.welcome)

        self.tabs = QTabWidget(self)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setDocumentMode(True)
        self.tabs.setElideMode(Qt.TextElideMode.ElideMiddle)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        self.stack.addWidget(self.tabs)

        self.setCentralWidget(self.stack)

    def _build_actions(self) -> None:
        self.action_open = QAction(tr("打开…"), self)
        self.action_open.setShortcut(QKeySequence.StandardKey.Open)
        self.action_open.triggered.connect(self.choose_files)

        self.action_print = QAction(tr("打印…"), self)
        self.action_print.setShortcut(QKeySequence.StandardKey.Print)
        self.action_print.triggered.connect(self.print_current)

        self.action_assoc = QAction(tr("文件关联…"), self)
        self.action_assoc.triggered.connect(self.show_association_dialog)

        self.action_uninstall = QAction(tr("移除文件关联…"), self)
        self.action_uninstall.triggered.connect(self.remove_association)

        self.action_quit = QAction(tr("退出"), self)
        self.action_quit.setShortcut(QKeySequence.StandardKey.Quit)
        self.action_quit.triggered.connect(self.close)

        self.action_copy = QAction(tr("复制"), self)
        self.action_copy.setShortcut(QKeySequence.StandardKey.Copy)
        self.action_copy.triggered.connect(self.copy)

        self.action_select_all = QAction(tr("全选"), self)
        self.action_select_all.setShortcut(QKeySequence.StandardKey.SelectAll)
        self.action_select_all.triggered.connect(self.select_all)

        self.action_copy_page = QAction(tr("复制本页文字"), self)
        self.action_copy_page.triggered.connect(self.copy_page_text)

        self.action_copy_all = QAction(tr("复制全文"), self)
        self.action_copy_all.triggered.connect(self.copy_all_text)

        self.action_clear_selection = QAction(tr("清除选择"), self)
        self.action_clear_selection.triggered.connect(self.clear_selection)

        self.action_find = QAction(tr("查找…"), self)
        self.action_find.setShortcut(QKeySequence.StandardKey.Find)
        self.action_find.triggered.connect(self.focus_search)

        self.action_sidebar = QAction(tr("目录侧栏"), self)
        self.action_sidebar.setCheckable(True)
        self.action_sidebar.setChecked(self.sidebar_visible)
        self.action_sidebar.setShortcut(QKeySequence(Qt.Key.Key_F4))
        self.action_sidebar.toggled.connect(self.set_sidebar_visible)

        self.action_zoom_in = QAction(tr("放大"), self)
        self.action_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.action_zoom_in.triggered.connect(lambda: self._call_view("zoom_in"))

        self.action_zoom_out = QAction(tr("缩小"), self)
        self.action_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.action_zoom_out.triggered.connect(lambda: self._call_view("zoom_out"))

        self.action_fit_width = QAction(tr("适应宽度"), self)
        self.action_fit_width.setShortcut(QKeySequence("Ctrl+0"))
        self.action_fit_width.triggered.connect(lambda: self._call_view("fit_width"))

        self.action_fit_page = QAction(tr("适应页面"), self)
        self.action_fit_page.setShortcut(QKeySequence("Ctrl+2"))
        self.action_fit_page.triggered.connect(lambda: self._call_view("fit_page"))

        self.action_actual_size = QAction(tr("实际大小"), self)
        self.action_actual_size.setShortcut(QKeySequence("Ctrl+1"))
        self.action_actual_size.triggered.connect(self._actual_size)

        self.action_dark = QAction(tr("深色模式"), self)
        self.action_dark.setCheckable(True)
        self.action_dark.setChecked(self.dark_mode)
        self.action_dark.toggled.connect(self.set_dark_mode)

        self.action_invert = QAction(tr("反色页面（夜间阅读）"), self)
        self.action_invert.setCheckable(True)
        self.action_invert.setChecked(self.invert_pages)
        self.action_invert.toggled.connect(self.set_invert_pages)

        self.action_fullscreen = QAction(tr("全屏"), self)
        self.action_fullscreen.setCheckable(True)
        self.action_fullscreen.setShortcut(QKeySequence(Qt.Key.Key_F11))
        self.action_fullscreen.toggled.connect(self._toggle_fullscreen)

        self.action_shortcuts = QAction(tr("快捷键"), self)
        self.action_shortcuts.triggered.connect(self.show_shortcuts)

        self.action_about = QAction(tr("关于 pdfreader"), self)
        self.action_about.triggered.connect(self.show_about)

    def _build_menus(self) -> None:
        menubar = self.menuBar()

        file_menu = menubar.addMenu(tr("文件(&F)"))
        file_menu.addAction(self.action_open)
        file_menu.addAction(self.action_print)
        file_menu.addSeparator()
        self.recent_menu = file_menu.addMenu(tr("最近打开"))
        file_menu.addSeparator()
        file_menu.addAction(self.action_assoc)
        file_menu.addAction(self.action_uninstall)
        file_menu.addSeparator()
        file_menu.addAction(self.action_quit)

        edit_menu = menubar.addMenu(tr("编辑(&E)"))
        edit_menu.addAction(self.action_copy)
        edit_menu.addAction(self.action_copy_page)
        edit_menu.addAction(self.action_copy_all)
        edit_menu.addAction(self.action_select_all)
        edit_menu.addSeparator()
        edit_menu.addAction(self.action_find)
        edit_menu.addAction(self.action_clear_selection)

        view_menu = menubar.addMenu(tr("视图(&V)"))
        view_menu.addAction(self.action_sidebar)
        view_menu.addSeparator()
        view_menu.addAction(self.action_zoom_in)
        view_menu.addAction(self.action_zoom_out)
        view_menu.addAction(self.action_fit_width)
        view_menu.addAction(self.action_fit_page)
        view_menu.addAction(self.action_actual_size)
        view_menu.addSeparator()
        view_menu.addAction(self.action_dark)
        view_menu.addAction(self.action_invert)
        view_menu.addAction(self.action_fullscreen)

        help_menu = menubar.addMenu(tr("帮助(&H)"))
        help_menu.addAction(self.action_shortcuts)
        help_menu.addAction(self.action_about)

        for menu in (file_menu, edit_menu, view_menu, help_menu):
            menu.setToolTipsVisible(True)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar(tr("主工具栏"), self)
        toolbar.setMovable(False)
        toolbar.setFloatable(False)
        toolbar.setIconSize(QSize(18, 18))
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(toolbar)
        self.toolbar = toolbar

        toolbar.addAction(self.action_open)
        toolbar.addAction(self.action_print)
        toolbar.addSeparator()
        toolbar.addAction(self.action_sidebar)
        toolbar.addSeparator()

        prev_button = QToolButton()
        prev_button.setText("◀")
        prev_button.setToolTip(tr("上一页（PageUp）"))
        prev_button.clicked.connect(self.previous_page)
        next_button = QToolButton()
        next_button.setText("▶")
        next_button.setToolTip(tr("下一页（PageDown）"))
        next_button.clicked.connect(self.next_page)
        self.page_edit = QLineEdit()
        self.page_edit.setFixedWidth(46)
        self.page_edit.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.page_edit.setToolTip(tr("输入页码后回车"))
        self.page_edit.returnPressed.connect(self._page_edit_entered)
        self.page_total = QLabel("/ 0")
        self.page_total.setObjectName("Hint")
        toolbar.addWidget(prev_button)
        toolbar.addWidget(self.page_edit)
        toolbar.addWidget(self.page_total)
        toolbar.addWidget(next_button)
        toolbar.addSeparator()

        zoom_out = QToolButton()
        zoom_out.setText("−")
        zoom_out.setToolTip(tr("缩小（Ctrl+-）"))
        zoom_out.clicked.connect(lambda: self._call_view("zoom_out"))
        self.zoom_button = QToolButton()
        self.zoom_button.setText(tr("适应宽度"))
        self.zoom_button.setToolTip(tr("缩放"))
        self.zoom_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        zoom_menu = QMenu(self.zoom_button)
        for label, handler in (
            (tr("适应宽度"), lambda: self._call_view("fit_width")),
            (tr("适应页面"), lambda: self._call_view("fit_page")),
            ("50%", lambda: self._set_zoom(0.5)),
            ("75%", lambda: self._set_zoom(0.75)),
            ("100%", lambda: self._set_zoom(1.0)),
            ("125%", lambda: self._set_zoom(1.25)),
            ("150%", lambda: self._set_zoom(1.5)),
            ("200%", lambda: self._set_zoom(2.0)),
            ("300%", lambda: self._set_zoom(3.0)),
            ("400%", lambda: self._set_zoom(4.0)),
        ):
            action = zoom_menu.addAction(label)
            action.triggered.connect(handler)
        self.zoom_button.setMenu(zoom_menu)
        zoom_in = QToolButton()
        zoom_in.setText("+")
        zoom_in.setToolTip(tr("放大（Ctrl++）"))
        zoom_in.clicked.connect(lambda: self._call_view("zoom_in"))
        toolbar.addWidget(zoom_out)
        toolbar.addWidget(self.zoom_button)
        toolbar.addWidget(zoom_in)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        toolbar.addWidget(spacer)

        self.search_edit = SearchEdit()
        self.search_edit.setPlaceholderText(tr("在文档中搜索…"))
        self.search_edit.setClearButtonEnabled(True)
        self.search_edit.setFixedWidth(230)
        self.search_edit.textChanged.connect(self._search_text_changed)
        self.search_edit.returnPressed.connect(self._search_next)
        self.search_edit.escape_pressed.connect(self._search_escape)
        search_prev = QToolButton()
        search_prev.setText("↑")
        search_prev.setToolTip(tr("上一个结果（Shift+Enter）"))
        search_prev.clicked.connect(self.search_previous)
        search_next = QToolButton()
        search_next.setText("↓")
        search_next.setToolTip(tr("下一个结果（Enter）"))
        search_next.clicked.connect(self.search_next)
        self.search_count = QLabel("")
        self.search_count.setObjectName("Hint")
        self.search_count.setMinimumWidth(52)
        self.search_count.setAlignment(Qt.AlignmentFlag.AlignCenter)
        toolbar.addWidget(self.search_edit)
        toolbar.addWidget(search_prev)
        toolbar.addWidget(search_next)
        toolbar.addWidget(self.search_count)
        toolbar.addSeparator()
        toolbar.addAction(self.action_dark)

    def _build_statusbar(self) -> None:
        bar = QStatusBar(self)
        self.setStatusBar(bar)
        self.label_file = QLabel("")
        self.label_file.setObjectName("StatusStrong")
        self.label_page = QLabel("")
        self.label_zoom = QLabel("")
        self.label_selection = QLabel("")
        bar.addPermanentWidget(self.label_selection)
        bar.addPermanentWidget(self.label_zoom)
        bar.addPermanentWidget(self.label_page)
        bar.addPermanentWidget(self.label_file)
        self.show_status(tr("就绪"))

    def _restore_settings(self) -> None:
        geometry = self.settings.value("window/geometry")
        if isinstance(geometry, QByteArray) and not geometry.isEmpty():
            self.restoreGeometry(geometry)
        self.apply_theme()
        self._rebuild_recent_menu()
        self.welcome.set_recent(self._recent_paths())

    # ------------------------------------------------------------------ theme
    def apply_theme(self) -> None:
        app = QApplication.instance()
        if app is not None:
            app.setPalette(palette(self.dark_mode))
            app.setStyleSheet(stylesheet(self.dark_mode))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PdfTab):
                tab.view.set_dark_background(self.dark_mode)

    def set_dark_mode(self, enabled: bool) -> None:
        if enabled == self.dark_mode:
            return
        self.dark_mode = enabled
        self.settings.setValue("ui/dark", enabled)
        self.apply_theme()
        self.action_dark.setChecked(enabled)

    def set_invert_pages(self, enabled: bool) -> None:
        self.invert_pages = enabled
        self.settings.setValue("ui/invert", enabled)
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PdfTab):
                tab.view.set_invert_pages(enabled)

    def set_sidebar_visible(self, visible: bool) -> None:
        self.sidebar_visible = visible
        self.settings.setValue("ui/sidebar", visible)
        self.action_sidebar.setChecked(visible)
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PdfTab):
                tab.set_sidebar_visible(visible)

    def _on_sidebar_width_changed(self, width: int) -> None:
        self.sidebar_width = max(220, min(560, int(width)))
        if self._syncing_sidebar_width:
            return
        self._syncing_sidebar_width = True
        try:
            for index in range(self.tabs.count()):
                tab = self.tabs.widget(index)
                if isinstance(tab, PdfTab) and tab.sidebar_width != self.sidebar_width:
                    tab.set_sidebar_width(self.sidebar_width)
        finally:
            self._syncing_sidebar_width = False

    # --------------------------------------------------------------- recent
    def _recent_paths(self) -> list[str]:
        value = self.settings.value(SETTINGS_RECENT, [])
        if isinstance(value, str):
            paths = [value]
        elif isinstance(value, (list, tuple)):
            paths = [str(p) for p in value]
        else:
            paths = []
        return [p for p in paths if p]

    def _save_recent(self, paths: list[str]) -> None:
        self.settings.setValue(SETTINGS_RECENT, paths)
        self.welcome.set_recent(paths)
        self._rebuild_recent_menu()

    def _add_recent(self, path: str) -> None:
        path = os.path.abspath(path)
        paths = [p for p in self._recent_paths() if os.path.normcase(p) != os.path.normcase(path)]
        paths.insert(0, path)
        self._save_recent(paths[:MAX_RECENT])

    def _remove_recent(self, path: str) -> None:
        paths = [p for p in self._recent_paths() if os.path.normcase(p) != os.path.normcase(path)]
        self._save_recent(paths)

    def _clear_recent(self) -> None:
        self._save_recent([])

    def _rebuild_recent_menu(self) -> None:
        if not hasattr(self, "recent_menu"):
            return
        self.recent_menu.clear()
        paths = self._recent_paths()
        if not paths:
            empty = self.recent_menu.addAction(tr("（没有最近文件）"))
            empty.setEnabled(False)
            return
        for path in paths:
            label = os.path.basename(path)
            action = self.recent_menu.addAction(label)
            action.setToolTip(path)
            action.triggered.connect(lambda _checked=False, p=path: self.open_path(p))
        self.recent_menu.addSeparator()
        clear = self.recent_menu.addAction(tr("清空列表"))
        clear.triggered.connect(self._clear_recent)

    # ---------------------------------------------------------------- opening
    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            tr("打开 PDF"),
            "",
            tr("PDF 文件 (*.pdf);;所有文件 (*.*)"),
        )
        if paths:
            self.open_paths(paths)

    def open_paths(self, paths: list[str], quiet: bool = False) -> int:
        opened = 0
        last_error = False
        for path in paths:
            if self.open_path(path, quiet=True):
                opened += 1
            else:
                last_error = True
        if opened:
            self._show_tabs()
            self.raise_()
            self.activateWindow()
        elif not quiet:
            self.show_status(
                tr("没有打开任何 PDF") if not last_error else tr("文件无法打开")
            )
        return opened

    def open_path(self, path: str, quiet: bool = False) -> bool:
        if not path:
            return False
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(path):
            if not quiet:
                QMessageBox.warning(
                    self,
                    tr("打不开"),
                    tr("文件不存在：\n{path}").format(path=path),
                )
            return False

        # Focus an existing tab instead of opening the same file twice.
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PdfTab) and os.path.normcase(tab.path) == os.path.normcase(path):
                self.tabs.setCurrentIndex(index)
                self._show_tabs()
                return True

        password: Optional[str] = None
        document: Optional[PdfDocument] = None
        for attempt in range(3):
            try:
                document = PdfDocument(path, password)
                break
            except PasswordRequired:
                password, ok = QInputDialog.getText(
                    self,
                    tr("需要密码"),
                    tr("这个 PDF 已加密，请输入密码（{attempt}/3）：\n{name}").format(
                        attempt=attempt + 1,
                        name=os.path.basename(path),
                    ),
                    QLineEdit.EchoMode.Password,
                )
                if not ok:
                    return False
                continue
            except PdfError as exc:
                if not quiet:
                    QMessageBox.critical(self, tr("打开失败"), str(exc))
                return False
        if document is None:
            QMessageBox.critical(self, tr("打开失败"), tr("密码错误或已取消。"))
            return False

        tab = PdfTab(document, self.sidebar_width, self)
        tab.sidebar_width_changed.connect(self._on_sidebar_width_changed)
        tab.view.set_dark_background(self.dark_mode)
        tab.view.invert_pages = self.invert_pages
        tab.set_sidebar_visible(self.sidebar_visible)
        tab.view.status_message.connect(self.show_status)
        tab.view.selection_changed.connect(self._on_selection_changed)
        tab.view.zoom_changed.connect(lambda z, t=tab: self._on_zoom_changed(t, z))
        tab.view.page_changed.connect(self._on_page_changed)
        tab.view.search_progress.connect(self._on_search_progress)
        tab.view.search_finished.connect(self._on_search_finished)
        tab.view.search_position.connect(self._on_search_position)

        index = self.tabs.addTab(tab, tab.name)
        self.tabs.setTabToolTip(index, tab.path)
        self.tabs.setCurrentIndex(index)
        self._add_recent(path)
        self._show_tabs()
        QTimer.singleShot(0, tab.view.fit_width)
        self.show_status(
            tr("已打开 {name} · {pages} 页 · {size}").format(
                name=tab.name,
                pages=document.page_count,
                size=_natural_size(document.file_size),
            )
        )
        return True

    def _show_tabs(self) -> None:
        if self.tabs.count():
            self.stack.setCurrentWidget(self.tabs)
        else:
            self.stack.setCurrentWidget(self.welcome)
            self.welcome.set_recent(self._recent_paths())
        self._update_window_title()
        self._update_ui_for_current()

    def _show_welcome(self) -> None:
        if self.tabs.count() == 0:
            self.stack.setCurrentWidget(self.welcome)
            self.welcome.set_recent(self._recent_paths())
        else:
            self.stack.setCurrentWidget(self.tabs)
        self._update_window_title()
        self._update_ui_for_current()

    def close_tab(self, index: int) -> None:
        tab = self.tabs.widget(index)
        if not isinstance(tab, PdfTab):
            return
        self.tabs.removeTab(index)
        tab.shutdown()
        tab.deleteLater()
        self._show_tabs()

    def closeEvent(self, event) -> None:  # noqa: N802
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            if isinstance(tab, PdfTab):
                tab.shutdown()
        self.tabs.clear()
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("ui/sidebar", self.sidebar_visible)
        self.settings.setValue("ui/sidebar_width", self.sidebar_width)
        self.settings.setValue("ui/dark", self.dark_mode)
        self.settings.setValue("ui/invert", self.invert_pages)
        self.settings.sync()
        if getattr(self, "_server", None) is not None:
            self._server.close()
            QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        super().closeEvent(event)

    # --------------------------------------------------------------- current
    def current_tab(self) -> Optional[PdfTab]:
        widget = self.tabs.currentWidget()
        return widget if isinstance(widget, PdfTab) else None

    def current_view(self) -> Optional[PdfView]:
        tab = self.current_tab()
        return tab.view if tab else None

    def _call_view(self, method: str) -> None:
        view = self.current_view()
        if view is not None:
            getattr(view, method)()

    def _set_zoom(self, zoom: float) -> None:
        view = self.current_view()
        if view is not None:
            view.set_zoom(zoom)

    def _actual_size(self) -> None:
        view = self.current_view()
        if view is not None:
            view.reset_zoom()

    def _page_edit_entered(self) -> None:
        view = self.current_view()
        if view is None:
            return
        try:
            page = int(self.page_edit.text().strip())
        except ValueError:
            self._update_page_controls()
            return
        view.goto_page(page - 1)

    def previous_page(self) -> None:
        view = self.current_view()
        if view is not None:
            view.goto_page(view.current_page() - 1)

    def next_page(self) -> None:
        view = self.current_view()
        if view is not None:
            view.goto_page(view.current_page() + 1)

    def _on_tab_changed(self, _index: int) -> None:
        self._update_window_title()
        self._update_ui_for_current()
        query = self.search_edit.text().strip()
        view = self.current_view()
        if view is not None:
            if query:
                view.start_search(query)
            else:
                self.search_count.setText("")

    def _update_window_title(self) -> None:
        tab = self.current_tab()
        if tab is None:
            self.setWindowTitle(APP_NAME)
        else:
            self.setWindowTitle(f"{tab.name} — {APP_NAME}")

    def _update_ui_for_current(self) -> None:
        tab = self.current_tab()
        view = tab.view if tab else None
        self._updating_ui = True
        try:
            self.action_print.setEnabled(view is not None)
            self.action_sidebar.setEnabled(view is not None)
            self.action_invert.setEnabled(view is not None)
            self.page_edit.setEnabled(view is not None)
            self.search_edit.setEnabled(view is not None)
            if view is None:
                self.page_edit.clear()
                self.page_total.setText("/ 0")
                self.zoom_button.setText(tr("适应宽度"))
                self.label_file.clear()
                self.label_page.clear()
                self.label_zoom.clear()
                self.label_selection.clear()
                return
            self.label_file.setText(
                tr("{name} · {pages} 页 · {size}").format(
                    name=tab.name,
                    pages=tab.document.page_count,
                    size=_natural_size(tab.document.file_size),
                )
            )
            self._update_page_controls()
            self._update_zoom_controls()
            self._on_selection_changed(len(view.selection_text()) if view.has_selection() else 0)
            self.search_count.setText("")
        finally:
            self._updating_ui = False

    def _update_page_controls(self) -> None:
        view = self.current_view()
        if view is None:
            return
        page = view.current_page() + 1
        total = view.document.page_count
        self.page_edit.setText(str(page))
        self.page_total.setText(f"/ {total}")
        self.label_page.setText(tr("第 {page} / {total} 页").format(page=page, total=total))

    def _update_zoom_controls(self) -> None:
        view = self.current_view()
        if view is None:
            return
        if view.zoom_mode == "width":
            text = tr("适应宽度")
        elif view.zoom_mode == "page":
            text = tr("适应页面")
        else:
            text = f"{round(view.zoom * 100)}%"
        self.zoom_button.setText(text)
        self.label_zoom.setText(text)

    def _on_page_changed(self, page: int) -> None:
        if self.sender() is not self.current_view():
            return
        page = max(0, page)
        self.page_edit.setText(str(page + 1))
        self.label_page.setText(
            tr("第 {page} / {total} 页").format(
                page=page + 1,
                total=self.current_view().document.page_count,
            )
        )

    def _on_zoom_changed(self, tab: PdfTab, zoom: float) -> None:
        if tab is not self.current_tab():
            return
        self._update_zoom_controls()
        self.show_status(tr("缩放 {percent}%").format(percent=round(zoom * 100)))

    def _on_selection_changed(self, chars: int) -> None:
        if self.sender() is not None and self.sender() is not self.current_view():
            return
        if chars > 0:
            self.label_selection.setText(tr("已选 {chars} 字").format(chars=chars))
        else:
            self.label_selection.clear()

    # -------------------------------------------------------------- edit ops
    def _line_edit_focus(self) -> Optional[QLineEdit]:
        widget = QApplication.focusWidget()
        return widget if isinstance(widget, QLineEdit) else None

    def copy(self) -> None:
        widget = self._line_edit_focus()
        if widget is not None and widget.selectedText():
            widget.copy()
            return
        view = self.current_view()
        if view is not None:
            view.copy_selection()

    def select_all(self) -> None:
        widget = self._line_edit_focus()
        if widget is not None:
            widget.selectAll()
            return
        view = self.current_view()
        if view is not None:
            view.select_all()

    def copy_page_text(self) -> None:
        view = self.current_view()
        if view is not None:
            view.copy_page_text()

    def copy_all_text(self) -> None:
        view = self.current_view()
        if view is not None:
            view.copy_all_text()

    def clear_selection(self) -> None:
        view = self.current_view()
        if view is not None:
            view.clear_selection()

    def print_current(self) -> None:
        tab = self.current_tab()
        if tab is None:
            return
        if print_document(self, tab.document):
            self.show_status(tr("打印任务已发送"))

    # ---------------------------------------------------------------- search
    def focus_search(self) -> None:
        if self.current_view() is None:
            return
        view = self.current_view()
        if view is not None and view.has_selection():
            text = view.selection_text().strip()
            if 0 < len(text) <= 120 and "\n" not in text:
                self.search_edit.setText(text)
        self.search_edit.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search_edit.selectAll()

    def _search_text_changed(self, text: str) -> None:
        if self._updating_ui:
            return
        if not text.strip():
            self._search_timer.stop()
            view = self.current_view()
            if view is not None:
                view.clear_search()
            self.search_count.setText("")
            return
        self._search_timer.start()

    def _start_search(self) -> None:
        view = self.current_view()
        if view is None:
            return
        query = self.search_edit.text().strip()
        if not query:
            view.clear_search()
            return
        self.search_count.setText(tr("搜索中…"))
        view.start_search(query)

    def _search_next(self) -> None:
        view = self.current_view()
        if view is None:
            return
        if view.search_query != self.search_edit.text().strip():
            self._start_search()
        else:
            view.next_hit()

    def _search_escape(self) -> None:
        self.search_edit.clear()
        view = self.current_view()
        if view is not None:
            view.clear_search()
            view.setFocus(Qt.FocusReason.ShortcutFocusReason)

    def search_next(self) -> None:
        self._search_next()

    def search_previous(self) -> None:
        view = self.current_view()
        if view is not None:
            if view.search_query != self.search_edit.text().strip():
                self._start_search()
            else:
                view.previous_hit()

    def _on_search_progress(self, processed: int, total: int) -> None:
        if self.sender() is not self.current_view():
            return
        if processed < total:
            self.search_count.setText(tr("搜索中…"))

    def _on_search_finished(self, total: int) -> None:
        if self.sender() is not self.current_view():
            return
        if total == 0:
            self.search_count.setText(
                tr("无结果") if self.search_edit.text().strip() else ""
            )
        else:
            view = self.current_view()
            if view is not None and view.current_hit >= 0:
                self.search_count.setText(f"{view.current_hit + 1}/{total}")
            else:
                self.search_count.setText(f"0/{total}")

    def _on_search_position(self, current: int, total: int) -> None:
        if self.sender() is not self.current_view():
            return
        self.search_count.setText(f"{current}/{total}")

    # --------------------------------------------------------------- dialogs
    def show_association_dialog(self) -> None:
        dialog = AssociationDialog(self)
        dialog.exec()

    def remove_association(self) -> None:
        answer = QMessageBox.question(
            self,
            tr("移除文件关联"),
            tr(
                "移除 pdfreader 写入注册表的文件关联？\n\n"
                "pdfreader 是绿色单文件程序，这一步不会删除 exe，"
                "也不会清除最近文件、窗口位置和主题设置。\n"
                "之后仍可重新注册。"
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        try:
            unregister()
        except AssocError as exc:
            QMessageBox.critical(self, tr("移除失败"), str(exc))
            return
        QMessageBox.information(self, tr("已移除"), tr("注册表关联已删除。"))

    def show_shortcuts(self) -> None:
        QMessageBox.information(
            self,
            tr("快捷键"),
            tr(
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
                "F4        显示 / 隐藏目录侧栏\n"
                "F11       全屏\n"
                "PageUp/Down、空格  翻页 / 滚动\n"
                "Esc       清除选择"
            ),
        )

    def show_about(self) -> None:
        QMessageBox.about(
            self,
            tr("关于 pdfreader"),
            f"<b>pdfreader {__version__}</b><br><br>"
            + tr(
                "轻量 PDF 阅读器：连续滚动、选中文字复制、全文搜索、目录与缩略图、"
                "多标签、深色模式、打印。<br><br>"
            )
            + f"PyMuPDF {getattr(fitz, '__version__', '')}<br>"
            + tr("程序位置：{path}<br><br>").format(path=app_executable())
            + tr("图标与界面为原创设计，不使用 Adobe 商标。"),
        )

    # ------------------------------------------------------------------ misc
    def show_status(self, message: str) -> None:
        self.statusBar().showMessage(message, 6000)

    def _toggle_fullscreen(self, enabled: bool) -> None:
        if enabled:
            self.showFullScreen()
        else:
            self.showNormal()

    # ------------------------------------------------------------ drag & drop
    def dragEnterEvent(self, event) -> None:  # noqa: N802
        if self._pdf_urls(event.mimeData()):
            event.acceptProposedAction()

    def dragMoveEvent(self, event) -> None:  # noqa: N802
        if self._pdf_urls(event.mimeData()):
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:  # noqa: N802
        paths = self._pdf_urls(event.mimeData())
        if paths:
            self.open_paths(paths)
            event.acceptProposedAction()

    @staticmethod
    def _pdf_urls(mime) -> list[str]:
        if not mime.hasUrls():
            return []
        paths = []
        for url in mime.urls():
            if url.isLocalFile():
                path = url.toLocalFile()
                if path.lower().endswith(".pdf"):
                    paths.append(path)
        return paths


# --------------------------------------------------------------------------- single instance
class SingleInstanceServer:
    def __init__(self, window: MainWindow) -> None:
        self.window = window
        self.server = QLocalServer(window)
        self.server.setSocketOptions(QLocalServer.SocketOption.UserAccessOption)
        QLocalServer.removeServer(SINGLE_INSTANCE_KEY)
        if not self.server.listen(SINGLE_INSTANCE_KEY):
            # A previous instance may still own it; not fatal.
            pass
        self.server.newConnection.connect(self._on_connection)
        self._buffers: dict[QLocalSocket, bytes] = {}

    def _on_connection(self) -> None:
        socket = self.server.nextPendingConnection()
        if socket is None:
            return
        self._buffers[socket] = b""
        socket.readyRead.connect(lambda s=socket: self._read(s))
        socket.disconnected.connect(lambda s=socket: self._cleanup(s))

    def _read(self, socket: QLocalSocket) -> None:
        data = bytes(socket.readAll())
        buffer = self._buffers.get(socket, b"") + data
        while b"\n" in buffer:
            line, buffer = buffer.split(b"\n", 1)
            self._handle(line)
        self._buffers[socket] = buffer

    def _handle(self, line: bytes) -> None:
        try:
            payload = json.loads(line.decode("utf-8"))
        except Exception:
            return
        paths = payload.get("paths") or []
        if paths:
            self.window.open_paths([p for p in paths if isinstance(p, str)])
        self.window.showNormal()
        self.window.raise_()
        self.window.activateWindow()

    def _cleanup(self, socket: QLocalSocket) -> None:
        self._buffers.pop(socket, None)
        socket.deleteLater()

    def close(self) -> None:
        self.server.close()


def _send_to_running_instance(paths: list[str]) -> bool:
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_KEY)
    if not socket.waitForConnected(400):
        return False
    payload = json.dumps({"paths": paths}, ensure_ascii=False).encode("utf-8") + b"\n"
    socket.write(payload)
    socket.flush()
    socket.waitForBytesWritten(400)
    socket.disconnectFromServer()
    return True


# --------------------------------------------------------------------------- entry
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdfreader",
        description=tr("轻量 PDF 阅读器：选中文字复制、搜索、目录、多标签。"),
    )
    parser.add_argument("files", nargs="*", help=tr("要打开的 PDF 文件"))
    parser.add_argument(
        "--register",
        action="store_true",
        help=tr("注册 .pdf 文件关联（仅当前用户）"),
    )
    parser.add_argument(
        "--unregister",
        "--uninstall",
        dest="unregister",
        action="store_true",
        help=tr("移除本程序写入注册表的文件关联"),
    )
    parser.add_argument(
        "--selftest",
        nargs="?",
        const="",
        metavar="REPORT",
        help=tr("运行内置自检"),
    )
    parser.add_argument(
        "--no-single-instance",
        action="store_true",
        help=tr("允许启动多个独立窗口"),
    )
    parser.add_argument("--version", action="version", version=f"pdfreader {__version__}")
    return parser


def main(argv: Optional[list[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    if args.register:
        try:
            register()
        except AssocError as exc:
            print(tr("注册失败：{error}").format(error=exc), file=sys.stderr)
            return 1
        print(tr("已注册 .pdf 文件关联（HKCU）。"))
        return 0

    if args.unregister:
        try:
            unregister()
        except AssocError as exc:
            print(tr("移除失败：{error}").format(error=exc), file=sys.stderr)
            return 1
        print(tr("已移除注册表关联。"))
        return 0

    QApplication.setApplicationName(APP_NAME)
    QApplication.setOrganizationName(ORG_NAME)
    QApplication.setApplicationVersion(__version__)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv[:1])
    qt_translator = install_qt_translator(app)
    app.setStyle("Fusion")
    app.setFont(QFont("Segoe UI", 10))
    app.setWindowIcon(QIcon(str(resource_path("assets/pdfreader.ico"))))
    if args.selftest is not None:
        from .selftest import run_selftest

        report_path = args.selftest or None
        return run_selftest(report_path)

    files = [os.path.abspath(p) for p in args.files if p]
    if not args.no_single_instance:
        if _send_to_running_instance(files):
            return 0

    dark = _settings_bool(QSettings(ORG_NAME, APP_NAME), "ui/dark", False)
    app.setStyleSheet(stylesheet(dark))

    window = MainWindow()
    window.show()
    if files:
        QTimer.singleShot(0, lambda: window.open_paths(files))
    if not args.no_single_instance:
        window._server = SingleInstanceServer(window)
    return app.exec()
