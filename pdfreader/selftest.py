"""Headless-ish self-test: opens the demo PDF, exercises selection and search."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import traceback
from typing import Callable

from PySide6.QtCore import QElapsedTimer, QPointF, QThread, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QMessageBox

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

from . import __version__
from .assoc import project_root
from .document import PdfDocument
from .i18n import (
    current_language,
    install_qt_translator,
    language_from_tags,
    set_language,
    tr,
)
from .theme import palette, stylesheet


def _pump(app: QApplication, milliseconds: int) -> None:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < milliseconds:
        app.processEvents()
        QThread.msleep(10)


def _wait(app: QApplication, predicate: Callable[[], bool], timeout_ms: int = 8000) -> bool:
    timer = QElapsedTimer()
    timer.start()
    while timer.elapsed() < timeout_ms:
        app.processEvents()
        if predicate():
            return True
        QThread.msleep(10)
    return predicate()


def _ensure_sample() -> str:
    root = project_root()
    target = root / "sample" / "demo.pdf"
    if target.exists():
        return str(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    script = root / "tools" / "make_sample_pdf.py"
    spec = importlib.util.spec_from_file_location("pdfreader_make_sample", script)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load sample generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.build(str(target))
    return str(target)


def run_selftest(report_path: str | None = None) -> int:
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv[:1])
    app.setStyle("Fusion")
    app.setPalette(palette(False))
    app.setStyleSheet(stylesheet(False))

    checks: list[dict] = []

    def check(name: str, ok: bool, detail: str = "") -> bool:
        checks.append({"name": name, "ok": bool(ok), "detail": str(detail)})
        return bool(ok)

    saved_language = current_language()
    set_language("en")
    english_ok = (
        tr("打开…") == "Open…"
        and tr("第 {page} / {total} 页").format(page=1, total=2) == "Page 1 / 2"
    )
    set_language("zh")
    chinese_ok = tr("打开…") == "打开…"
    qt_translator = install_qt_translator(app)
    button_text = ""
    if qt_translator is not None:
        box = QMessageBox(
            QMessageBox.Icon.Question,
            "test",
            "test",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        button_text = box.button(QMessageBox.StandardButton.Yes).text()
        box.deleteLater()
        app.removeTranslator(qt_translator)
    set_language(saved_language)
    fallback_ok = (
        language_from_tags(["de-DE", "de"]) == "en"
        and language_from_tags(["zh-Hant-TW", "zh"]) == "zh"
        and language_from_tags(["en-GB", "en"]) == "en"
    )
    check(
        "ui language",
        english_ok and chinese_ok and fallback_ok,
        saved_language,
    )
    check("qt translations", "是" in button_text, button_text or "not loaded")

    window = None
    try:
        sample = _ensure_sample()
        check("sample exists", os.path.isfile(sample), sample)

        document = PdfDocument(sample)
        check("page count", document.page_count == 6, str(document.page_count))
        words0 = document.words(0)
        chars0 = document.chars(0)
        check("text extraction", len(words0) > 20, f"{len(words0)} words on page 1")
        check("character extraction", len(chars0) > len(words0), f"{len(chars0)} chars")
        combined = " ".join(word.text for word in words0).lower()
        check("expected text", "pdfreader" in combined, combined[:80])
        check("cjk extraction", len(document.words(2)) > 0, f"{len(document.words(2))} words")
        check("rotated page", document.page_rotation(5) == 90, str(document.page_rotation(5)))
        rotated_words = document.words(5)
        check("rotated words", len(rotated_words) > 0, f"{len(rotated_words)} words")
        if rotated_words:
            page_w, page_h = document.page_size(5)
            inside = all(
                -1.0 <= word.x0 and word.x1 <= page_w + 1.0
                and -1.0 <= word.y0 and word.y1 <= page_h + 1.0
                for word in rotated_words
            )
            check("rotated coords", inside, f"page {page_w:.0f}x{page_h:.0f}")
        hits = document.search_page(1, "selection")
        check("document search", len(hits) >= 5, f"{len(hits)} hits")
        check("outline", len(document.outline()) == 6, str(len(document.outline())))

        from .app import MainWindow

        window = MainWindow()
        window.resize(1280, 820)
        if window.dark_mode:
            window.set_dark_mode(False)
        if not window.sidebar_visible:
            window.set_sidebar_visible(True)
        window.show()
        _pump(app, 250)

        opened = window.open_path(sample)
        _pump(app, 600)
        tab = window.current_tab()
        check("window open", opened and tab is not None, "tab opened")
        if tab is None:
            raise RuntimeError("no tab after opening sample")

        view = tab.view
        check("view pages", len(view.pages) == 6, str(len(view.pages)))
        check("outline widget", tab.sidebar.outline.topLevelItemCount() == 6,
              str(tab.sidebar.outline.topLevelItemCount()))
        check("thumbnails", tab.sidebar.thumbs.count() == 6,
              str(tab.sidebar.thumbs.count()))

        # The sidebar can be widened and the thumbnail column must stay
        # centered as the splitter moves.  Restore the user's saved width
        # afterwards so the self-test does not alter their layout.
        sidebar = tab.sidebar
        saved_sidebar_width = window.sidebar_width
        sidebar.tabs.setCurrentIndex(1)
        tab.set_sidebar_width(360)
        _pump(app, 150)
        sizes = tab.splitter.sizes()
        item = sidebar.thumbs.item(0)
        if item is not None:
            rect = sidebar.thumbs.visualItemRect(item)
            margins = sidebar.thumbs.viewportMargins()
            center = rect.center().x() + margins.left() + sidebar.thumbs.frameWidth()
            offset = abs(center - sidebar.thumbs.width() / 2.0)
        else:
            offset = 999.0
        check("sidebar width", abs(sizes[0] - 360) <= 2, f"{sizes[0]} px")
        check("thumbnail centering", offset <= 2.0, f"off by {offset:.1f} px")
        sidebar.tabs.setCurrentIndex(0)
        tab.set_sidebar_width(saved_sidebar_width)
        _pump(app, 100)

        # A second file must create a tab, and closing it must fall back to
        # the first tab.  Use a temp copy so the "same path" de-duplication
        # logic does not interfere.
        second_path = os.path.join(tempfile.gettempdir(), "pdfreader-selftest-copy.pdf")
        shutil.copyfile(sample, second_path)
        try:
            opened_second = window.open_path(second_path, quiet=True)
            _pump(app, 450)
            check("multi tab", opened_second and window.tabs.count() == 2,
                  f"{window.tabs.count()} tabs")
            window.close_tab(window.tabs.currentIndex())
            _pump(app, 300)
            check("close tab", window.tabs.count() == 1,
                  f"{window.tabs.count()} tabs")
        finally:
            window._remove_recent(second_path)
            try:
                os.remove(second_path)
            except OSError:
                pass

        _wait(app, lambda: view.pages[0]._pixmap is not None, 5000)
        check("page rendering", view.pages[0]._pixmap is not None, "page 1 pixmap")

        # Programmatic selection on page 1 (drag equivalent).  Character
        # indices, not word indices: partial words must be selectable.
        view.goto_page(0)
        view._sel_anchor = (0, 2)
        view._sel_cursor = (0, min(30, len(chars0)))
        view._apply_selection()
        selected = view.selection_text()
        check("selection text", len(selected) > 10, selected.replace("\n", " ")[:90])
        copied = view.copy_selection()
        clipboard_text = QApplication.clipboard().text()
        check("clipboard", copied and clipboard_text == selected, f"{len(clipboard_text)} chars")
        menu = view._make_context_menu()
        actions = menu.actions()
        check("context menu", bool(actions) and actions[0].text() == tr("复制文字"),
              actions[0].text() if actions else "no actions")
        menu.deleteLater()

        # Simulate a real drag on the first page (not just private state).
        view.goto_page(0)
        view.clear_selection()
        _pump(app, 120)
        drag_words = document.words(0)
        if len(drag_words) >= 28:
            start_word = drag_words[20]
            end_word = drag_words[25]
            item0 = view.pages[0]

            def _to_viewport(word, edge: float):
                x = word.x0 if edge < 0.5 else word.x1
                local = QPointF(x * view.scale, (word.y0 + word.y1) / 2.0 * view.scale)
                return view.mapFromScene(item0.mapToScene(local))

            p1 = _to_viewport(start_word, 0.0)
            p2 = _to_viewport(end_word, 1.0)
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
            QTest.mouseMove(view.viewport(), p2, 40)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p2)
            _pump(app, 150)
            dragged = view.selection_text()
            expected_pair = f"{start_word.text}" in dragged and f"{end_word.text}" in dragged
            check("mouse drag", len(dragged) > 5 and expected_pair,
                  dragged.replace("\n", " ")[:90])
        else:
            check("mouse drag", False, "not enough words for drag test")

        # Drag only part of a word: this is the behavior that separates
        # character selection from the old whole-word selection.
        view.goto_page(1)
        view.clear_selection()
        _pump(app, 120)
        chars1 = document.chars(1)
        text1 = "".join(char.text for char in chars1)
        phrase_start = text1.find("Text selection")
        if phrase_start >= 0:
            item1 = view.pages[1]

            def _char_viewport(index: int, right_edge: bool):
                char = chars1[index]
                x = char.x1 - 0.1 if right_edge else char.x0 + 0.1
                local = QPointF(x * view.scale, (char.y0 + char.y1) / 2.0 * view.scale)
                return view.mapFromScene(item1.mapToScene(local))

            p1 = _char_viewport(phrase_start + 1, False)
            p2 = _char_viewport(phrase_start + 7, True)
            QTest.mousePress(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p1)
            QTest.mouseMove(view.viewport(), p2, 40)
            QTest.mouseRelease(view.viewport(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, p2)
            _pump(app, 120)
            partial = view.selection_text()
            check("partial mouse drag", partial.startswith("ext sel"), partial[:40])
        else:
            check("partial mouse drag", False, "phrase not found")

        # Selection hit-testing on the rotated page.
        rotated_words = document.words(5)
        if rotated_words:
            word = rotated_words[0]
            hit = view._caret_at(
                view.pages[5], (word.x0 + word.x1) / 2.0, (word.y0 + word.y1) / 2.0
            )
            check("rotated hit-test", hit is not None, f"hit index {hit}")

        # Search through the real UI path.
        window.search_edit.setText("selection")
        window._start_search()
        found = _wait(app, lambda: view.search_count >= 5, 8000)
        _pump(app, 600)
        check("view search", found and view.search_count >= 5, f"{view.search_count} hits")
        if view.search_count:
            first = view.current_hit
            view.next_hit()
            check("search next", view.current_hit != first, f"{view.current_hit + 1}/{view.search_count}")

        # Zoom modes.
        view.set_zoom(1.5)
        check("zoom custom", abs(view.zoom - 1.5) < 0.01, f"{view.zoom:.2f}")
        view.fit_width()
        check("fit width", view.zoom_mode == "width", f"{view.zoom:.2f}")
        _pump(app, 200)

        # Screenshot for the README (only when running from source).
        screenshot = project_root() / "docs" / "screenshot.png"
        if not getattr(sys, "frozen", False):
            screenshot.parent.mkdir(parents=True, exist_ok=True)
            view.goto_page(1)
            sharp = _wait(app, lambda: view.pages[1]._pixmap is not None, 3000)
            check("tiled page render", sharp, "page 2 composed")
            chars1 = document.chars(1)
            if len(chars1) > 20:
                view._sel_anchor = (1, 4)
                view._sel_cursor = (1, min(90, len(chars1)))
                view._apply_selection()
                view.selection_changed.emit(len(view.selection_text()))
            _pump(app, 150)
            pixmap = window.grab()
            saved = pixmap.save(str(screenshot))
            check("screenshot", saved and screenshot.stat().st_size > 20000,
                  f"{screenshot.stat().st_size if saved else 0} bytes")
        else:
            check("screenshot", True, "skipped in frozen build")

        document.close()
    except Exception:
        check("unexpected error", False, traceback.format_exc())
    finally:
        if window is not None:
            try:
                window.close()
                _pump(app, 100)
            except Exception:
                pass

    ok = all(item["ok"] for item in checks)
    report = {
        "ok": ok,
        "version": __version__,
        "frozen": bool(getattr(sys, "frozen", False)),
        "python": sys.version,
        "pymupdf": getattr(fitz, "__version__", ""),
        "checks": checks,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if report_path:
        path = os.path.abspath(report_path)
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text + "\n")
        # Windows consoles are often GBK; keep stdout ASCII-safe.
        print(json.dumps(report, ensure_ascii=True, indent=2))
    else:
        print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if ok else 1
