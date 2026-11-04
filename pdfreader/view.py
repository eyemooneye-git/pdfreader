"""Continuous-scroll PDF view with word selection, search and zoom."""

from __future__ import annotations

import bisect
import math
from typing import Optional

from PySide6.QtCore import QPoint, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QFont,
    QImage,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
    QResizeEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QApplication, QGraphicsItem, QGraphicsScene, QGraphicsView, QMenu

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from .document import PdfDocument, SearchHit, TextChar, TextLine, Word
from .i18n import tr

BASE_SCALE = 96.0 / 72.0  # 100% zoom == 96 dpi
MARGIN = 26
PAGE_GAP = 22
MIN_ZOOM = 0.15
MAX_ZOOM = 6.0

# Rendering is split into small tiles.  A tile is cheap enough (a few ms on
# complex pages) that the event loop can keep servicing the scrollbar between
# tiles, unlike one monolithic page render which can block for 100 ms or more.
PREVIEW_TARGET_PX = 240
TILE_TARGET_PX = 512
TILE_INTERVAL_MS = 0

_ZOOM_STEPS = (
    0.25,
    0.33,
    0.5,
    0.67,
    0.75,
    0.9,
    1.0,
    1.1,
    1.25,
    1.5,
    1.75,
    2.0,
    2.5,
    3.0,
    4.0,
    5.0,
    6.0,
)

_CJK_RANGES = (
    (0x2E80, 0x2EFF),   # CJK radicals
    (0x3000, 0x303F),   # CJK punctuation
    (0x3040, 0x30FF),   # Hiragana / Katakana
    (0x3400, 0x4DBF),   # CJK extension A
    (0x4E00, 0x9FFF),   # CJK unified ideographs
    (0xAC00, 0xD7AF),   # Hangul
    (0xF900, 0xFAFF),   # compatibility ideographs
    (0xFF00, 0xFFEF),   # full-width forms
)

_NO_SPACE_BEFORE = set("，。！？；：、）》」』】…—,.!?;:)]}%”’")
_NO_SPACE_AFTER = set("（(《「『【[{“‘")


def _is_cjk(ch: str) -> bool:
    if not ch:
        return False
    code = ord(ch)
    for low, high in _CJK_RANGES:
        if low <= code <= high:
            return True
    return False


def words_to_text(words: list[Word]) -> str:
    """Join extracted words into readable text (CJK-aware)."""
    if not words:
        return ""
    lines: list[str] = []
    current: list[str] = []
    last_key: Optional[tuple[int, int]] = None
    for word in words:
        key = (word.block, word.line)
        if last_key is not None and key != last_key:
            lines.append("".join(current).rstrip())
            current = []
        elif current:
            prev = current[-1][-1:]
            head = word.text[:1]
            if (
                prev
                and head
                and not (_is_cjk(prev) and _is_cjk(head))
                and head not in _NO_SPACE_BEFORE
                and prev not in _NO_SPACE_AFTER
            ):
                current.append(" ")
        current.append(word.text)
        last_key = key
    if current:
        lines.append("".join(current).rstrip())
    return "\n".join(lines)


def chars_to_text(chars: list[TextChar]) -> str:
    """Join selected glyphs into lines without losing partial words.

    PDF text often contains real space (or NBSP) glyphs; keep them, but also
    add a conservative space when a PDF encodes word gaps purely as geometry.
    """
    if not chars:
        return ""
    lines: list[str] = []
    current: list[str] = []
    last_key: Optional[tuple[int, int]] = None
    previous: Optional[TextChar] = None

    def flush() -> None:
        nonlocal current
        if current:
            lines.append("".join(current).rstrip())
            current = []

    for char in chars:
        key = (char.block, char.line)
        if last_key is not None and key != last_key:
            flush()
            previous = None
        text = char.text.replace("\xa0", " ")
        if previous is not None and text and not text[0].isspace():
            prev_text = previous.text.replace("\xa0", " ")
            if prev_text and not prev_text[-1].isspace():
                gap = char.x0 - previous.x1
                line_height = max(1.0, char.y1 - char.y0, previous.y1 - previous.y0)
                if gap > max(1.5, line_height * 0.3):
                    prev_head = prev_text[-1]
                    head = text[0]
                    if not (_is_cjk(prev_head) and _is_cjk(head)):
                        current.append(" ")
        current.append(text)
        previous = char
        last_key = key
    flush()
    return "\n".join(lines)


