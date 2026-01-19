# Quick Start Guide

Get started with extracting credit report tables from PDFs in 5 minutes!

## 📋 What You'll Need

- Python 3.8 or later
- A PDF file containing "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
- 5 minutes of your time

## 🚀 Installation

### Option 1: Automatic (Recommended)

**On macOS/Linux:**
```bash
./install.sh
```

**On Windows:**
```batch
install.bat
```

### Option 2: Manual

```bash
pip install pdfplumber pandas openpyxl
```

## 📝 Basic Usage

### Step 1: Place Your PDF

Put your credit report PDF file in this directory, or note its path.

### Step 2: Run the Test

```bash
python test_extractor.py your_credit_report.pdf
```

This will:
- ✅ Check all dependencies
- ✅ Find tables in your PDF
- ✅ Extract the data
- ✅ Save results to CSV and JSON

### Step 3: Check the Output

You'll get:
- `test_output_table_1.csv` - Table data in CSV format
- `test_output_records.json` - Structured records in JSON format

## 📊 Example Code

### Extract to CSV (Simple)

```python
from pdf_table_extractor import CreditReportExtractor

# Create extractor
extractor = CreditReportExtractor("my_report.pdf")

# Extract tables
tables = extractor.extract_tables()

# Save first table
if tables:
    tables[0].to_csv("output.csv", index=False)
    print(f"✓ Saved {len(tables[0])} rows to output.csv")
```

### Extract to JSON (Detailed)

```python
from pdf_table_extractor import CreditReportExtractor
import json

# Create extractor
extractor = CreditReportExtractor("my_report.pdf")

# Extract with detailed parsing
records = extractor.extract_with_detailed_parsing()

# Save to JSON
with open("output.json", "w") as f:
    json.dump(records, f, indent=2)
print(f"✓ Saved {len(records)} records to output.json")
```

### Process Multiple PDFs

```python
from pdf_table_extractor import CreditReportExtractor
import pandas as pd

pdf_files = ["report1.pdf", "report2.pdf", "report3.pdf"]
all_data = []

for pdf in pdf_files:
    extractor = CreditReportExtractor(pdf)
    tables = extractor.extract_tables()
    all_data.extend(tables)

# Combine all
combined = pd.concat(all_data, ignore_index=True)
combined.to_csv("all_reports.csv", index=False)
print(f"✓ Combined {len(combined)} rows from {len(pdf_files)} PDFs")
```

## 🎯 Common Tasks

### Task 1: Extract All Banking Accounts

```bash
python example_usage.py
```

Edit `example_usage.py` and change `pdf_file = "credit_report.pdf"` to your file path.

### Task 2: Compare Different Extraction Methods

```bash
python alternative_extractors.py
```

This will try:
- pdfplumber (default)
- Camelot (if installed)
- Tabula (if installed)

And show you which works best for your PDF.

### Task 3: Batch Process a Folder

```python
import glob
from pdf_table_extractor import CreditReportExtractor
import pandas as pd

# Find all PDFs
pdfs = glob.glob("*.pdf")
all_tables = []

for pdf in pdfs:
    try:
        extractor = CreditReportExtractor(pdf)
        tables = extractor.extract_tables()
        all_tables.extend(tables)
        print(f"✓ {pdf}: {len(tables)} tables")
    except Exception as e:
        print(f"✗ {pdf}: {e}")

# Combine and save
if all_tables:
    result = pd.concat(all_tables, ignore_index=True)
    result.to_csv("batch_output.csv", index=False)
    print(f"\n✓ Total: {len(result)} rows saved to batch_output.csv")
```

## 🔧 Troubleshooting

### Problem: "No tables found"

**Solution 1:** Check if your PDF contains the exact text "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"

**Solution 2:** Try alternative extractors:
```python
from alternative_extractors import CamelotExtractor

extractor = CamelotExtractor("report.pdf")
tables = extractor.extract_tables()
```

**Solution 3:** The PDF might be image-based (scanned). You'll need OCR:
```bash
# Convert to text-based PDF first using OCR tools like Tesseract
```

### Problem: "Module not found"

```bash
# Reinstall dependencies
pip install --upgrade pdfplumber pandas openpyxl
```

### Problem: Table structure is wrong

Use detailed parsing instead:
```python
extractor = CreditReportExtractor("report.pdf")
records = extractor.extract_with_detailed_parsing()
```

### Problem: Missing columns

The PDF table might have merged cells. Try:
1. Use `extract_with_detailed_parsing()` method
2. Try the Camelot extractor (better for complex tables)
3. Manually adjust `table_settings` in the code

## 📚 File Overview

| File | Purpose |
|------|---------|
| `pdf_table_extractor.py` | Main extraction class (pdfplumber-based) |
| `example_usage.py` | Usage examples and templates |
| `alternative_extractors.py` | Camelot, Tabula, PDFMiner methods |
| `test_extractor.py` | Test and verify your setup |
| `requirements.txt` | Python dependencies |
| `install.sh` / `install.bat` | Installation scripts |

## 🎓 Next Steps

1. **Read the full README.md** for detailed documentation
2. **Customize the extractor** for your specific PDF format
3. **Integrate with your workflow** - import into databases, Excel, etc.

## 💡 Tips

- **For best results:** Use text-based PDFs (not scanned images)
- **For speed:** Use `extract_tables()` for simple structures
- **For accuracy:** Use `extract_with_detailed_parsing()` for complex tables
- **For large batches:** Process PDFs in parallel with multiprocessing

## 🆘 Need Help?

1. Run the test script: `python test_extractor.py your_file.pdf`
2. Check if dependencies are installed: `pip list | grep -E "pdfplumber|pandas"`
3. Try alternative extractors if one doesn't work
4. Review the troubleshooting section in README.md

## ✨ Success Indicators

You're ready when you see:

```
✓ pdfplumber installed
✓ pandas installed
✓ File found: 1234567 bytes
✓ Success! Found 1 table(s)
  Table 1:
    Rows: 15
    Columns: 14
    ✓ Saved to: test_output_table_1.csv
```

Happy extracting! 🎉
