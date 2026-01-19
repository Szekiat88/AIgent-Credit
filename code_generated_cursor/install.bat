@echo off
REM Installation script for Credit Report PDF Table Extractor (Windows)

echo ==============================================================================
echo   Credit Report PDF Table Extractor - Installation Script (Windows)
echo ==============================================================================
echo.

REM Check if Python is installed
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python is not installed or not in PATH.
    echo Please install Python 3.8 or later from https://www.python.org/
    pause
    exit /b 1
)

echo [OK] Python found
python --version
echo.

REM Check if pip is installed
pip --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] pip is not installed or not in PATH.
    pause
    exit /b 1
)

echo [OK] pip found
pip --version
echo.

echo Select installation type:
echo   1) Basic (pdfplumber only - recommended)
echo   2) Full (all extraction libraries)
echo.
set /p choice="Enter choice [1-2]: "

if "%choice%"=="1" goto basic
if "%choice%"=="2" goto full
echo Invalid choice. Exiting.
pause
exit /b 1

:basic
echo.
echo Installing basic dependencies...
echo ------------------------------------------------------------------------------
pip install pdfplumber pandas openpyxl

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed. Please check the error messages above.
    pause
    exit /b 1
)

echo.
echo [OK] Basic installation complete!
echo.
echo You can now use:
echo   - pdf_table_extractor.py
echo   - example_usage.py
echo.
echo To test: python test_extractor.py your_file.pdf
goto end

:full
echo.
echo Full installation includes additional extraction libraries.
echo.
echo IMPORTANT: You need to install these system dependencies manually:
echo   1. Ghostscript - Download from: https://www.ghostscript.com/
echo   2. Java Runtime - Download from: https://www.java.com/
echo.
echo Press any key to continue after installing the above, or Ctrl+C to cancel...
pause
echo.

echo Installing Python packages...
echo ------------------------------------------------------------------------------
pip install pdfplumber pandas openpyxl
pip install "camelot-py[cv]"
pip install tabula-py
pip install pdfminer.six

if errorlevel 1 (
    echo.
    echo [ERROR] Installation failed. Please check the error messages above.
    echo.
    echo Common issues:
    echo   - Camelot requires Ghostscript to be installed
    echo   - Tabula requires Java Runtime Environment
    pause
    exit /b 1
)

echo.
echo [OK] Full installation complete!
echo.
echo You can now use:
echo   - pdf_table_extractor.py (pdfplumber)
echo   - alternative_extractors.py (Camelot, Tabula)
echo   - example_usage.py
echo.
echo To test: python test_extractor.py your_file.pdf

:end
echo.
echo ==============================================================================
echo Next steps:
echo   1. Place your PDF file in this directory
echo   2. Run: python test_extractor.py
echo   3. Or: python example_usage.py
echo ==============================================================================
echo.
pause