class PageItem(QGraphicsItem):
    """One rendered PDF page, including selection/search overlays."""

    def __init__(self, view: "PdfView", index: int, width: float, height: float) -> None:
        super().__init__()
        self.view = view
        self.index = index
        self.page_width = width
        self.page_height = height
        self._scale = view.scale
        self._pixmap: Optional[QPixmap] = None
        self._preview_pixmap: Optional[QPixmap] = None
        self._pixmap_failed = False
        self._preview_failed = False
        self._tiles: dict[
            tuple[int, int], tuple[QPixmap, int, int, int, int]
        ] = {}
        self._tile_next = 0
        self._tile_rows = 0
        self._tile_cols = 0
        self._tile_count = 0
        self._tile_dpr = 1.0
        self._tile_render_scale = 1.0
        self._tile_page_rect = fitz.Rect(0, 0, width, height)
        self._tile_full_px = (0, 0)
        self._tile_failed = False
        self._selection_rects: list[fitz.Rect] = []
        self._search_hits: list[tuple[fitz.Rect, bool]] = []
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemUsesExtendedStyleOption, False)

    # ----------------------------------------------------------- geometry
    def _size(self) -> tuple[float, float]:
        return self.page_width * self._scale, self.page_height * self._scale

    def boundingRect(self) -> QRectF:  # noqa: N802 (Qt API)
        w, h = self._size()
        return QRectF(-2.0, -2.0, w + 8.0, h + 10.0)

    def set_scale(self, scale: float) -> None:
        if abs(scale - self._scale) < 1e-9:
            return
        self.prepareGeometryChange()
        self._scale = scale
        self._pixmap = None
        self._preview_pixmap = None
        self._pixmap_failed = False
        self._preview_failed = False
        self._reset_tiles()
        self.update()

    def set_selection(self, rects: list[fitz.Rect]) -> None:
        self._selection_rects = rects
        self.update()

    def set_search_hits(self, hits: list[tuple[fitz.Rect, bool]]) -> None:
        self._search_hits = hits
        self.update()

    def release_pixmap(self) -> None:
        if (
            self._pixmap is not None
            or self._preview_pixmap is not None
            or self._tiles
            or self._tile_failed
            or self._pixmap_failed
            or self._preview_failed
        ):
            self._pixmap = None
            self._preview_pixmap = None
            self._preview_failed = False
            self._pixmap_failed = False
            self._reset_tiles()
            self.update()

    def _reset_tiles(self) -> None:
        self._tiles.clear()
        self._tile_next = 0
        self._tile_rows = 0
        self._tile_cols = 0
        self._tile_count = 0
        self._tile_dpr = 1.0
        self._tile_render_scale = 1.0
        self._tile_full_px = (0, 0)
        self._tile_failed = False

    # ------------------------------------------------------------- rendering
    def _render_preview_pixmap(self) -> Optional[QPixmap]:
        """Quick medium-resolution render shown until the sharp page arrives.

        It is deliberately cached and much cheaper than the final page pixmap,
        so the thumb follows the mouse while every visible page keeps showing
        its content instead of going blank.
        """
        if self._preview_pixmap is not None or self._preview_failed:
            return self._preview_pixmap
        try:
            page = self.view.document.page(self.index)
            dpr = max(1.0, float(self.view.devicePixelRatioF()))
            full_scale = min(self._scale * dpr, 4.0)
            # Keep this deliberately small: it is rendered on the GUI thread
            # and must never delay the scrollbar.  Sharp tiles replace it as
            # the event loop gets breathing room.
            target_scale = PREVIEW_TARGET_PX / max(1.0, self.page_width)
            preview_scale = min(full_scale, max(0.2, target_scale))
            pix = page.get_pixmap(
                matrix=fitz.Matrix(preview_scale, preview_scale),
                alpha=False,
                annots=True,
            )
            fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            if self.view.invert_pages:
                image.invertPixels(QImage.InvertMode.InvertRgb)
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                raise RuntimeError("empty preview")
            self._preview_pixmap = pixmap
        except Exception:
            self._preview_failed = True
            self._preview_pixmap = None
        return self._preview_pixmap

    def _ensure_tile_grid(self) -> bool:
        if self._tile_rows:
            return True
        if self._pixmap is not None:
            return False
        try:
            page = self.view.document.page(self.index)
            rect = page.rect
            dpr = max(1.0, float(self.view.devicePixelRatioF()))
            render_scale = min(self._scale * dpr, 4.0)
            full_w = max(1, int(round(rect.width * render_scale)))
            full_h = max(1, int(round(rect.height * render_scale)))
            self._tile_dpr = dpr
            self._tile_render_scale = render_scale
            self._tile_page_rect = fitz.Rect(rect)
            self._tile_full_px = (full_w, full_h)
            self._tile_cols = max(1, math.ceil(full_w / TILE_TARGET_PX))
            self._tile_rows = max(1, math.ceil(full_h / TILE_TARGET_PX))
            self._tile_count = self._tile_rows * self._tile_cols
            self._tile_next = 0
            return True
        except Exception:
            self._tile_failed = True
            return False

    def has_pending_tiles(self) -> bool:
        if self._pixmap is not None or self._tile_failed:
            return False
        if not self._ensure_tile_grid():
            return False
        return self._tile_next < self._tile_count

    def render_next_tile(self) -> bool:
        if self._pixmap is not None or self._tile_failed:
            return False
        if not self._ensure_tile_grid() or self._tile_next >= self._tile_count:
            return False
        index = self._tile_next
        row = index // self._tile_cols
        col = index % self._tile_cols
        full_w, full_h = self._tile_full_px
        x0 = round(full_w * col / self._tile_cols)
        x1 = round(full_w * (col + 1) / self._tile_cols)
        y0 = round(full_h * row / self._tile_rows)
        y1 = round(full_h * (row + 1) / self._tile_rows)
        scale = self._tile_render_scale
        rect = self._tile_page_rect
        clip = fitz.Rect(
            rect.x0 + x0 / scale,
            rect.y0 + y0 / scale,
            rect.x0 + x1 / scale,
            rect.y0 + y1 / scale,
        )
        try:
            page = self.view.document.page(self.index)
            pix = page.get_pixmap(
                matrix=fitz.Matrix(scale, scale),
                alpha=False,
                annots=True,
                clip=clip,
            )
            fmt = (
                QImage.Format.Format_RGBA8888
                if pix.alpha
                else QImage.Format.Format_RGB888
            )
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            if self.view.invert_pages:
                image.invertPixels(QImage.InvertMode.InvertRgb)
            pixmap = QPixmap.fromImage(image)
            if pixmap.isNull():
                raise RuntimeError("empty tile")
            self._tiles[(row, col)] = (pixmap, x0, y0, x1, y1)
            self._tile_next += 1
            dpr = max(1.0, self._tile_dpr)
            if self._tile_next >= self._tile_count:
                self._compose_tiles()
                self.update()
            else:
                self.update(
                    QRectF(
                        x0 / dpr,
                        y0 / dpr,
                        (x1 - x0) / dpr,
                        (y1 - y0) / dpr,
                    )
                )
            return True
        except Exception:
            self._tile_failed = True
            if self._preview_pixmap is None and not self._tiles:
                self._pixmap_failed = True
            self.update()
            return False

    def _compose_tiles(self) -> None:
        if self._pixmap is not None or not self._tiles:
            return
        full_w, full_h = self._tile_full_px
        pixmap = QPixmap(full_w, full_h)
        pixmap.fill(QColor(255, 255, 255))
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, False)
        for tile, x0, y0, x1, y1 in self._tiles.values():
            painter.drawPixmap(
                QRectF(x0, y0, x1 - x0, y1 - y0),
                tile,
                QRectF(0.0, 0.0, float(tile.width()), float(tile.height())),
            )
        painter.end()
        pixmap.setDevicePixelRatio(self._tile_dpr)
        self._pixmap = pixmap
        self._tiles.clear()
        self._preview_pixmap = None

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        w, h = self._size()

        # Soft drop shadow.
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(15, 23, 42, 38 if not self.view.dark_background else 110))
        painter.drawRoundedRect(QRectF(2.0, 5.0, w, h), 3.0, 3.0)

        painter.setBrush(QColor(255, 255, 255))
        painter.setPen(QPen(QColor(0, 0, 0, 34), 1.0))
        painter.drawRect(QRectF(0.0, 0.0, w, h))

        # Draw the cheap preview first, then overlay sharp tiles as they are
        # produced.  Each tile render is small enough that the scrollbar keeps
        # following the mouse; the final composed pixmap replaces both.
        pixmap = self._pixmap
        # Smooth upscaling is expensive and the user cannot see the detail
        # during a fast drag anyway; switch it off until the thumb settles.
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            pixmap is not None or not self.view.is_fast_scrolling(),
        )
        if pixmap is not None:
            painter.drawPixmap(
                QRectF(0.0, 0.0, w, h),
                pixmap,
                QRectF(0.0, 0.0, float(pixmap.width()), float(pixmap.height())),
            )
        else:
            preview = self._render_preview_pixmap()
            if preview is not None:
                painter.drawPixmap(
                    QRectF(0.0, 0.0, w, h),
                    preview,
                    QRectF(0.0, 0.0, float(preview.width()), float(preview.height())),
                )
            dpr = max(1.0, self._tile_dpr)
            for tile, x0, y0, x1, y1 in self._tiles.values():
                painter.drawPixmap(
                    QRectF(x0 / dpr, y0 / dpr, (x1 - x0) / dpr, (y1 - y0) / dpr),
                    tile,
                    QRectF(0.0, 0.0, float(tile.width()), float(tile.height())),
                )
            if preview is None and not self._tiles and (
                self._tile_failed or self._preview_failed
            ):
                painter.setPen(QColor(185, 28, 28))
                painter.setFont(QFont("Segoe UI", 11))
                painter.drawText(
                    QRectF(0.0, 0.0, w, h),
                    Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                    tr("无法渲染此页"),
                )
            else:
                self.view.schedule_tile_work()

        # Search highlights below selection.
        scale = self._scale
        for rect, current in self._search_hits:
            if current:
                painter.setBrush(QColor(249, 115, 22, 135))
                painter.setPen(QPen(QColor(234, 88, 12, 220), 1.4))
            else:
                painter.setBrush(QColor(250, 204, 21, 105))
                painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(
                QRectF(rect.x0 * scale, rect.y0 * scale, rect.width * scale, rect.height * scale)
            )

        if self._selection_rects:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(37, 99, 235, 92))
            for rect in self._selection_rects:
                painter.drawRect(
                    QRectF(rect.x0 * scale, rect.y0 * scale, rect.width * scale, rect.height * scale)
                )


