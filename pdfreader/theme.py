"""Light / dark stylesheet shared by the whole application."""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette


def palette(dark: bool) -> QPalette:
    """A matching QPalette so Fusion draws standard icons/controls correctly."""
    if dark:
        window, base, text = QColor("#0F1115"), QColor("#1B1F27"), QColor("#E6E8EB")
        button, muted = QColor("#171A21"), QColor("#9CA3AF")
        accent, disabled = QColor("#3B82F6"), QColor("#6B7280")
    else:
        window, base, text = QColor("#F3F4F6"), QColor("#FFFFFF"), QColor("#111827")
        button, muted = QColor("#FFFFFF"), QColor("#6B7280")
        accent, disabled = QColor("#2563EB"), QColor("#9CA3AF")

    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, window)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, button)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.Highlight, accent)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor("#FFFFFF"))
    p.setColor(QPalette.ColorRole.ToolTipBase, base)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.PlaceholderText, muted)
    p.setColor(QPalette.ColorRole.Link, accent)
    for role in (
        QPalette.ColorRole.WindowText,
        QPalette.ColorRole.Text,
        QPalette.ColorRole.ButtonText,
    ):
        p.setColor(QPalette.ColorGroup.Disabled, role, disabled)
    return p


def colors(dark: bool) -> dict[str, str]:
    """Theme colour tokens shared by the stylesheet and the painted icons."""
    if dark:
        return {
            "window": "#0F1115",
            "panel": "#171A21",
            "base": "#1B1F27",
            "text": "#E6E8EB",
            "muted": "#9CA3AF",
            "border": "#2A2F3A",
            "hover": "#232833",
            "accent": "#3B82F6",
            "accent_hover": "#60A5FA",
            "accent_text": "#FFFFFF",
            "selected": "#1E3A5F",
            "view": "#0B0D11",
            "handle": "#3B4250",
            "handle_hover": "#4B5563",
            "scroll_track": "#121722",
            "scroll_border": "#303746",
            "scroll_handle": "#667386",
            "scroll_handle_hover": "#8996A8",
            "scroll_handle_pressed": "#A7B3C3",
            "divider": "#39404E",
            "divider_hover": "#4B5563",
        }
    return {
        "window": "#F3F4F6",
        "panel": "#FFFFFF",
        "base": "#FFFFFF",
        "text": "#111827",
        "muted": "#6B7280",
        "border": "#E5E7EB",
        "hover": "#F3F4F6",
        "accent": "#2563EB",
        "accent_hover": "#1D4ED8",
        "accent_text": "#FFFFFF",
        "selected": "#DBEAFE",
        "view": "#E7E9EE",
        "handle": "#CBD5E1",
        "handle_hover": "#94A3B8",
        "scroll_track": "#E1E6ED",
        "scroll_border": "#B9C3D0",
        "scroll_handle": "#728096",
        "scroll_handle_hover": "#5B6B7F",
        "scroll_handle_pressed": "#475569",
        "divider": "#CDD5E0",
        "divider_hover": "#AEB9C8",
    }


