#!/usr/bin/env python3
"""Render a .docx to PDF (Word COM) then page PNGs (PyMuPDF) for visual acceptance.

Word COM is the same faithful path the PPTX preview uses (PowerPoint COM);
LibreOffice is not installed in this environment. Every page is rendered and
kept, so the page count and representative pages are reproducible evidence.
"""

import os
import sys

sys.stdout.reconfigure(encoding="utf-8")


def export_pdf_via_word(docx_path, pdf_path):
    import win32com.client
    word = win32com.client.Dispatch("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(os.path.abspath(docx_path), ReadOnly=True)
        # 17 = wdExportFormatPDF
        doc.ExportAsFixedFormat(OutputFileName=os.path.abspath(pdf_path),
                                ExportFormat=17)
        doc.Close(False)
    finally:
        word.Quit()
    return os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0


def render_pages(pdf_path, out_dir, prefix="page"):
    import fitz
    os.makedirs(out_dir, exist_ok=True)
    doc = fitz.open(pdf_path)
    n = doc.page_count
    paths = []
    for i in range(n):
        pix = doc[i].get_pixmap(dpi=110)
        p = os.path.join(out_dir, f"{prefix}_{i + 1:02d}.png")
        pix.save(p)
        paths.append(p)
    doc.close()
    return n, paths


def main(argv):
    if not argv:
        print("Usage: python scripts/render_docx.py <file.docx> [out_dir]")
        return 1
    docx_path = argv[0]
    out_dir = argv[1] if len(argv) > 1 else os.path.join(
        os.path.dirname(docx_path), "_preview_docx")
    base = os.path.splitext(os.path.basename(docx_path))[0]
    os.makedirs(out_dir, exist_ok=True)
    pdf_path = os.path.join(out_dir, base + ".pdf")
    if not export_pdf_via_word(docx_path, pdf_path):
        print("FAIL: Word PDF export failed")
        return 1
    n, paths = render_pages(pdf_path, out_dir)
    print(f"OK: {n} pages ({os.path.getsize(pdf_path)} bytes pdf) -> {out_dir}")
    for p in paths:
        print("  " + p)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