class PdfView(QGraphicsView):
    page_changed = Signal(int)
    zoom_changed = Signal(float)
    status_message = Signal(str)
    selection_changed = Signal(int)
    search_progress = Signal(int, int)
    search_finished = Signal(int)
    search_position = Signal(int, int)

    def __init__(self, document: PdfDocument, parent=None) -> None:
        super().__init__(parent)
        self.document = document
        self._shutting_down = False
        self.pages: list[PageItem] = []
        self._page_sizes: list[tuple[float, float]] = [
            document.page_size(i) for i in range(document.page_count)
        ]
        self.zoom = 1.0
        self.zoom_mode = "custom"  # "custom" | "width" | "page"
        self.invert_pages = False
        self.dark_background = False

        self._anchor: Optional[tuple[int, float, float]] = None
        self._rebuilding = False
        self._fit_pending = False
        self._current_page = 0

        # Selection state: character insertion points (page, char index).
        self._sel_anchor: Optional[tuple[int, int]] = None
        self._sel_cursor: Optional[tuple[int, int]] = None
        self._selected_pages: set[int] = set()
        self._dragging = False
        self._drag_moved = False
        self._select_all_mode = False

        # Page geometry cache (scene coordinates), used for fast scrolling.
        self._page_tops: list[float] = []
        self._page_bottoms: list[float] = []
        self._scroll_timer = QTimer(self)
        self._scroll_timer.setSingleShot(True)
        self._scroll_timer.setInterval(60)
        self._scroll_timer.timeout.connect(self._after_scroll)
        self._fast_scroll = False
        self._slider_dragging = False
        self._scroll_count = 0

        # One small page tile per tick, so PyMuPDF cannot monopolise the GUI
        # thread while the user is dragging the scrollbar.
        self._tile_timer = QTimer(self)
        self._tile_timer.setSingleShot(True)
        self._tile_timer.setInterval(TILE_INTERVAL_MS)
        self._tile_timer.timeout.connect(self._render_next_tile)

        # Search state.
        self._query = ""
        self._hits: list[SearchHit] = []
        self._hit_pages: dict[int, list[tuple[fitz.Rect, int]]] = {}
        self._current_hit = -1
        self._search_pos = 0
        self._search_timer = QTimer(self)
        self._search_timer.setSingleShot(False)
        self._search_timer.timeout.connect(self._search_chunk)

        self.setScene(QGraphicsScene(self))
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.BoundingRectViewportUpdate)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._show_context_menu)
        self.setBackgroundBrush(QColor("#E7E9EE"))

        for bar in (self.verticalScrollBar(), self.horizontalScrollBar()):
            bar.valueChanged.connect(self._on_scroll)
            bar.sliderPressed.connect(self._begin_slider_drag)
            bar.sliderReleased.connect(self._end_slider_drag)

        self._build_pages()
        self.set_zoom(1.0, mode="custom")

    # ------------------------------------------------------------- page layout
    def _build_pages(self) -> None:
        scene = self.scene()
        scene.clear()
        self.pages = []
        for index, (width, height) in enumerate(self._page_sizes):
            item = PageItem(self, index, width, height)
            scene.addItem(item)
            self.pages.append(item)
        self._layout_pages()

    @property
    def scale(self) -> float:
        return self.zoom * BASE_SCALE

    def _layout_pages(self) -> None:
        if not self.pages:
            self.scene().setSceneRect(QRectF(0, 0, 1, 1))
            return
        scale = self.scale
        widths = [w * scale for w, _ in self._page_sizes]
        heights = [h * scale for _, h in self._page_sizes]
        max_width = max(widths) if widths else 1.0
        y = float(MARGIN)
        self._page_tops = []
        self._page_bottoms = []
        for item, width, height in zip(self.pages, widths, heights):
            item.set_scale(scale)
            x = MARGIN + (max_width - width) / 2.0
            item.setPos(x, y)
            self._page_tops.append(y)
            self._page_bottoms.append(y + height)
            y += height + PAGE_GAP
        scene_width = max_width + MARGIN * 2
        scene_height = max(MARGIN * 2, y - PAGE_GAP + MARGIN)
        self.scene().setSceneRect(QRectF(0, 0, scene_width, scene_height))

    def _capture_anchor(self) -> Optional[tuple[int, float, float]]:
        if not self.pages:
            return None
        center = self.mapToScene(self.viewport().rect().center())
        for item in self.pages:
            rect = item.sceneBoundingRect()
            if rect.top() <= center.y() <= rect.bottom():
                rx = (center.x() - rect.left()) / max(1.0, rect.width())
                ry = (center.y() - rect.top()) / max(1.0, rect.height())
                return item.index, min(1.0, max(0.0, rx)), min(1.0, max(0.0, ry))
        index = self._nearest_page(center.y())
        item = self.pages[index]
        rect = item.sceneBoundingRect()
        ry = (center.y() - rect.top()) / max(1.0, rect.height())
        return index, 0.5, min(1.0, max(0.0, ry))

    def _restore_anchor(self, anchor: tuple[int, float, float]) -> None:
        index, rx, ry = anchor
        if not (0 <= index < len(self.pages)):
            return
        item = self.pages[index]
        rect = item.sceneBoundingRect()
        self.centerOn(rect.left() + rx * rect.width(), rect.top() + ry * rect.height())

    def _nearest_page(self, scene_y: float) -> int:
        if not self._page_tops:
            return 0
        index = bisect.bisect_right(self._page_tops, scene_y) - 1
        index = max(0, min(len(self._page_tops) - 1, index))
        # The next page may start just below scene_y; pick the closer one.
        if index + 1 < len(self._page_tops):
            if abs(scene_y - self._page_tops[index + 1]) < abs(scene_y - self._page_bottoms[index]):
                index += 1
        return index

    def current_page(self) -> int:
        if not self.pages:
            return 0
        center_y = self.mapToScene(self.viewport().rect().center()).y()
        return self._nearest_page(center_y)

    # ------------------------------------------------------------------ zoom
    def set_zoom(self, zoom: float, mode: str = "custom", anchor=None) -> None:
        zoom = max(MIN_ZOOM, min(MAX_ZOOM, float(zoom)))
        if abs(zoom - self.zoom) < 1e-6 and mode == self.zoom_mode:
            return
        if anchor is None:
            anchor = self._capture_anchor()
        self.zoom = zoom
        self.zoom_mode = mode
        self._rebuilding = True
        self._layout_pages()
        self._rebuilding = False
        if anchor is not None:
            self._restore_anchor(anchor)
        self._release_far_pixmaps(force=True)
        self.zoom_changed.emit(self.zoom)

    def zoom_in(self) -> None:
        for step in _ZOOM_STEPS:
            if step > self.zoom + 1e-6:
                self.set_zoom(step, mode="custom")
                return
        self.set_zoom(MAX_ZOOM, mode="custom")

    def zoom_out(self) -> None:
        for step in reversed(_ZOOM_STEPS):
            if step < self.zoom - 1e-6:
                self.set_zoom(step, mode="custom")
                return
        self.set_zoom(MIN_ZOOM, mode="custom")

    def fit_width(self) -> None:
        if not self.pages:
            return
        max_width = max(width for width, _ in self._page_sizes)
        available = max(80, self.viewport().width() - 2 * MARGIN - 4)
        scale = available / max_width
        self.set_zoom(scale / BASE_SCALE, mode="width")

    def fit_page(self) -> None:
        if not self.pages:
            return
        index = max(0, min(len(self.pages) - 1, self.current_page()))
        width, height = self._page_sizes[index]
        available_w = max(80, self.viewport().width() - 2 * MARGIN - 4)
        available_h = max(80, self.viewport().height() - 2 * MARGIN - 4)
        scale = min(available_w / width, available_h / height)
        self.set_zoom(scale / BASE_SCALE, mode="page")

    def reset_zoom(self) -> None:
        self.set_zoom(1.0, mode="custom")

    def goto_page(self, index: int, point: Optional[tuple[float, float]] = None) -> None:
        if not self.pages:
            return
        index = max(0, min(len(self.pages) - 1, int(index)))
        item = self.pages[index]
        rect = item.sceneBoundingRect()
        if point is not None:
            x = rect.left() + point[0] * self.scale
            y = rect.top() + point[1] * self.scale
            self.centerOn(x, y)
        else:
            self.verticalScrollBar().setValue(int(rect.top() - 6))
            self.horizontalScrollBar().setValue(0)
        self._current_page = index
        self.page_changed.emit(index)

    def center_on_page_point(self, index: int, x: float, y: float) -> None:
        if not (0 <= index < len(self.pages)):
            return
        item = self.pages[index]
        rect = item.sceneBoundingRect()
        self.centerOn(rect.left() + x * self.scale, rect.top() + y * self.scale)

    # ----------------------------------------------------------------- events
    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        if self.zoom_mode == "width" and not self._rebuilding and not self._fit_pending:
            self._fit_pending = True
            QTimer.singleShot(0, self._fit_after_resize)

    def _fit_after_resize(self) -> None:
        self._fit_pending = False
        if self.zoom_mode == "width":
            self.fit_width()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            scene_point = self.mapToScene(event.position().toPoint())
            if event.angleDelta().y() > 0:
                self.zoom_in()
            elif event.angleDelta().y() < 0:
                self.zoom_out()
            self.centerOn(scene_point)
            event.accept()
            return
        super().wheelEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        key = event.key()
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_C:
                self.copy_selection()
                event.accept()
                return
            if key == Qt.Key.Key_A:
                self.select_all()
                event.accept()
                return
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_in()
                event.accept()
                return
            if key == Qt.Key.Key_Minus:
                self.zoom_out()
                event.accept()
                return
            if key == Qt.Key.Key_0:
                self.fit_width()
                event.accept()
                return
        if key == Qt.Key.Key_Escape:
            self.clear_selection()
            self.clear_search()
            event.accept()
            return
        if key in (Qt.Key.Key_PageDown, Qt.Key.Key_Space):
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() + self.viewport().height() - 40)
            event.accept()
            return
        if key == Qt.Key.Key_PageUp:
            bar = self.verticalScrollBar()
            bar.setValue(bar.value() - self.viewport().height() + 40)
            event.accept()
            return
        super().keyPressEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        item = self._page_item_at(event.position().toPoint())
        if item is None:
            self.clear_selection()
            event.accept()
            return

        page_x, page_y = self._page_point(item, event.position().toPoint())
        link = self._link_at(item, page_x, page_y)
        if link is not None:
            self._follow_link(link)
            event.accept()
            return

        caret = self._caret_at(item, page_x, page_y)
        self._dragging = True
        self._drag_moved = False
        self._select_all_mode = False
        if caret is None:
            self.clear_selection()
        else:
            self._sel_anchor = (item.index, caret)
            self._sel_cursor = (item.index, caret)
            self._clear_selection_rects()
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        pos = event.position().toPoint()
        if self._dragging and self._sel_anchor is not None:
            self._autoscroll(pos)
            item = self._page_item_at(pos)
            if item is not None:
                page_x, page_y = self._page_point(item, pos)
                caret = self._caret_at(item, page_x, page_y, slack=80.0)
                if caret is not None:
                    new_cursor = (item.index, caret)
                    if new_cursor != self._sel_cursor:
                        self._drag_moved = True
                        self._sel_cursor = new_cursor
                        self._apply_selection()
            event.accept()
            return

        item = self._page_item_at(pos)
        if item is not None:
            page_x, page_y = self._page_point(item, pos)
            if self._link_at(item, page_x, page_y) is not None:
                self.viewport().setCursor(Qt.CursorShape.PointingHandCursor)
                event.accept()
                return
            if self._line_at(item, page_x, page_y) is not None:
                self.viewport().setCursor(Qt.CursorShape.IBeamCursor)
                event.accept()
                return
        self.viewport().setCursor(Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            if self._sel_anchor is not None:
                if not self._drag_moved:
                    self.clear_selection()
                else:
                    self.selection_changed.emit(len(self.selection_text()))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            super().mouseDoubleClickEvent(event)
            return
        item = self._page_item_at(event.position().toPoint())
        if item is None:
            return
        page_x, page_y = self._page_point(item, event.position().toPoint())
        line = self._line_at(item, page_x, page_y)
        if line is None:
            return
        self._sel_anchor = (item.index, line.chars[0].index)
        self._sel_cursor = (item.index, line.chars[-1].index + 1)
        self._select_all_mode = False
        self._apply_selection()
        self.selection_changed.emit(len(self.selection_text()))
        event.accept()

    def _show_context_menu(self, pos: QPoint) -> None:
        menu = self._make_context_menu()
        menu.exec(self.viewport().mapToGlobal(pos))

    def _make_context_menu(self) -> QMenu:
        menu = QMenu(self)
        copy_text = menu.addAction(tr("复制文字"))
        copy_text.setEnabled(bool(self.selection_text().strip()))
        copy_text.triggered.connect(self.copy_selection)
        menu.addSeparator()
        select_all = menu.addAction(tr("全选"))
        select_all.triggered.connect(self.select_all)
        copy_page = menu.addAction(tr("复制本页文字"))
        copy_page.triggered.connect(self.copy_page_text)
        copy_all = menu.addAction(tr("复制全文"))
        copy_all.triggered.connect(self.copy_all_text)
        if self.has_selection():
            menu.addSeparator()
            clear = menu.addAction(tr("清除选择"))
            clear.triggered.connect(self.clear_selection)
        return menu

    def _autoscroll(self, pos: QPoint) -> None:
        margin = 24
        bar = self.verticalScrollBar()
        if pos.y() < margin:
            bar.setValue(bar.value() - 18)
        elif pos.y() > self.viewport().height() - margin:
            bar.setValue(bar.value() + 18)

    # --------------------------------------------------------------- selection
    def _page_item_at(self, pos: QPoint) -> Optional[PageItem]:
        item = self.itemAt(pos)
        if isinstance(item, PageItem):
            return item
        return None

    def _page_point(self, item: PageItem, pos: QPoint) -> tuple[float, float]:
        local = item.mapFromScene(self.mapToScene(pos))
        return local.x() / self.scale, local.y() / self.scale

    def _line_at(
        self, item: PageItem, page_x: float, page_y: float, slack: float = 18.0
    ) -> Optional[TextLine]:
        """Closest text line to a display-space point."""
        best: Optional[TextLine] = None
        best_distance = slack * slack
        for line in self.document.char_lines(item.index):
            rect = line.rect
            dx = max(rect.x0 - page_x, 0.0, page_x - rect.x1)
            dy = max(rect.y0 - page_y, 0.0, page_y - rect.y1)
            distance = dx * dx + dy * dy
            if distance < best_distance:
                best_distance = distance
                best = line
        return best

    def _caret_at(
        self, item: PageItem, page_x: float, page_y: float, slack: float = 18.0
    ) -> Optional[int]:
        """Return a character insertion point (0..len(chars)) near a point."""
        line = self._line_at(item, page_x, page_y, slack)
        if line is None or not line.chars:
            return None
        chars = line.chars
        centers_x = [(char.x0 + char.x1) / 2.0 for char in chars]
        centers_y = [(char.y0 + char.y1) / 2.0 for char in chars]
        horizontal = (max(centers_x) - min(centers_x)) >= (
            max(centers_y) - min(centers_y)
        )
        if horizontal:
            for char in chars:
                if page_x < (char.x0 + char.x1) / 2.0:
                    return char.index
            return chars[-1].index + 1
        for char in chars:
            if page_y < (char.y0 + char.y1) / 2.0:
                return char.index
        return chars[-1].index + 1

    @staticmethod
    def _selection_rects(chars: list[TextChar]) -> list[fitz.Rect]:
        """Merge selected glyph boxes into one highlight rect per text line."""
        rects: list[fitz.Rect] = []
        current_key: Optional[tuple[int, int]] = None
        x0 = y0 = x1 = y1 = 0.0
        for char in chars:
            key = (char.block, char.line)
            if current_key is not None and key != current_key:
                rects.append(fitz.Rect(x0, y0, x1, y1))
                current_key = None
            if current_key is None:
                current_key = key
                x0, y0, x1, y1 = char.x0, char.y0, char.x1, char.y1
            else:
                x0 = min(x0, char.x0)
                y0 = min(y0, char.y0)
                x1 = max(x1, char.x1)
                y1 = max(y1, char.y1)
        if current_key is not None:
            rects.append(fitz.Rect(x0, y0, x1, y1))
        return rects

    def _apply_selection(self) -> None:
        if self._sel_anchor is None or self._sel_cursor is None:
            self._clear_selection_rects()
            return
        start = self._sel_anchor
        end = self._sel_cursor
        if start > end:
            start, end = end, start
        start_page, start_index = start
        end_page, end_index = end

        pages: set[int] = set()
        for page in range(start_page, end_page + 1):
            chars = self.document.chars(page)
            if not chars:
                continue
            lo = start_index if page == start_page else 0
            hi = end_index if page == end_page else len(chars)
            lo = max(0, min(lo, len(chars)))
            hi = max(0, min(hi, len(chars)))
            if lo >= hi:
                continue
            self.pages[page].set_selection(self._selection_rects(chars[lo:hi]))
            pages.add(page)

        for page in self._selected_pages - pages:
            self.pages[page].set_selection([])
        self._selected_pages = pages

    def _clear_selection_rects(self) -> None:
        for page in self._selected_pages:
            self.pages[page].set_selection([])
        self._selected_pages.clear()

    def clear_selection(self) -> None:
        self._sel_anchor = None
        self._sel_cursor = None
        self._select_all_mode = False
        self._clear_selection_rects()
        self.selection_changed.emit(0)

    def selected_char_slices(self) -> list[tuple[int, list[TextChar]]]:
        if self._sel_anchor is None or self._sel_cursor is None:
            return []
        start, end = self._sel_anchor, self._sel_cursor
        if start > end:
            start, end = end, start
        result: list[tuple[int, list[TextChar]]] = []
        for page in range(start[0], end[0] + 1):
            chars = self.document.chars(page)
            if not chars:
                continue
            lo = start[1] if page == start[0] else 0
            hi = end[1] if page == end[0] else len(chars)
            lo = max(0, min(lo, len(chars)))
            hi = max(0, min(hi, len(chars)))
            if lo < hi:
                result.append((page, chars[lo:hi]))
        return result

    def selection_text(self) -> str:
        if self._select_all_mode:
            return self.document.all_text()
        pages = self.selected_char_slices()
        return "\n\n".join(chars_to_text(chars) for _, chars in pages if chars)

    def has_selection(self) -> bool:
        return self._select_all_mode or self._sel_anchor is not None

    def select_all(self) -> None:
        if not self.pages:
            return
        # Selecting every glyph of a huge document is expensive and rarely
        # useful; fall back to the current page for very large files.
        if self.document.page_count <= 60:
            for page in range(self.document.page_count):
                chars = self.document.chars(page)
                if chars:
                    self._sel_anchor = (page, 0)
                    break
            else:
                self.status_message.emit(tr("这个 PDF 没有可选择的文字（可能是扫描件）"))
                return
            for page in range(self.document.page_count - 1, -1, -1):
                chars = self.document.chars(page)
                if chars:
                    self._sel_cursor = (page, len(chars))
                    break
            self._select_all_mode = False
            self._apply_selection()
            self.selection_changed.emit(len(self.selection_text()))
            return
        page = max(0, min(self.document.page_count - 1, self.current_page()))
        chars = self.document.chars(page)
        if not chars:
            self.status_message.emit(tr("此页没有可选择的文字（可能是扫描件）"))
            return
        self._sel_anchor = (page, 0)
        self._sel_cursor = (page, len(chars))
        self._select_all_mode = False
        self._apply_selection()
        self.selection_changed.emit(len(self.selection_text()))

    def copy_selection(self) -> bool:
        text = self.selection_text()
        if not text.strip():
            self.status_message.emit(tr("没有选中文字（扫描件需要 OCR，当前版本不支持）"))
            return False
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.status_message.emit(tr("已复制 {count} 个字符").format(count=len(text)))
        return True

    def copy_page_text(self) -> None:
        page = max(0, min(self.document.page_count - 1, self.current_page()))
        text = self.document.text(page)
        if not text.strip():
            self.status_message.emit(tr("此页没有可复制的文字（可能是扫描件）"))
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.status_message.emit(
            tr("已复制第 {page} 页文字（{count} 个字符）").format(
                page=page + 1,
                count=len(text),
            )
        )

    def copy_all_text(self) -> None:
        text = self.document.all_text()
        if not text.strip():
            self.status_message.emit(tr("这个 PDF 没有可复制的文字（可能是扫描件）"))
            return
        clipboard = QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(text)
        self.status_message.emit(
            tr("已复制全文（{count} 个字符）").format(count=len(text))
        )

    # ----------------------------------------------------------------- search
    def start_search(self, query: str) -> None:
        self.clear_search(emit=False)
        self._query = query.strip()
        if not self._query:
            self.search_finished.emit(0)
            return
        self._search_pos = 0
        self._search_timer.start(0)

    def _search_chunk(self) -> None:
        if not self._query:
            self._search_timer.stop()
            return
        processed = 0
        total = self.document.page_count
        while self._search_pos < total and processed < 6 and len(self._hits) < 3000:
            page = self._search_pos
            rects = self.document.search_page(page, self._query)
            for rect in rects:
                index = len(self._hits)
                self._hits.append(SearchHit(page, rect))
                self._hit_pages.setdefault(page, []).append((rect, index))
            if rects:
                self._update_page_hits(page)
            self._search_pos += 1
            processed += 1
        self.search_progress.emit(self._search_pos, total)
        if self._current_hit < 0 and self._hits:
            self._set_current_hit(0, jump=True)
        if self._search_pos >= total or len(self._hits) >= 3000:
            self._search_timer.stop()
            self.search_finished.emit(len(self._hits))

    def _update_page_hits(self, page_index: int) -> None:
        if not (0 <= page_index < len(self.pages)):
            return
        current = self._current_hit
        hits = [
            (rect, index == current)
            for rect, index in self._hit_pages.get(page_index, [])
        ]
        self.pages[page_index].set_search_hits(hits)

    def _set_current_hit(self, index: int, jump: bool = False) -> None:
        if not self._hits:
            return
        old_page = self._hits[self._current_hit].page if 0 <= self._current_hit < len(self._hits) else -1
        self._current_hit = index % len(self._hits)
        new_page = self._hits[self._current_hit].page
        if old_page >= 0:
            self._update_page_hits(old_page)
        self._update_page_hits(new_page)
        self.search_position.emit(self._current_hit + 1, len(self._hits))
        if jump:
            self._jump_to_hit(self._current_hit)

    def _jump_to_hit(self, index: int) -> None:
        hit = self._hits[index]
        if not (0 <= hit.page < len(self.pages)):
            return
        item = self.pages[hit.page]
        rect = item.sceneBoundingRect()
        cx = (hit.rect.x0 + hit.rect.x1) / 2.0
        cy = (hit.rect.y0 + hit.rect.y1) / 2.0
        self.centerOn(rect.left() + cx * self.scale, rect.top() + cy * self.scale)
        self._current_page = hit.page
        self.page_changed.emit(hit.page)

    def next_hit(self) -> None:
        if not self._hits:
            self.status_message.emit(tr("没有搜索结果"))
            return
        self._set_current_hit(self._current_hit + 1, jump=True)

    def previous_hit(self) -> None:
        if not self._hits:
            self.status_message.emit(tr("没有搜索结果"))
            return
        self._set_current_hit(self._current_hit - 1, jump=True)

    def clear_search(self, emit: bool = True) -> None:
        self._search_timer.stop()
        self._query = ""
        for page in self._hit_pages:
            if 0 <= page < len(self.pages):
                self.pages[page].set_search_hits([])
        self._hit_pages.clear()
        self._hits.clear()
        self._current_hit = -1
        self._search_pos = 0
        if emit:
            self.search_finished.emit(0)

    @property
    def search_query(self) -> str:
        return self._query

    @property
    def search_count(self) -> int:
        return len(self._hits)

    @property
    def current_hit(self) -> int:
        return self._current_hit

    # ------------------------------------------------------------------ links
    def _link_at(self, item: PageItem, page_x: float, page_y: float) -> Optional[dict]:
        rotation = self.document.page_rotation(item.index)
        matrix = self.document.page(item.index).rotation_matrix if rotation else None
        for link in self.document.page_links(item.index):
            rect = link.get("from")
            if rect is None:
                continue
            target = fitz.Rect(rect)
            if matrix is not None:
                target = target * matrix
            if target.contains(fitz.Point(page_x, page_y)):
                return link
        return None

    def _follow_link(self, link: dict) -> None:
        uri = link.get("uri")
        if uri:
            QDesktopServices.openUrl(QUrl(uri))
            self.status_message.emit(tr("已打开链接：{uri}").format(uri=uri))
            return
        target = link.get("page", -1)
        if isinstance(target, int) and target >= 0:
            point = link.get("to")
            if point is not None:
                try:
                    self.goto_page(int(target), (float(point.x), float(point.y)))
                except Exception:
                    self.goto_page(int(target))
            else:
                self.goto_page(int(target))
            return
        if link.get("name"):
            try:
                resolved = self.document._doc.resolve_link(link)  # type: ignore[attr-defined]
            except Exception:
                resolved = None
            if resolved and int(resolved.get("page", -1)) >= 0:
                self.goto_page(int(resolved["page"]))

    # ------------------------------------------------------------------ misc
    def set_invert_pages(self, invert: bool) -> None:
        if invert == self.invert_pages:
            return
        self.invert_pages = invert
        for item in self.pages:
            item.release_pixmap()
        self.viewport().update()

    def set_dark_background(self, dark: bool) -> None:
        self.dark_background = dark
        self.setBackgroundBrush(QColor("#0B0D11" if dark else "#E7E9EE"))
        self.viewport().update()

    def is_fast_scrolling(self) -> bool:
        return self._fast_scroll

    def _begin_slider_drag(self) -> None:
        self._slider_dragging = True
        self._fast_scroll = True
        self._scroll_timer.stop()
        self._tile_timer.stop()

    def _end_slider_drag(self) -> None:
        self._slider_dragging = False
        self._fast_scroll = False
        self._scroll_timer.start()
        self.schedule_tile_work()

    def _sync_current_page(self) -> None:
        page = self.current_page()
        if page != self._current_page:
            self._current_page = page
            self.page_changed.emit(page)

    def _on_scroll(self, _value: int = 0) -> None:
        if self._rebuilding or not self.pages:
            return
        # Keep the page number/sidebar in step even while the thumb is held.
        self._sync_current_page()
        self._fast_scroll = True
        self._tile_timer.stop()
        self._scroll_count += 1
        if self._scroll_count % 8 == 0:
            self._release_far_pixmaps()
        # Even while the thumb is held, a short pause should sharpen the page.
        self._scroll_timer.start()

    def _after_scroll(self) -> None:
        if self._rebuilding or not self.pages:
            return
        self._fast_scroll = False
        self._sync_current_page()
        self._release_far_pixmaps()
        # Finish the visible page even if the last paint did not run.
        self.schedule_tile_work()
        self.viewport().update()

    def _release_far_pixmaps(self, force: bool = False) -> None:
        if force:
            # Zoom / invert changes invalidate every pixmap; drop them now.
            for item in self.pages:
                item.release_pixmap()
            return
        current = self.current_page()
        for item in self.pages:
            if abs(item.index - current) > 5:
                item.release_pixmap()

    def _visible_page_indices(self) -> list[int]:
        if not self.pages or not self._page_tops:
            return []
        view = self.mapToScene(self.viewport().rect()).boundingRect()
        top = view.top()
        bottom = view.bottom()
        index = max(0, bisect.bisect_left(self._page_bottoms, top))
        result: list[int] = []
        while index < len(self.pages) and self._page_tops[index] <= bottom:
            result.append(index)
            index += 1
        return result

    def schedule_tile_work(self, delay: int = 0) -> None:
        if self._shutting_down or not self.pages or self._fast_scroll:
            return
        if not self._tile_timer.isActive():
            self._tile_timer.start(max(0, delay))

    def _render_next_tile(self) -> None:
        if self._shutting_down or not self.pages or self._fast_scroll:
            return
        visible = self._visible_page_indices()
        visible.sort(key=lambda index: abs(index - self._current_page))
        for index in visible:
            item = self.pages[index]
            if item.has_pending_tiles():
                item.render_next_tile()
                self._tile_timer.start(TILE_INTERVAL_MS)
                return
        # Nothing visible is waiting; repaints/scrolls will schedule again.

    def shutdown(self) -> None:
        self._shutting_down = True
        self._search_timer.stop()
        self._scroll_timer.stop()
        self._tile_timer.stop()
        self.scene().clear()
        self.pages.clear()

    def rendered_debug_image(self, index: int = 0) -> QImage:
        """Helper for the self-test: render one page without a visible widget."""
        page = self.document.page(index)
        pix = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False, annots=True)
        fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
        return QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
