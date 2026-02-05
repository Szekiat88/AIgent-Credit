# Distribution Guide - How to Share the EXE with Others

## What to Include When Distributing

When you share the EXE with other people, you need to include:

### Required Files:
1. **`AIgent_Credit.exe`** - The main executable
2. **`Knockout Matrix Template.xlsx`** - The Excel template file

### How to Package for Distribution

#### Option 1: Simple Folder (Recommended)
1. Create a folder named `AIgent_Credit`
2. Copy both files into this folder:
   - `AIgent_Credit.exe`
   - `Knockout Matrix Template.xlsx`
3. Zip the folder and share it

**Folder structure:**
```
AIgent_Credit/
├── AIgent_Credit.exe
└── Knockout Matrix Template.xlsx
```

#### Option 2: Include Instructions
Create a README.txt in the folder with:
```
AIgent Credit - User Instructions
================================

1. Extract all files to a folder
2. Double-click AIgent_Credit.exe
3. Select your PDF file when prompted
4. The filled Excel file will be created in the same folder

Note: Keep both files (EXE and Excel template) in the same folder.
```

## How the EXE Finds the Excel Template

The EXE will automatically look for `Knockout Matrix Template.xlsx` in this order:

1. **Same folder as the EXE** (most common)
2. **Current working directory** (where you run the EXE from)
3. **PyInstaller temp directory** (if bundled with EXE)

### Best Practice
**Always place the Excel template in the same folder as the EXE.** This is the most reliable method.

## Building the EXE for Distribution

### Step 1: Build the EXE
```cmd
pip install -r requirements.txt
pyinstaller AIgent_Credit.spec --clean
```

### Step 2: Prepare Distribution Folder
```cmd
mkdir AIgent_Credit_Distribution
copy dist\AIgent_Credit.exe AIgent_Credit_Distribution\
copy "Knockout Matrix Template.xlsx" AIgent_Credit_Distribution\
```

### Step 3: Test Before Distributing
1. Copy the folder to a different location (or different computer)
2. Run the EXE from there
3. Make sure it can find and use the Excel template

## Alternative: Bundle Excel Template in EXE

The Excel template is already configured to be bundled in the EXE (see `AIgent_Credit.spec` line 10). However, PyInstaller extracts it to a temporary directory at runtime.

The code automatically finds it, but for maximum compatibility, **it's still recommended to include the Excel file alongside the EXE**.

## Troubleshooting for End Users

If users report "Excel template not found":

1. **Check file location**: Ensure `Knockout Matrix Template.xlsx` is in the same folder as `AIgent_Credit.exe`

2. **Check file name**: The file must be named exactly: `Knockout Matrix Template.xlsx` (case-sensitive on some systems)

3. **Use explicit path**: Users can specify the Excel file path:
   ```cmd
   AIgent_Credit.exe --excel "C:\full\path\to\Knockout Matrix Template.xlsx"
   ```

4. **Check permissions**: Make sure the user has read permissions for the Excel file

## Creating an Installer (Advanced)

For professional distribution, you can create an installer using:
- **Inno Setup** (free, Windows)
- **NSIS** (free, cross-platform)
- **WiX Toolset** (free, Windows)

These will create a proper installer that places files in the correct locations.
