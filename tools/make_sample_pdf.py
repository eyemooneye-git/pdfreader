"""Generate a small demo PDF used by the self-test and README screenshot."""

from __future__ import annotations

import os
import sys

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    import fitz  # type: ignore

PAGE_W, PAGE_H = 595, 842
MARGIN = 64
BLUE = (0.15, 0.39, 0.92)
DARK = (0.07, 0.09, 0.13)
GRAY = (0.42, 0.45, 0.50)
LIGHT = (0.90, 0.93, 0.98)

# Microsoft YaHei has both CJK and proportional Latin glyphs, so mixed
# strings such as "Ctrl+F 的命中" keep normal spacing. Embedding is subsetted
# by PyMuPDF; the demo PDF stays small.
CJK = "msyh"
CJK_BOLD = "msyhbd"
_FONT_FILES = {
    CJK: r"C:\Windows\Fonts\msyh.ttc",
    CJK_BOLD: r"C:\Windows\Fonts\msyhbd.ttc",
}


def _new_page(doc) -> "fitz.Page":
    return doc.new_page(width=PAGE_W, height=PAGE_H)


def _put(page, point, text, fontsize=10, fontname="helv", color=DARK, **kwargs) -> None:
    fontfile = _FONT_FILES.get(fontname)
    if fontfile:
        kwargs["fontfile"] = fontfile
    page.insert_text(point, text, fontsize=fontsize, fontname=fontname, color=color, **kwargs)


def _heading(page, text, number: str, y: float = 92) -> float:
    page.draw_rect(fitz.Rect(MARGIN, y - 26, PAGE_W - MARGIN, y + 44), color=None, fill=LIGHT)
    _put(page, (MARGIN + 14, y + 6), number, fontsize=26, fontname="hebo", color=BLUE)
    _put(page, (MARGIN + 72, y + 5), text, fontsize=19, fontname=CJK_BOLD, color=DARK)
    return y + 68


def _body(page, rect, text, size=10.5, color=DARK, font=CJK) -> None:
    kwargs = {}
    fontfile = _FONT_FILES.get(font)
    if fontfile:
        kwargs["fontfile"] = fontfile
    page.insert_textbox(
        rect,
        text,
        fontsize=size,
        fontname=font,
        color=color,
        lineheight=1.55,
        align=fitz.TEXT_ALIGN_LEFT,
        **kwargs,
    )


def _footer(page, number: int, total: int = 6) -> None:
    _put(page, 
        (PAGE_W / 2 - 22, PAGE_H - 34),
        f"{number} / {total}",
        fontsize=8.5,
        fontname="helv",
        color=GRAY,
    )


