"""RocketCFD PDF belgeleri için ortak stil katmanı (reportlab, Türkçe karakterli TTF fontlar)."""
from __future__ import annotations

import re
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, Preformatted, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

FONT_DIR = Path(r"C:\Windows\Fonts")
pdfmetrics.registerFont(TTFont("Arial", str(FONT_DIR / "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", str(FONT_DIR / "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", str(FONT_DIR / "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", str(FONT_DIR / "arialbi.ttf")))
pdfmetrics.registerFont(TTFont("Consolas", str(FONT_DIR / "consola.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

NAVY = colors.HexColor("#0F2A47")
BLUE = colors.HexColor("#1F5FA8")
GREY = colors.HexColor("#5A6470")
LIGHT = colors.HexColor("#EEF2F7")
CODE_BG = colors.HexColor("#F4F5F7")
WARN_BG = colors.HexColor("#FFF4E5")
WARN_BD = colors.HexColor("#E8A33D")
OK_BG = colors.HexColor("#EAF6EC")
OK_BD = colors.HexColor("#3E9B4F")
INFO_BG = colors.HexColor("#EAF1FB")
INFO_BD = BLUE

S = {
    "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=22, leading=27, textColor=NAVY, spaceAfter=6),
    "subtitle": ParagraphStyle("subtitle", fontName="Arial", fontSize=11.5, leading=15, textColor=GREY, spaceAfter=14),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=15, leading=19, textColor=NAVY, spaceBefore=14, spaceAfter=7,
                         keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12, leading=15, textColor=BLUE, spaceBefore=10, spaceAfter=5,
                         keepWithNext=1),
    "body": ParagraphStyle("body", fontName="Arial", fontSize=9.6, leading=14.2, spaceAfter=5),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=8.2, leading=11, textColor=GREY),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8.4, leading=11.8),
    "cellb": ParagraphStyle("cellb", fontName="Arial-Bold", fontSize=8.4, leading=11.8, textColor=colors.white),
    "bullet": ParagraphStyle("bullet", fontName="Arial", fontSize=9.6, leading=13.4, leftIndent=14, bulletIndent=2,
                             spaceAfter=2.5, bulletFontName="Arial"),
    "code": ParagraphStyle("code", fontName="Consolas", fontSize=8.3, leading=10.6),
    "box": ParagraphStyle("box", fontName="Arial", fontSize=9.2, leading=12.6),
    "caption": ParagraphStyle("caption", fontName="Arial-Italic", fontSize=8.3, leading=11, textColor=GREY, alignment=TA_CENTER, spaceAfter=8),
    "center": ParagraphStyle("center", fontName="Arial", fontSize=9.6, leading=13, alignment=TA_CENTER),
}
CONTENT_W = A4[0] - 36 * mm


def esc(t: str) -> str:
    return escape(t)


_SUP = str.maketrans("⁻⁺⁰¹²³⁴⁵⁶⁷⁸⁹", "-+0123456789")
_SUP_RE = re.compile(r"[⁻⁺⁰¹²³⁴⁵⁶⁷⁸⁹]+")


def fix(text: str) -> str:
    """Arial'de olmayan Unicode üst simgeleri (⁻⁴, ⁺ ...) <super> işaretlemesine çevirir. ² ve ³ tek başına korunur."""
    def rep(m):
        s = m.group(0)
        return s if set(s) <= {"²", "³", "¹"} else f"<super>{s.translate(_SUP)}</super>"
    return _SUP_RE.sub(rep, text)


def P(text: str, style: str = "body") -> Paragraph:
    """Metin reportlab mini-HTML'i içerebilir (<b>, <i>, <font>); ham '<' gerekiyorsa esc() kullanın."""
    return Paragraph(fix(text), S[style])


def H1(t): return P(t, "h1")
def H2(t): return P(t, "h2")


def bullets(items: list[str], style: str = "bullet") -> list:
    return [Paragraph(fix(i), S[style], bulletText="•") for i in items]


def numbered(items: list[str]) -> list:
    return [Paragraph(fix(i), S["bullet"], bulletText=f"{n}.") for n, i in enumerate(items, 1)]


MAX_CODE_COLS = 100


def code(text: str) -> Table:
    long = [ln for ln in text.strip("\n").splitlines() if len(ln) > MAX_CODE_COLS]
    if long:
        raise ValueError(f"Kod satırı {MAX_CODE_COLS} karakteri aşıyor (sayfadan taşar): {long[0][:60]}...")
    pre = Preformatted(text.strip("\n"), S["code"])
    t = Table([[pre]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), CODE_BG), ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#C9CED6")),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    t.spaceBefore, t.spaceAfter = 2, 7
    return t


def box(text: str, kind: str = "info", title: str | None = None) -> Table:
    bg, bd = {"info": (INFO_BG, INFO_BD), "warn": (WARN_BG, WARN_BD), "ok": (OK_BG, OK_BD)}[kind]
    content = [Paragraph(f"<b>{fix(title)}</b>", S["box"])] if title else []
    content.append(Paragraph(fix(text), S["box"]))
    t = Table([[content]], colWidths=[CONTENT_W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg), ("LINEBEFORE", (0, 0), (0, -1), 3, bd),
                           ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
    t.spaceBefore, t.spaceAfter = 3, 8
    return t


def table(rows: list[list], widths: list[float] | None = None, header: bool = True, zebra: bool = True,
          font_size: float | None = None) -> Table:
    st = S["cell"] if font_size is None else ParagraphStyle("c2", parent=S["cell"], fontSize=font_size, leading=font_size * 1.42)
    sth = S["cellb"] if font_size is None else ParagraphStyle("c2b", parent=S["cellb"], fontSize=font_size, leading=font_size * 1.42)
    data = []
    for i, r in enumerate(rows):
        data.append([c if not isinstance(c, str) else Paragraph(fix(c), sth if (header and i == 0) else st) for c in r])
    if widths:
        tot = sum(widths)
        widths = [w / tot * CONTENT_W for w in widths]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    cmds = [("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#C9CED6")), ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
            ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for i in range(1 if header else 0, len(rows)):
            if i % 2 == 0:
                cmds.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(cmds))
    t.spaceBefore, t.spaceAfter = 2, 8
    return t


def image(path: Path, width_frac: float = 1.0, caption: str | None = None) -> list:
    from reportlab.lib.utils import ImageReader
    ir = ImageReader(str(path))
    iw, ih = ir.getSize()
    w = CONTENT_W * width_frac
    out = [Image(str(path), width=w, height=w * ih / iw)]
    if caption:
        out.append(Paragraph(caption, S["caption"]))
    return [KeepTogether(out)]


def build(path: Path, story: list, doc_title: str, subject: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    def on_page(canv, doc):
        canv.saveState()
        canv.setFont("Arial", 7.8)
        canv.setFillColor(GREY)
        canv.drawString(18 * mm, 10 * mm, f"RocketCFD — {doc_title}")
        canv.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Sayfa {doc.page}")
        canv.setStrokeColor(colors.HexColor("#C9CED6"))
        canv.setLineWidth(0.4)
        canv.line(18 * mm, 13 * mm, A4[0] - 18 * mm, 13 * mm)
        canv.restoreState()

    doc = SimpleDocTemplate(str(path), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm,
                            bottomMargin=18 * mm, title=doc_title, author="RocketCFD (Claude Code)", subject=subject)
    doc.build(story, onFirstPage=on_page, onLaterPages=on_page)


__all__ = ["P", "H1", "H2", "bullets", "numbered", "code", "box", "table", "image", "build", "esc", "S",
           "Spacer", "PageBreak", "KeepTogether", "mm", "CONTENT_W", "TA_LEFT"]