def stylesheet(dark: bool) -> str:
    c = colors(dark)

    return f"""
    QWidget {{
        font-family: "Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif;
        font-size: 10pt;
        color: {c['text']};
    }}
    QMainWindow, QDialog {{ background: {c['window']}; }}
    QToolTip {{
        background: {c['panel']}; color: {c['text']};
        border: 1px solid {c['border']}; padding: 4px 7px;
    }}

    QToolBar {{
        background: {c['panel']};
        border: none;
        border-bottom: 1px solid {c['border']};
        spacing: 4px;
        padding: 6px 10px;
    }}
    QToolBar::separator {{
        background: {c['border']}; width: 1px; margin: 5px 6px;
    }}
    QToolButton {{
        background: transparent;
        border: 1px solid transparent;
        border-radius: 6px;
        padding: 5px 9px;
    }}
    QToolButton:hover {{ background: {c['hover']}; }}
    QToolButton:pressed {{ background: {c['selected']}; }}
    QToolButton:checked {{ background: {c['selected']}; color: {c['accent']}; }}
    QToolButton:disabled {{ color: {c['muted']}; }}

    QPushButton {{
        background: {c['base']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 6px 14px;
        min-height: 22px;
    }}
    QPushButton:hover {{ background: {c['hover']}; border-color: {c['handle']}; }}
    QPushButton:pressed {{ background: {c['selected']}; }}
    QPushButton:disabled {{ color: {c['muted']}; background: {c['window']}; }}
    QPushButton#primary {{
        background: {c['accent']};
        color: {c['accent_text']};
        border: 1px solid {c['accent']};
        font-weight: 600;
        padding: 8px 20px;
    }}
    QPushButton#primary:hover {{ background: {c['accent_hover']}; border-color: {c['accent_hover']}; }}
    QPushButton#primary:pressed {{ background: {c['accent']}; }}

    QLineEdit, QComboBox {{
        background: {c['base']};
        color: {c['text']};
        border: 1px solid {c['border']};
        border-radius: 6px;
        padding: 5px 9px;
        min-height: 22px;
        selection-background-color: {c['accent']};
        selection-color: #FFFFFF;
    }}
    QLineEdit:focus, QComboBox:focus {{ border-color: {c['accent']}; }}
    QLineEdit:disabled {{ color: {c['muted']}; background: {c['window']}; }}
    QComboBox::drop-down {{ border: none; width: 20px; }}
    QComboBox QAbstractItemView {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        selection-background-color: {c['selected']};
        selection-color: {c['text']};
        outline: 0;
    }}

    QTabWidget::pane {{ border: none; background: {c['window']}; }}
    QTabBar {{ background: {c['panel']}; }}
    QTabBar::tab {{
        background: transparent;
        color: {c['muted']};
        border: none;
        border-bottom: 2px solid transparent;
        padding: 7px 14px;
        min-width: 70px;
    }}
    QTabBar::tab:hover {{ background: {c['hover']}; color: {c['text']}; }}
    QTabBar::tab:selected {{
        color: {c['text']};
        border-bottom: 2px solid {c['accent']};
        font-weight: 600;
    }}
    QTabBar::close-button {{ margin: 2px; }}

    QTabWidget#SidebarTabs::pane {{
        border: none;
        background: {c['panel']};
    }}
    QTabWidget#SidebarTabs QTabBar {{
        background: {c['panel']};
        border-bottom: 1px solid {c['border']};
        padding: 0 6px;
    }}
    QTabWidget#SidebarTabs QTabBar::tab {{
        background: transparent;
        color: {c['muted']};
        border: none;
        border-radius: 7px;
        padding: 6px 10px;
        margin: 6px 3px;
        min-width: 66px;
    }}
    QTabWidget#SidebarTabs QTabBar::tab:hover {{
        background: {c['hover']};
        color: {c['text']};
    }}
    QTabWidget#SidebarTabs QTabBar::tab:selected {{
        background: {c['selected']};
        color: {c['text']};
        border: none;
    }}

    QTreeWidget, QListWidget {{
        background: {c['panel']};
        border: none;
        outline: 0;
        alternate-background-color: {c['window']};
    }}
    QTreeWidget::item, QListWidget::item {{
        padding: 4px 6px;
        border-radius: 4px;
    }}
    QTreeWidget::item:hover, QListWidget::item:hover {{ background: {c['hover']}; }}
    QTreeWidget::item:selected, QListWidget::item:selected {{
        background: {c['selected']};
        color: {c['text']};
    }}
    QHeaderView::section {{
        background: {c['panel']};
        color: {c['muted']};
        border: none;
        border-bottom: 1px solid {c['border']};
        padding: 6px;
    }}

    QMenuBar {{
        background: {c['panel']};
        border-bottom: 1px solid {c['border']};
        padding: 2px 6px;
    }}
    QMenuBar::item {{ padding: 5px 10px; border-radius: 4px; background: transparent; }}
    QMenuBar::item:selected {{ background: {c['hover']}; }}
    QMenu {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 8px;
        padding: 5px;
    }}
    QMenu::item {{ padding: 6px 26px 6px 22px; border-radius: 4px; }}
    QMenu::item:selected {{ background: {c['accent']}; color: #FFFFFF; }}
    QMenu::separator {{ height: 1px; background: {c['border']}; margin: 5px 8px; }}

    QStatusBar {{
        background: {c['panel']};
        color: {c['muted']};
        border-top: 1px solid {c['border']};
    }}
    QStatusBar::item {{ border: none; }}
    QStatusBar QLabel {{ color: {c['muted']}; padding: 0 6px; }}
    QStatusBar QLabel#StatusStrong {{ color: {c['text']}; }}

    QGraphicsView {{ background: {c['view']}; border: none; }}
    QSplitter::handle {{ background: {c['border']}; width: 1px; height: 1px; }}
    QSplitter#SidebarSplitter::handle {{
        background: {c['divider']};
        width: 4px;
    }}
    QSplitter#SidebarSplitter::handle:hover {{ background: {c['divider_hover']}; }}
    QSplitter#SidebarSplitter::handle:pressed {{ background: {c['accent']}; }}

    QScrollBar:vertical {{
        background: {c['scroll_track']};
        width: 16px;
        margin: 0;
        border-left: 1px solid {c['scroll_border']};
    }}
    QScrollBar::handle:vertical {{
        background: {c['scroll_handle']};
        min-height: 42px;
        border-radius: 5px;
        margin: 2px 2px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {c['scroll_handle_hover']}; }}
    QScrollBar::handle:vertical:pressed {{ background: {c['scroll_handle_pressed']}; }}
    QScrollBar:horizontal {{
        background: {c['scroll_track']};
        height: 16px;
        margin: 0;
        border-top: 1px solid {c['scroll_border']};
    }}
    QScrollBar::handle:horizontal {{
        background: {c['scroll_handle']};
        min-width: 42px;
        border-radius: 5px;
        margin: 2px 2px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {c['scroll_handle_hover']}; }}
    QScrollBar::handle:horizontal:pressed {{ background: {c['scroll_handle_pressed']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{
        width: 0; height: 0; background: transparent; border: none;
    }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

    QLabel#Hint {{ color: {c['muted']}; }}
    QLabel#Title {{ font-size: 30pt; font-weight: 700; letter-spacing: -1px; }}
    QLabel#Subtitle {{ color: {c['muted']}; font-size: 11pt; }}
    QLabel#SectionTitle {{ font-weight: 600; font-size: 10.5pt; }}

    QWidget#WelcomePage {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {c['window']}, stop:0.55 {c['window']}, stop:1 {c['base']});
    }}
    QFrame#WelcomeCard {{
        background: {c['panel']};
        border: 1px solid {c['border']};
        border-radius: 14px;
    }}
    QListWidget#RecentList {{
        background: transparent;
        border: none;
    }}
    QListWidget#RecentList::item {{
        padding: 9px 10px;
        border-radius: 7px;
    }}
    QListWidget#RecentList::item:hover {{ background: {c['hover']}; }}
    QListWidget#RecentList::item:selected {{ background: {c['selected']}; color: {c['text']}; }}
    QLabel#DropHint {{
        color: {c['muted']};
        border: 2px dashed {c['border']};
        border-radius: 12px;
        padding: 26px;
        background: {c['base']};
    }}
    QWidget#SidebarPanel {{
        background: {c['panel']};
    }}
    """
