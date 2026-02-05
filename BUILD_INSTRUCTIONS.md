# Building EXE for Windows

This guide will help you convert the Python application to a Windows EXE file.

## Prerequisites

1. **Python 3.8+** installed on Windows
2. **pip** (usually comes with Python)

## Quick Start - Build Command

Open **Command Prompt** or **PowerShell** in this directory and run:

```bash
# Step 1: Install dependencies
pip install -r requirements.txt

# Step 2: Build EXE (Console mode - shows output, recommended for debugging)
pyinstaller --onefile --name "AIgent_Credit" insert_excel_file.py
```

**OR** using the spec file (recommended):

```bash
pip install -r requirements.txt
pyinstaller AIgent_Credit.spec --clean
```

After building, find your EXE at: `dist\AIgent_Credit.exe`

**Note**: The code has been fixed to work properly with PyInstaller EXEs. The EXE will look for `Knockout Matrix Template.xlsx` in the same directory as the EXE file.

## Important Notes

### Excel Template Location

The EXE will automatically find `Knockout Matrix Template.xlsx` by checking:
1. PyInstaller temp directory (if bundled)
2. Same directory as the EXE (recommended)
3. Current working directory

**For Distribution**: Copy `Knockout Matrix Template.xlsx` to the same folder as the EXE. See `DISTRIBUTION_GUIDE.md` for complete distribution instructions.

### Distribution

When distributing the EXE to others:

1. **Copy the EXE**: `dist\AIgent_Credit.exe`
2. **Copy the Excel template**: `Knockout Matrix Template.xlsx` (place in same folder as EXE)
3. **Test on a clean Windows machine** without Python installed

### Troubleshooting

**If the EXE doesn't work, see `TROUBLESHOOTING.md` for detailed solutions.**

Common issues:

#### EXE doesn't run / crashes
- Run from Command Prompt to see error messages: `AIgent_Credit.exe`
- Make sure `Knockout Matrix Template.xlsx` is in the same folder as the EXE
- Rebuild with: `pyinstaller AIgent_Credit.spec --clean`

#### "Module not found" errors
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Rebuild with `--clean` flag: `pyinstaller AIgent_Credit.spec --clean`

#### EXE is too large
- This is normal - PyInstaller bundles Python and all dependencies
- Typical size: 50-100 MB

#### EXE doesn't find Excel template
- Ensure `Knockout Matrix Template.xlsx` is in the same directory as the EXE
- Or use the `--excel` command line argument: `AIgent_Credit.exe --excel "path\to\template.xlsx"`

## Command Line Options

The EXE supports the same arguments as the Python script:

```bash
# Run with file picker (default)
AIgent_Credit.exe

# Use specific PDF
AIgent_Credit.exe --pdf "report.pdf"

# Use pre-generated merged JSON
AIgent_Credit.exe --merged-json merged.json

# Specify Excel template
AIgent_Credit.exe --excel "template.xlsx"

# Specify issuer name
AIgent_Credit.exe --issuer "Company Name"
```

## File Structure After Build

```
AIgent Credit/
├── dist/
│   └── AIgent_Credit.exe          ← Your EXE file
├── build/                          ← Temporary build files (can delete)
├── AIgent_Credit.spec              ← PyInstaller spec file
├── Knockout Matrix Template.xlsx   ← Copy this with the EXE
└── ... (other source files)
```

## Advanced: Customizing the Build

Edit `AIgent_Credit.spec` to customize:
- **console=True/False**: Show/hide console window
- **upx=True/False**: Compress EXE (requires UPX tool)
- **icon**: Add custom icon file
- **datas**: Include additional data files

Then rebuild with: `pyinstaller AIgent_Credit.spec`
