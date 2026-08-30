#!/usr/bin/env bash
set -euo pipefail

latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
(
  cd supplementary
  latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=../output supplementary_information.tex
)
cp output/main.pdf output/Taxila_CHIP_Manuscript.pdf
cp output/supplementary_information.pdf output/Taxila_CHIP_Supplementary_Information.pdf
echo "Compilation complete. PDFs are in output/."
