"""Print support (one PDF page per sheet, scaled to fit)."""

from __future__ import annotations

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPageLayout, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from .document import PdfDocument
from .i18n import tr


def print_document(parent, document: PdfDocument) -> bool:
    if document.page_count == 0:
        return False

    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setDocName(document.title)
    try:
        first_w, first_h = document.page_size(0)
        if first_w > first_h:
            printer.setPageOrientation(QPageLayout.Orientation.Landscape)
    except Exception:
        pass

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle(tr("打印 PDF"))
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return False

    painter = QPainter()
    if not painter.begin(printer):
        QMessageBox.warning(parent, tr("打印失败"), tr("无法初始化打印机。"))
        return False

    QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
    try:
        for index in range(document.page_count):
            if index:
                printer.newPage()
            viewport = painter.viewport()
            if viewport.width() <= 0 or viewport.height() <= 0:
                continue
            page = document.page(index)
            width, height = page.rect.width, page.rect.height
            fit = min(viewport.width() / width, viewport.height() / height)
            target_w = width * fit
            target_h = height * fit
            target = QRectF(
                viewport.x() + (viewport.width() - target_w) / 2.0,
                viewport.y() + (viewport.height() - target_h) / 2.0,
                target_w,
                target_h,
            )

            dpi_scale = min(4.0, max(1.0, printer.resolution() / 72.0))
            pix = page.get_pixmap(matrix=fitz.Matrix(dpi_scale, dpi_scale), alpha=False, annots=True)
            fmt = QImage.Format.Format_RGBA8888 if pix.alpha else QImage.Format.Format_RGB888
            image = QImage(pix.samples, pix.width, pix.height, pix.stride, fmt).copy()
            painter.drawImage(target, image)
    except Exception as exc:
        QMessageBox.warning(
            parent,
            tr("打印失败"),
            tr("打印过程中出错：{error}").format(error=exc),
        )
        return False
    finally:
        QApplication.restoreOverrideCursor()
        painter.end()
    return True
