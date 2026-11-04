"""Outline and thumbnail side panel."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QIcon, QImage, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListWidget,
    QListWidgetItem,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from .document import PdfDocument
from .i18n import tr


class ThumbnailList(QListWidget):
    """Thumbnail list that keeps its single column centered in the panel."""

    COLUMN_WIDTH = 154

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._centering = False
        self.verticalScrollBar().rangeChanged.connect(self._center_items)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._center_items()

    def showEvent(self, event) -> None:  # noqa: N802
        super().showEvent(event)
        self._center_items()

    def _center_items(self, *_args) -> None:
        if self._centering:
            return
        self._centering = True
        try:
            bar = self.verticalScrollBar()
            policy = self.verticalScrollBarPolicy()
            scrollbar_width = 0
            if policy == Qt.ScrollBarPolicy.ScrollBarAlwaysOn or (
                policy != Qt.ScrollBarPolicy.ScrollBarAlwaysOff
                and bar.maximum() > bar.minimum()
            ):
                scrollbar_width = bar.sizeHint().width()
            usable = max(0, self.width() - 2 * self.frameWidth())
            left = max(0, (usable - self.COLUMN_WIDTH) // 2)
            right = max(0, usable - scrollbar_width - left - self.COLUMN_WIDTH)
            margins = self.viewportMargins()
            if margins.left() != left or margins.right() != right:
                self.setViewportMargins(left, 0, right, 0)
        finally:
            self._centering = False


class PdfSidebar(QWidget):
    page_requested = Signal(int)

    def __init__(self, document: PdfDocument, parent=None) -> None:
        super().__init__(parent)
        self.setObjectName("SidebarPanel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.document = document
        self._syncing = False
        self._thumb_page = 0
        self._thumb_timer = QTimer(self)
        self._thumb_timer.setInterval(0)
        self._thumb_timer.timeout.connect(self._make_thumbnails)

        self.tabs = QTabWidget(self)
        self.tabs.setObjectName("SidebarTabs")
        self.tabs.tabBar().setExpanding(True)
        self.tabs.tabBar().setDrawBase(False)

        # ---------------------------------------------------------- outline
        self.outline = QTreeWidget(self)
        self.outline.setHeaderHidden(True)
        self.outline.setIndentation(14)
        self.outline.setAnimated(True)
        self.outline.setUniformRowHeights(True)
        self.outline.itemClicked.connect(self._outline_clicked)
        self._fill_outline()
        self.tabs.addTab(self.outline, tr("目录"))

        # ------------------------------------------------------- thumbnails
        self.thumbs = ThumbnailList(self)
        self.thumbs.setViewMode(QListWidget.ViewMode.IconMode)
        self.thumbs.setFlow(QListWidget.Flow.TopToBottom)
        self.thumbs.setWrapping(False)
        self.thumbs.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.thumbs.setMovement(QListWidget.Movement.Static)
        self.thumbs.setIconSize(QSize(128, 168))
        self.thumbs.setGridSize(QSize(ThumbnailList.COLUMN_WIDTH, 202))
        self.thumbs.setSpacing(2)
        self.thumbs.setWordWrap(False)
        self.thumbs.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.thumbs.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.thumbs.itemClicked.connect(self._thumb_clicked)
        self._fill_thumb_items()
        self.tabs.addTab(self.thumbs, tr("缩略图"))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.tabs)

        self.setMinimumWidth(220)
        self.setMaximumWidth(560)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        # QTabBar sizes itself to its tabs; stretch it across the panel so the
        # two tabs share the full width.
        self.tabs.tabBar().setMinimumWidth(self.width())

    # --------------------------------------------------------------- outline
    def _fill_outline(self) -> None:
        items = self.document.outline()
        if not items:
            placeholder = QTreeWidgetItem([tr("此 PDF 没有目录")])
            placeholder.setFlags(Qt.ItemFlag.NoItemFlags)
            self.outline.addTopLevelItem(placeholder)
            return

        stack: list[QTreeWidgetItem] = []
        for entry in items:
            node = QTreeWidgetItem([entry.title])
            node.setToolTip(0, entry.title)
            if entry.page >= 0:
                node.setData(0, Qt.ItemDataRole.UserRole, entry.page)
            else:
                node.setFlags(node.flags() & ~Qt.ItemFlag.ItemIsSelectable)
            while stack and stack[-1].data(0, Qt.ItemDataRole.UserRole + 1) >= entry.level:
                stack.pop()
            if stack:
                stack[-1].addChild(node)
            else:
                self.outline.addTopLevelItem(node)
            node.setData(0, Qt.ItemDataRole.UserRole + 1, entry.level)
            stack.append(node)

    def _outline_clicked(self, item: QTreeWidgetItem, _column: int) -> None:
        page = item.data(0, Qt.ItemDataRole.UserRole)
        if isinstance(page, int) and page >= 0:
            self.page_requested.emit(page)

    # ------------------------------------------------------------ thumbnails
    def _fill_thumb_items(self) -> None:
        for index in range(self.document.page_count):
            item = QListWidgetItem(str(index + 1))
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom)
            item.setSizeHint(QSize(ThumbnailList.COLUMN_WIDTH, 198))
            self.thumbs.addItem(item)
        if self.document.page_count:
            self._thumb_timer.start()

    def _make_thumbnails(self) -> None:
        made = 0
        while self._thumb_page < self.document.page_count and made < 4:
            index = self._thumb_page
            item = self.thumbs.item(index)
            if item is not None:
                try:
                    page = self.document.page(index)
                    pix = page.get_pixmap(matrix=fitz.Matrix(0.19, 0.19), alpha=False, annots=False)
                    fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
                    item.setIcon(QIcon(QPixmap.fromImage(image)))
                except Exception:
                    pass
            self._thumb_page += 1
            made += 1
        if self._thumb_page >= self.document.page_count:
            self._thumb_timer.stop()

    def _thumb_clicked(self, item: QListWidgetItem) -> None:
        if self._syncing:
            return
        page = item.data(Qt.ItemDataRole.UserRole)
        if isinstance(page, int) and page >= 0:
            self.page_requested.emit(page)

    def set_current_page(self, index: int) -> None:
        if not (0 <= index < self.thumbs.count()):
            return
        self._syncing = True
        item = self.thumbs.item(index)
        if item is not None and self.thumbs.currentItem() is not item:
            self.thumbs.setCurrentItem(item)
            self.thumbs.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._syncing = False

    def shutdown(self) -> None:
        self._thumb_timer.stop()
