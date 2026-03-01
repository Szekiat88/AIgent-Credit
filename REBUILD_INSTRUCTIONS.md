# Rebuild Instructions - Fix pdfplumber Error

## The Problem
You're getting: `ModuleNotFoundError: No module named 'pdfplumber'`

This happens because PyInstaller doesn't automatically bundle all of pdfplumber's dependencies.

## Solution: Rebuild with Updated Spec File

The spec file has been updated to properly collect all pdfplumber modules. Follow these steps:

### Step 1: Clean Previous Build
```cmd
rmdir /s /q build dist
del AIgent_Credit.spec
```

### Step 2: Rebuild with Updated Spec
```cmd
pip install -r requirements.txt
pyinstaller --onefile --name "AIgent_Credit" --collect-all pdfplumber insert_excel_file.py
```

**OR** if you want to use the spec file approach:

```cmd
# First, regenerate the spec file with collect-all
pyinstaller --onefile --name "AIgent_Credit" --collect-all pdfplumber --specpath . insert_excel_file.py

# Then rebuild using the spec
pyinstaller AIgent_Credit.spec --clean
```

### Step 3: Test the EXE
```cmd
cd dist
AIgent_Credit.exe
```

## Alternative: Quick Fix Command

If the above doesn't work, try this comprehensive build command:

```cmd
pip install --upgrade pdfplumber pyinstaller
pyinstaller --onefile ^
    --name "AIgent_Credit" ^
    --collect-all pdfplumber ^
    --collect-all pypdf ^
    --collect-all PIL ^
    --hidden-import pdfplumber ^
    --hidden-import pypdf ^
    --hidden-import PIL ^
    insert_excel_file.py
```

## What Changed

The spec file now:
1. Uses `collect_all('pdfplumber')` to gather all pdfplumber dependencies
2. Includes pdfplumber's data files and binaries
3. Adds all pdfplumber submodules to hiddenimports

This ensures pdfplumber and all its dependencies are properly bundled.
