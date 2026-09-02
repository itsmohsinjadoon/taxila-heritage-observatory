"""Build the canonical manuscript PDF from the approved archival map render."""

from __future__ import annotations

import argparse
import hashlib
from pathlib import Path

from PIL import Image
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas


SOURCE_ROOT = Path(__file__).resolve().parent
ARCHIVE = SOURCE_ROOT / "archive" / "Taxila_Figure1_author_approved_original_180dpi.png"
DEFAULT_OUTPUT = SOURCE_ROOT.parents[1] / "main" / "figure_01_study_area_context_map.pdf"
EXPECTED_SHA256 = "ffb87ca7a17fc5cd283a7058b419fbe55ee08dfa736ff0c19468abfb34c16c22"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(output: Path) -> None:
    if sha256(ARCHIVE) != EXPECTED_SHA256:
        raise RuntimeError("The archived approved render failed its SHA-256 check")

    with Image.open(ARCHIVE) as image:
        if image.size != (1843, 1240) or image.mode != "RGB":
            raise RuntimeError(f"Unexpected archival render: size={image.size}, mode={image.mode}")

    output.parent.mkdir(parents=True, exist_ok=True)
    width_points = 260 / 25.4 * 72
    height_points = 175 / 25.4 * 72
    pdf = Canvas(
        str(output),
        pagesize=(width_points, height_points),
        pageCompression=1,
        pdfVersion=(1, 7),
        invariant=1,
    )
    pdf.setTitle("Taxila Figure 1 — author-approved original cartography")
    pdf.setAuthor("Taxila Heritage Observatory")
    pdf.setSubject("Study-area context and analytical neighbourhoods")
    pdf.drawImage(
        ImageReader(str(ARCHIVE)),
        0,
        0,
        width=width_points,
        height=height_points,
        preserveAspectRatio=False,
        mask="auto",
    )
    pdf.showPage()
    pdf.save()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    build(args.output.resolve())


if __name__ == "__main__":
    main()
