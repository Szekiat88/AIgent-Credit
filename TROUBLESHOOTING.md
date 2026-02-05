# Troubleshooting EXE Issues on Windows

## Common Issues and Solutions

### Issue 1: EXE Doesn't Run / Crashes Immediately

**Solution**: The EXE is built with `console=True` to show errors. Run it from Command Prompt to see the error message:

```cmd
cd "C:\path\to\your\exe\folder"
AIgent_Credit.exe
```

This will show you the exact error message.

### Issue 2: "Excel template not found"

**Problem**: The EXE can't find `Knockout Matrix Template.xlsx`

**Solution**: 
1. Copy `Knockout Matrix Template.xlsx` to the **same folder** as `AIgent_Credit.exe`
2. OR use the `--excel` argument:
   ```cmd
   AIgent_Credit.exe --excel "C:\full\path\to\Knockout Matrix Template.xlsx"
   ```

### Issue 3: "Module not found" or Import Errors

**Problem**: PyInstaller didn't include all modules

**Solution**: Rebuild with the spec file:
```cmd
pip install -r requirements.txt
pyinstaller AIgent_Credit.spec --clean
```

The `--clean` flag removes old build files.

### Issue 4: File Picker Doesn't Open

**Problem**: tkinter might not be working in the EXE

**Solution**: 
1. Make sure you're running on Windows (tkinter should work)
2. Try running from Command Prompt to see errors
3. Rebuild with explicit tkinter imports (already in spec file)

### Issue 5: EXE Runs But No Output

**Problem**: If you built with `--windowed`, you won't see console output

**Solution**: 
1. Rebuild with `console=True` (already set in spec file)
2. OR run from Command Prompt to see output

### Issue 6: "Permission Denied" or Antivirus Blocks EXE

**Problem**: Some antivirus software blocks PyInstaller EXEs

**Solution**:
1. Add exception in your antivirus
2. PyInstaller EXEs are often flagged as false positives
3. You may need to sign the EXE (requires code signing certificate)

## Debug Steps

1. **Run from Command Prompt** to see error messages:
   ```cmd
   cd "C:\path\to\exe"
   AIgent_Credit.exe
   ```

2. **Check if Excel template exists**:
   ```cmd
   dir "Knockout Matrix Template.xlsx"
   ```

3. **Test with explicit paths**:
   ```cmd
   AIgent_Credit.exe --pdf "C:\full\path\to\report.pdf" --excel "C:\full\path\to\template.xlsx"
   ```

4. **Rebuild with debug info**:
   ```cmd
   pyinstaller --onefile --name "AIgent_Credit" --debug=all insert_excel_file.py
   ```

## Rebuilding the EXE

If you need to rebuild:

```cmd
# Clean old build
rmdir /s /q build dist
del AIgent_Credit.spec

# Rebuild
pip install -r requirements.txt
pyinstaller --onefile --name "AIgent_Credit" insert_excel_file.py
```

Or use the spec file:
```cmd
pyinstaller AIgent_Credit.spec --clean
```

## Getting Help

If the EXE still doesn't work:

1. Run from Command Prompt and copy the **full error message**
2. Check that all files are in the same folder:
   - `AIgent_Credit.exe`
   - `Knockout Matrix Template.xlsx`
3. Try running the Python script directly to verify it works:
   ```cmd
   python insert_excel_file.py
   ```
