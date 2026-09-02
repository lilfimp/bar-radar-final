"""Fixes known text-extraction artifacts before parsing menu content.

Real menus expose two recurring problems (confirmed against actual extracted
data, not hypothetical):

1. LETTER-SPACED WORDS. Some PDFs use stylized/wide-tracked fonts (common on
   trendy cocktail-bar branding). pdfplumber's text extraction reconstructs
   reading order from glyph positions, and a wide-tracked font makes it
   insert a space between every letter: "MAI TAI 16" becomes "M A I T A I
   1 6". This is NOT an OCR problem (confirmed: this happens on direct PDF
   text extraction too) - it's a font-kerning artifact.

2. MULTI-COLUMN PDFS COLLAPSING INTO SCRAMBLED READING ORDER. A two-column
   menu (e.g. cocktails on the left, food on the right) can extract with
   rows interleaved left-to-right rather than column-by-column, so a name
   and the price actually printed next to it aren't reliably adjacent in
   the extracted text. This is NOT fixed by normalization - it requires
   layout-aware extraction (tracking word bounding boxes), which Phase 2's
   extractor doesn't currently do. This module cannot fully undo it; the
   item parser's confidence scoring is the honest mitigation, not a fix.
"""
from __future__ import annotations

import re

# Collapses runs of 3+ single alphabetic characters separated by single
# spaces into one word: "M A I T A I" -> "MAITAI". Threshold of 3+ avoids
# accidentally collapsing legitimate short text (e.g. "a" or "I" appearing
# naturally) - normal prose essentially never has 3+ consecutive
# single-letter "words" in a row, but letter-spaced titles commonly do.
_LETTER_SPACING_PATTERN = re.compile(r"(?:\b[A-Za-zÀ-ÿ]\s){2,}[A-Za-zÀ-ÿ]\b")

# Same idea for digit runs, applied separately so a letter-run and the price
# that follows it don't get fused together ("MAITAI 16" not "MAITAI16") -
# the space between the two classes of run is a real word boundary.
_DIGIT_SPACING_PATTERN = re.compile(r"(?:\b\d\s){1,}\d\b")

_MULTI_SPACE_PATTERN = re.compile(r"[ \t]{2,}")
_MULTI_NEWLINE_PATTERN = re.compile(r"\n{3,}")


def fix_letter_spacing(text: str) -> str:
    text = _LETTER_SPACING_PATTERN.sub(lambda m: m.group(0).replace(" ", ""), text)
    text = _DIGIT_SPACING_PATTERN.sub(lambda m: m.group(0).replace(" ", ""), text)
    return text


def normalize_whitespace(text: str) -> str:
    text = _MULTI_SPACE_PATTERN.sub(" ", text)
    text = _MULTI_NEWLINE_PATTERN.sub("\n\n", text)
    return text.strip()


def normalize_menu_text(text: str) -> str:
    """Full normalization pipeline applied before any parsing."""
    if not text:
        return ""
    text = fix_letter_spacing(text)
    text = normalize_whitespace(text)
    return text