def build(path: str) -> str:
    doc = fitz.open()

    # ---------------------------------------------------------------- page 1
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    page.draw_rect(fitz.Rect(0, 0, PAGE_W, 10), color=None, fill=BLUE)
    page.draw_rect(fitz.Rect(MARGIN, 92, MARGIN + 52, 144), color=None, fill=BLUE, radius=0.18)
    _put(page, (MARGIN + 13, 129), "P", fontsize=30, fontname="hebo", color=(1, 1, 1))
    _put(page, (MARGIN + 70, 122), "pdfreader", fontsize=30, fontname="hebo", color=DARK)
    _put(page, 
        (MARGIN + 72, 150),
        "轻量 PDF 阅读器 · 选择文字 · 复制 · 搜索",
        fontsize=10.5,
        fontname=CJK,
        color=GRAY,
    )

    y = 208
    _put(page, (MARGIN, y), "示例文档", fontsize=18, fontname=CJK_BOLD, color=BLUE)
    y += 28
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 118),
        "这是一个用于测试 pdfreader 的示例 PDF。用鼠标从“连续滚动”拖到“打印”，"
        "松开后按 Ctrl+C，就可以把选中的文字复制到剪贴板。文字选择按阅读顺序工作，"
        "跨行和跨页都可以。",
    )
    y += 126
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 112),
        "pdfreader 使用 PyMuPDF 渲染页面，支持连续滚动、缩放、目录、缩略图、全文搜索、"
        "多标签、深色模式和打印。所有处理都在本机完成，不上传文件，也不需要账号。",
    )
    y += 120
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 104),
        "The quick brown fox jumps over the lazy dog. Text selection keeps spaces "
        "and line breaks, so copied paragraphs stay readable in other applications. "
        "Try searching for the word “selection” with Ctrl+F.",
        size=10.5,
        font="helv",
    )

    # A clickable internal link.
    link_rect = fitz.Rect(MARGIN, 610, MARGIN + 168, 636)
    page.draw_rect(link_rect, color=BLUE, width=0.8, radius=0.15)
    _put(page, (MARGIN + 10, 626), "跳到第 3 页 →", fontsize=10, fontname=CJK, color=BLUE)
    # Links are inserted after every page exists (see the end of build()).
    ext_rect = fitz.Rect(MARGIN, 668, MARGIN + 250, 690)
    _put(page, 
        (ext_rect.x0, 682),
        "参考：pymupdf.readthedocs.io",
        fontsize=10,
        fontname="helv",
        color=BLUE,
    )
    page.draw_line((ext_rect.x0, 684), (ext_rect.x0 + 158, 684), color=BLUE, width=0.6)

    page.draw_rect(fitz.Rect(MARGIN, 730, PAGE_W - MARGIN, 734), color=None, fill=LIGHT)
    _put(page, 
        (MARGIN, 760),
        "提示：右键 PDF → 打开方式 → pdfreader，或在设置中设为默认。",
        fontsize=9,
        fontname=CJK,
        color=GRAY,
    )
    _footer(page, 1)

    # ---------------------------------------------------------------- page 2
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = _heading(page, "搜索测试", "02")
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 70),
        "这一页重复出现关键词，方便测试 Ctrl+F 的命中数量和上一个/下一个跳转。",
        color=GRAY,
    )
    y += 64
    for i in range(6):
        _body(
            page,
            fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 46),
            f"{i + 1}. Text selection is a core feature. Select any sentence and copy it.",
            font="helv",
            size=11,
        )
        y += 46
    y += 16
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 74),
        "选中文字后，状态栏会显示字符数。复制不会带上 PDF 的排版信息，只保留换行。",
    )
    y += 88
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 60),
        "搜索 selection，看看右侧的命中计数如何变化。",
        color=GRAY,
    )
    _footer(page, 2)

    # ---------------------------------------------------------------- page 3
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = _heading(page, "中文排版", "03")
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 220),
        "中文没有空格，复制时需要避免在汉字之间插入多余的空格。pdfreader 对中文和英文"
        "混排做了简单处理：汉字与汉字直接相连，英文单词之间保留空格，标点符号紧跟前文。"
        "这段文字可以整段选中，也可以只选其中一句。\n\n"
        "标点测试：逗号，句号。问号？感叹号！分号；冒号：括号（示例）以及“引号”。\n\n"
        "第二段用于验证跨行选择。拖动鼠标时，高亮会覆盖经过的词语；松开后剪贴板里"
        "得到的是按阅读顺序排列的纯文本。",
    )
    y += 238
    _body(
        page,
        fitz.Rect(MARGIN, y, PAGE_W - MARGIN, y + 96),
        "English and 中文 can be mixed in one paragraph. Copying should produce "
        "“English and 中文” rather than inserting spaces between every CJK glyph.",
        size=10.5,
    )
    _footer(page, 3)

    # ---------------------------------------------------------------- page 4
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = _heading(page, "双栏文字", "04")
    col_w = (PAGE_W - MARGIN * 2 - 28) / 2
    left = fitz.Rect(MARGIN, y, MARGIN + col_w, 690)
    right = fitz.Rect(MARGIN + col_w + 28, y, PAGE_W - MARGIN, 690)
    _body(
        page,
        left,
        "左栏。读取顺序通常是从上到下、从左到右。选择文字时，pdfreader 依赖 PDF "
        "内部的内容流顺序，因此双栏排版有时会出现左右栏交替的情况。\n\n"
        "这是一个已知限制，不影响复制单栏正文。\n\n"
        "Left column: continuous scrolling is smooth because pages are rendered "
        "lazily and cached near the viewport.",
        size=10,
    )
    _body(
        page,
        right,
        "右栏。目录和缩略图在左侧栏中，按 F4 可以显示或隐藏。点击目录项会跳到对应页。\n\n"
        "缩略图是后台分批生成的，打开很大的文档时不会卡住界面。\n\n"
        "Right column: thumbnails are produced in small batches with a timer.",
        size=10,
    )
    page.draw_line((PAGE_W / 2, y), (PAGE_W / 2, 690), color=LIGHT, width=1.2)
    _footer(page, 4)

    # ---------------------------------------------------------------- page 5
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    y = _heading(page, "长段落与快捷键", "05")
    lines = [
        ("Ctrl+O", "打开 PDF"),
        ("Ctrl+F", "搜索，Enter / Shift+Enter 切换结果"),
        ("Ctrl+C", "复制选中文字"),
        ("Ctrl+A", "全选（超大文档只选当前页）"),
        ("Ctrl+0", "适应宽度"),
        ("Ctrl+1", "实际大小 100%"),
        ("Ctrl+2", "适应页面"),
        ("Ctrl++ / Ctrl+-", "放大 / 缩小"),
        ("Ctrl+滚轮", "以鼠标位置为中心缩放"),
        ("F4", "显示 / 隐藏目录侧栏"),
        ("F11", "全屏"),
        ("PageUp / PageDown", "滚动或翻页"),
        ("Esc", "清除选择 / 退出搜索"),
    ]
    for key, desc in lines:
        _put(page, (MARGIN, y), key, fontsize=10.5, fontname="hebo", color=BLUE)
        _put(page, (MARGIN + 150, y), desc, fontsize=10.5, fontname=CJK, color=DARK)
        y += 30
    _footer(page, 5)

    # ---------------------------------------------------------------- page 6
    page = doc.new_page(width=PAGE_W, height=PAGE_H)
    _heading(page, "旋转页面", "06")
    _body(
        page,
        fitz.Rect(MARGIN, 190, PAGE_W - MARGIN, 420),
        "这一页会被旋转 90 度，用来检查文字选择坐标是否仍然正确。\n\n"
        "Rotated pages should still allow selection and copying.",
        size=11,
    )
    page.set_rotation(90)
    _footer(page, 6)

    # Add the cover links now that all destination pages exist. PyMuPDF 1.26
    # invalidates earlier Page objects when new_page() is called, so linking
    # is done last against a freshly loaded page.
    cover = doc.load_page(0)
    cover.insert_link(
        {
            "kind": fitz.LINK_GOTO,
            "from": fitz.Rect(MARGIN, 610, MARGIN + 168, 636),
            "page": 2,
            "to": fitz.Point(72, 84),
            "zoom": 0,
        }
    )
    cover.insert_link(
        {
            "kind": fitz.LINK_URI,
            "from": fitz.Rect(MARGIN, 668, MARGIN + 250, 690),
            "uri": "https://pymupdf.readthedocs.io/",
        }
    )

    doc.set_toc(
        [
            [1, "封面", 1],
            [1, "搜索测试", 2],
            [1, "中文排版", 3],
            [1, "双栏文字", 4],
            [1, "长段落与快捷键", 5],
            [1, "旋转页面", 6],
        ]
    )
    doc.set_metadata(
        {
            "title": "pdfreader 示例文档",
            "author": "pdfreader",
            "subject": "text selection, search and navigation demo",
            "keywords": "pdfreader, pdf, selection, search",
        }
    )
    try:
        doc.subset_fonts()
    except Exception:
        pass
    doc.save(path, garbage=3, deflate=True)
    doc.close()
    return path


def main() -> int:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    out_dir = os.path.join(root, "sample")
    os.makedirs(out_dir, exist_ok=True)
    target = os.path.join(out_dir, "demo.pdf")
    build(target)
    print(f"Wrote {target} ({os.path.getsize(target)} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
