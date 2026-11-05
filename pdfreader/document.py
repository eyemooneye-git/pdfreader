"""PDF document model built on PyMuPDF (no UI code here)."""

from __future__ import annotations

import os
from dataclasses import dataclass

try:  # PyMuPDF >= 1.24 imports as "pymupdf"; "fitz" is the legacy alias.
    import pymupdf as fitz
except ImportError:  # pragma: no cover - very old PyMuPDF
    import fitz  # type: ignore

from .i18n import tr


class PdfError(Exception):
    """The file could not be opened as a PDF."""


class PasswordRequired(PdfError):
    """The document is encrypted and needs a password."""

    def __init__(self, path: str) -> None:
        super().__init__(path)
        self.path = path


@dataclass(frozen=True)
class Word:
    """A single word in display (rotated) page coordinates."""

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int
    line: int
    index: int

    @property
    def rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class TextChar:
    """One extractable glyph (or space) in display coordinates.

    Character boxes let the mouse select part of a word instead of forcing
    whole-word granularity.
    """

    x0: float
    y0: float
    x1: float
    y1: float
    text: str
    block: int
    line: int
    index: int

    @property
    def rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class TextLine:
    """Characters that share a PDF text line, in reading order."""

    block: int
    line: int
    x0: float
    y0: float
    x1: float
    y1: float
    chars: tuple[TextChar, ...]

    @property
    def rect(self) -> fitz.Rect:
        return fitz.Rect(self.x0, self.y0, self.x1, self.y1)


@dataclass(frozen=True)
class OutlineItem:
    level: int
    title: str
    page: int  # 0-based; -1 when the bookmark has no local destination


@dataclass(frozen=True)
class SearchHit:
    page: int
    rect: fitz.Rect


