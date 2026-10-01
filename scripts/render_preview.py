"""Render all slides using PowerPoint COM or LibreOffice PDF + PyMuPDF.

No approximate fallback. Each run uses a clean temporary directory. Rendered
previews include a SHA-256 receipt so an old montage cannot represent a new deck.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFont


def export_slides(pptx_path, output_dir):
    source = Path(pptx_path).resolve()
    dest = Path(output_dir).resolve()
    dest.mkdir(parents=True, exist_ok=True)
    backend = None
    with tempfile.TemporaryDirectory(prefix="songstudy-render-") as temp:
        temp = Path(temp)
        copied = temp / "deck.pptx"
        shutil.copy2(source, copied)
        com_error = None
        images = []
        if os.name == "nt":
            try:
                import win32com.client
                app = win32com.client.DispatchEx("PowerPoint.Application")
                pres = None
                try:
                    pres = app.Presentations.Open(str(copied), True, False, False)
                    for i in range(1, pres.Slides.Count+1):
                        target = temp / f"slide_{i:03}.png"
                        pres.Slides.Item(i).Export(str(target), "PNG", 1600, 900)
                        images.append(target)
                    backend = "PowerPoint COM"
                finally:
                    if pres is not None:pres.Close()
                    app.Quit()
            except Exception as exc:
                com_error = str(exc)
                images = []
        if not images:
            exe = shutil.which("soffice") or shutil.which("libreoffice")
            if not exe:
                raise RuntimeError(f"No slide renderer available. PowerPoint error: {com_error}")
            profile = (temp / "lo-profile").as_uri()
            result = subprocess.run([exe, f"-env:UserInstallation={profile}", "--headless", "--convert-to", "pdf", "--outdir", str(temp), str(copied)], capture_output=True, text=True, timeout=180)
            pdf = temp / "deck.pdf"
            if result.returncode or not pdf.exists():
                raise RuntimeError(f"LibreOffice export failed: {result.stdout} {result.stderr}")
            import fitz
            with fitz.open(pdf) as doc:
                for i, page in enumerate(doc, 1):
                    target = temp / f"slide_{i:03}.png"
                    page.get_pixmap(matrix=fitz.Matrix(1600/page.rect.width,1600/page.rect.width)).save(target)
                    images.append(target)
            shutil.copy2(pdf, dest / "deck.pdf")
            backend = "LibreOffice PDF + PyMuPDF"
        from pptx import Presentation
        expected = len(Presentation(source).slides)
        if len(images) != expected:raise RuntimeError(f"Rendered {len(images)} of {expected} slides")
        # Delete only files owned by this renderer after a successful new export.
        for old in dest.glob("slide_*.png"):old.unlink()
        paths = []
        for image in images:
            target = dest / image.name
            shutil.copy2(image, target)
            paths.append(str(target))
        if backend == "PowerPoint COM":
            # COM exports PNG only; never leave a PDF from an older LO run.
            (dest / "deck.pdf").unlink(missing_ok=True)
    receipt = {"source": source.name, "pptx_sha256":hashlib.sha256(source.read_bytes()).hexdigest(),
               "images":{Path(p).name:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
               "backend":backend, "slide_count":expected, "render_status":"completed",
               "visual_status":"not_reviewed"}
    (dest / "render_receipt.json").write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding="utf8")
    return paths, receipt


def contact_sheet(paths, output, labels=None, cell_w=480, columns=3):
    rows=(len(paths)+columns-1)//columns
    cell_h=round(cell_w*9/16)
    pad,bar=14,26
    sheet=Image.new("RGB",(columns*cell_w+(columns+1)*pad,rows*(cell_h+bar)+(rows+1)*pad),(229,231,235))
    draw=ImageDraw.Draw(sheet)
    for i,path in enumerate(paths):
        x=pad+(i%columns)*(cell_w+pad);y=pad+(i//columns)*(cell_h+bar+pad)
        with Image.open(path) as im:sheet.paste(im.convert("RGB").resize((cell_w,cell_h),Image.Resampling.LANCZOS),(x,y))
        draw.text((x,y+cell_h+6), labels[i] if labels and i<len(labels) else f"{i+1:02d}",fill=(40,48,65))
    Path(output).parent.mkdir(parents=True,exist_ok=True)
    sheet.save(output)


def generate_montage(pptx_path, out_png, labels=None, cell_w=480):
    output=Path(out_png)
    paths, receipt=export_slides(pptx_path,output.parent/(output.stem+"_slides"))
    contact_sheet(paths,output,labels,cell_w)
    print(f"Rendered {receipt['slide_count']} slides using {receipt['backend']}: {output}")
    return receipt


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("pptx")
    parser.add_argument("--output",required=True,help="Montage PNG path; individual slides and PDF saved beside it")
    args=parser.parse_args()
    generate_montage(args.pptx,args.output)
