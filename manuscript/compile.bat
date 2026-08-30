@echo off
setlocal
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
if errorlevel 1 exit /b 1
pushd supplementary
latexmk -pdf -interaction=nonstopmode -halt-on-error -outdir=../output supplementary_information.tex
if errorlevel 1 exit /b 1
popd
copy /Y output\main.pdf output\Taxila_CHIP_Manuscript.pdf >nul
copy /Y output\supplementary_information.pdf output\Taxila_CHIP_Supplementary_Information.pdf >nul
echo Compilation complete. PDFs are in output\.
endlocal
