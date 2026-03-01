# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

block_cipher = None

# Collect all pdfplumber data and binaries
datas_pdfplumber, binaries_pdfplumber, hiddenimports_pdfplumber = collect_all('pdfplumber')

a = Analysis(
    ['insert_excel_file.py'],
    pathex=[],
    binaries=binaries_pdfplumber,
    datas=[
        ('Knockout Matrix Template.xlsx', '.'),
    ] + datas_pdfplumber,
    hiddenimports=[
        'openpyxl',
        'pdfplumber',
        'pdfplumber.pdf',
        'pdfplumber.page',
        'pdfplumber.table',
        'pdfplumber.utils',
        'PIL',
        'PIL.Image',
        'pypdf',
        'pypdf._reader',
        'pypdf._writer',
        'pypdf.generic',
        'pypdf.constants',
        'pypdf.errors',
        'pypdf.pdf',
        'pypdf.utils',
        'pypdf._encryption',
        'pypdf._page',
        'pypdf._merger',
        'tkinter',
        'tkinter.filedialog',
        'merged_credit_report',
        'pdf_utils',
        'Detailed_Credit_Report_Extractor',
        'Non_Bank_Lender_Credit_Information',
        'load_file_version',
    ] + hiddenimports_pdfplumber,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='AIgent_Credit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep True to see errors - change to False after testing
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