class PdfDocument:
    """Cached wrapper around a PyMuPDF document.

    Pages, words and search results are memoised because the view asks for
    them repeatedly while painting and hit-testing.
    """

    def __init__(self, path: str, password: str | None = None) -> None:
        self.path = os.path.abspath(path)
        try:
            self._doc = fitz.open(self.path)
        except Exception as exc:  # pragma: no cover - depends on file
            raise PdfError(tr("无法打开 PDF：{error}").format(error=exc)) from exc

        if self._doc.needs_pass:
            ok = False
            if password is not None:
                try:
                    ok = bool(self._doc.authenticate(password))
                except Exception:
                    ok = False
            if not ok:
                self._doc.close()
                raise PasswordRequired(self.path)

        if not self._doc.is_pdf:
            self._doc.close()
            raise PdfError(tr("这个文件不是 PDF。"))

        self.page_count = self._doc.page_count
        self._pages: dict[int, fitz.Page] = {}
        self._words: dict[int, list[Word]] = {}
        self._chars: dict[int, list[TextChar]] = {}
        self._char_lines: dict[int, list[TextLine]] = {}
        self._text: dict[int, str] = {}
        try:
            self.file_size = os.path.getsize(self.path)
        except OSError:
            self.file_size = 0

        meta = self._doc.metadata or {}
        self.title = (meta.get("title") or "").strip() or os.path.splitext(os.path.basename(self.path))[0]
        self._outline: list[OutlineItem] | None = None

    # ------------------------------------------------------------------ pages
    def page(self, index: int) -> fitz.Page:
        page = self._pages.get(index)
        if page is None:
            page = self._doc.load_page(index)
            self._pages[index] = page
        return page

    def page_size(self, index: int) -> tuple[float, float]:
        rect = self.page(index).rect
        return rect.width, rect.height

    def page_rotation(self, index: int) -> int:
        return int(self.page(index).rotation or 0)

    # ------------------------------------------------------------------- text
    def words(self, index: int) -> list[Word]:
        cached = self._words.get(index)
        if cached is not None:
            return cached

        page = self.page(index)
        rotation = int(page.rotation or 0)
        matrix = page.rotation_matrix if rotation else None
        words: list[Word] = []
        try:
            # For rotated pages the physical sort happens in unrotated space,
            # which scrambles reading order after mapping to the screen. Keep
            # the content-stream order there; normal pages use PyMuPDF's
            # vertical/horizontal sort.
            raw = page.get_text("words", sort=rotation == 0)
        except Exception:
            raw = []
        for i, item in enumerate(raw):
            try:
                x0, y0, x1, y1, text, block, line, _no = item
            except (TypeError, ValueError):
                continue
            text = (text or "").strip()
            if not text:
                continue
            rect = fitz.Rect(x0, y0, x1, y1)
            if matrix is not None:
                rect = rect * matrix
            if rect.is_empty:
                continue
            words.append(
                Word(rect.x0, rect.y0, rect.x1, rect.y1, text, int(block), int(line), len(words))
            )
        self._words[index] = words
        return words

    def chars(self, index: int) -> list[TextChar]:
        """Character-level boxes used for arbitrary text selection."""
        cached = self._chars.get(index)
        if cached is not None:
            return cached

        page = self.page(index)
        rotation = int(page.rotation or 0)
        matrix = page.rotation_matrix if rotation else None
        chars: list[TextChar] = []
        try:
            # Keep the content-stream order on rotated pages for the same
            # reason as in words(); normal pages use visual reading order.
            raw = page.get_text("rawdict", sort=rotation == 0)
        except Exception:
            raw = {}
        for block in raw.get("blocks", []):
            if block.get("type", 0) != 0:
                continue
            block_no = int(block.get("number", 0))
            for line_no, line in enumerate(block.get("lines", [])):
                for span in line.get("spans", []):
                    for item in span.get("chars", []):
                        text = item.get("c") or ""
                        if not text:
                            continue
                        bbox = item.get("bbox")
                        if not bbox:
                            continue
                        try:
                            rect = fitz.Rect(bbox)
                            if matrix is not None:
                                rect = rect * matrix
                        except Exception:
                            continue
                        if rect.is_empty:
                            continue
                        chars.append(
                            TextChar(
                                rect.x0,
                                rect.y0,
                                rect.x1,
                                rect.y1,
                                text,
                                block_no,
                                line_no,
                                len(chars),
                            )
                        )
        page_width = float(page.rect.width)
        grouped: dict[tuple[int, int], list[TextChar]] = {}
        for char in chars:
            grouped.setdefault((char.block, char.line), []).append(char)

        lines = list(grouped.values())
        if page_width > 0 and len(lines) >= 4:
            split = page_width * 0.5
            left_lines = [
                line
                for line in lines
                if max(char.x1 for char in line) < split
                and min(char.x0 for char in line) < split * 0.75
            ]
            right_lines = [
                line
                for line in lines
                if min(char.x0 for char in line) > split
                and max(char.x1 for char in line) > split * 1.25
            ]
            if len(left_lines) >= 2 and len(right_lines) >= 2:
                left_keys = {(char.block, char.line) for line in left_lines for char in line}
                right_keys = {(char.block, char.line) for line in right_lines for char in line}

                def line_y(line: list[TextChar]) -> float:
                    return min(char.y0 for char in line)

                ordered_keys = [
                    (char.block, char.line)
                    for line in sorted(left_lines, key=lambda item: (line_y(item), min(char.x0 for char in item)))
                    for char in line[:1]
                ]
                ordered_keys += [
                    (char.block, char.line)
                    for line in sorted(right_lines, key=lambda item: (line_y(item), min(char.x0 for char in item)))
                    for char in line[:1]
                ]
                column_keys = set(left_keys) | set(right_keys)
                intermediate_keys = [
                    key for key in grouped if key not in column_keys
                ]
                ordered_keys = intermediate_keys + ordered_keys

                ordered_chars: list[TextChar] = []
                for key in ordered_keys:
                    line_chars = sorted(grouped[key], key=lambda char: (char.x0, char.index))
                    ordered_chars.extend(line_chars)
                chars = [
                    TextChar(
                        char.x0,
                        char.y0,
                        char.x1,
                        char.y1,
                        char.text,
                        char.block,
                        char.line,
                        index,
                    )
                    for index, char in enumerate(ordered_chars)
                ]
        self._chars[index] = chars
        return chars

    def char_lines(self, index: int) -> list[TextLine]:
        """Group chars into text lines for hit-testing and readable copying."""
        cached = self._char_lines.get(index)
        if cached is not None:
            return cached

        grouped: list[list[TextChar]] = []
        current_key: tuple[int, int] | None = None
        for char in self.chars(index):
            key = (char.block, char.line)
            if current_key != key:
                grouped.append([])
                current_key = key
            grouped[-1].append(char)

        lines: list[TextLine] = []
        for group in grouped:
            if not group:
                continue
            lines.append(
                TextLine(
                    group[0].block,
                    group[0].line,
                    min(ch.x0 for ch in group),
                    min(ch.y0 for ch in group),
                    max(ch.x1 for ch in group),
                    max(ch.y1 for ch in group),
                    tuple(group),
                )
            )
        self._char_lines[index] = lines
        return lines

    def text(self, index: int) -> str:
        cached = self._text.get(index)
        if cached is None:
            try:
                cached = self.page(index).get_text("text")
            except Exception:
                cached = ""
            self._text[index] = cached
        return cached

    def all_text(self) -> str:
        parts: list[str] = []
        for i in range(self.page_count):
            text = self.text(i).strip()
            if text:
                parts.append(text)
        return "\n\n".join(parts)

    # ---------------------------------------------------------------- outline
    def outline(self) -> list[OutlineItem]:
        if self._outline is not None:
            return self._outline
        items: list[OutlineItem] = []
        try:
            toc = self._doc.get_toc(simple=True)
        except Exception:
            toc = []
        for entry in toc:
            try:
                level, title, page_no = entry
            except (TypeError, ValueError):
                continue
            page = int(page_no) - 1 if page_no and int(page_no) > 0 else -1
            if page >= self.page_count:
                page = -1
            items.append(OutlineItem(int(level), str(title).strip() or tr("未命名"), page))
        self._outline = items
        return items

    # ----------------------------------------------------------------- search
    def search_page(self, index: int, query: str, limit: int = 400) -> list[fitz.Rect]:
        if not query:
            return []
        page = self.page(index)
        matrix = page.rotation_matrix if int(page.rotation or 0) else None
        try:
            hits = page.search_for(query)
        except Exception:
            return []
        result: list[fitz.Rect] = []
        for rect in hits[:limit]:
            if matrix is not None:
                rect = rect * matrix
            result.append(rect)
        return result

    def page_links(self, index: int) -> list[dict]:
        try:
            return self.page(index).get_links()
        except Exception:
            return []

    def close(self) -> None:
        self._words.clear()
        self._chars.clear()
        self._char_lines.clear()
        self._text.clear()
        self._pages.clear()
        try:
            self._doc.close()
        except Exception:
            pass
