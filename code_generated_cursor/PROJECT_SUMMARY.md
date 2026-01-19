# Project Summary: Credit Report PDF Table Extractor

## 🎯 Project Overview

A comprehensive Python toolkit for extracting "DETAILED CREDIT REPORT (BANKING ACCOUNTS)" tables from PDF documents. This solution provides multiple extraction methods, handles complex table structures, and exports to various formats.

## 📦 What's Included

### Core Files

1. **pdf_table_extractor.py** (Main Module)
   - `CreditReportExtractor` class
   - Two extraction methods:
     - `extract_tables()` - Simple DataFrame extraction
     - `extract_with_detailed_parsing()` - Complex record parsing
   - Handles merged cells and multi-row records
   - Automatic table detection

2. **example_usage.py** (Usage Examples)
   - Single PDF processing
   - Batch processing multiple PDFs
   - Different export formats (CSV, Excel, JSON)
   - Ready-to-use templates

3. **alternative_extractors.py** (Alternative Methods)
   - `CamelotExtractor` - For tables with clear borders
   - `TabulaExtractor` - Java-based robust extraction
   - `PDFMinerExtractor` - Low-level text extraction
   - Comparison utility

4. **test_extractor.py** (Testing & Validation)
   - Interactive testing tool
   - Dependency checker
   - Automatic PDF detection
   - Debug information

### Documentation

5. **README.md** - Complete documentation with:
   - Features overview
   - Installation instructions
   - Detailed usage examples
   - Troubleshooting guide
   - API reference

6. **QUICKSTART.md** - 5-minute quick start guide:
   - Fast installation
   - Basic examples
   - Common tasks
   - Quick troubleshooting

### Installation

7. **requirements.txt** - Python package dependencies
8. **install.sh** - Automated installer for macOS/Linux
9. **install.bat** - Automated installer for Windows

## 🔑 Key Features

### Multiple Extraction Methods

| Method | Best For | Library |
|--------|----------|---------|
| pdfplumber (default) | General purpose, good balance | pdfplumber |
| Camelot | Tables with visible borders | camelot-py |
| Tabula | Complex PDFs, very robust | tabula-py |

### Flexible Output Formats

- **CSV** - For Excel and data analysis
- **Excel (XLSX)** - Formatted spreadsheets
- **JSON** - For nested structures and databases
- **Pandas DataFrame** - For Python analysis

### Smart Table Detection

- Automatically finds tables by title
- Validates table structure
- Handles multi-page PDFs
- Processes merged cells

## 🚀 Quick Start

### 1. Install

```bash
# Automatic
./install.sh  # macOS/Linux
install.bat   # Windows

# Manual
pip install -r requirements.txt
```

### 2. Test

```bash
python test_extractor.py your_report.pdf
```

### 3. Use

```python
from pdf_table_extractor import CreditReportExtractor

extractor = CreditReportExtractor("report.pdf")
tables = extractor.extract_tables()
tables[0].to_csv("output.csv")
```

## 📊 Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     PDF Document Input                       │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Credit Report Extractor (Main)                  │
│                                                               │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  1. Find Table by Title                             │    │
│  │     "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"     │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  2. Extract Table Structure                         │    │
│  │     • Identify headers                              │    │
│  │     • Parse rows                                    │    │
│  │     • Handle merged cells                           │    │
│  └─────────────────────────────────────────────────────┘    │
│                      │                                       │
│                      ▼                                       │
│  ┌─────────────────────────────────────────────────────┐    │
│  │  3. Parse Records                                   │    │
│  │     • Banking account details                       │    │
│  │     • Facility information                          │    │
│  │     • Payment history                               │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                    Output Formats                            │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │   CSV    │  │  Excel   │  │   JSON   │  │DataFrame │   │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘   │
└─────────────────────────────────────────────────────────────┘

Alternative Extractors (if main fails):
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│   Camelot    │  │    Tabula    │  │   PDFMiner   │
│  (borders)   │  │   (robust)   │  │  (low-level) │
└──────────────┘  └──────────────┘  └──────────────┘
```

## 💻 Usage Patterns

### Pattern 1: Single File, Quick Extract

```python
from pdf_table_extractor import CreditReportExtractor

extractor = CreditReportExtractor("report.pdf")
df = extractor.extract_tables()[0]
df.to_csv("output.csv")
```

### Pattern 2: Detailed Parsing

```python
from pdf_table_extractor import CreditReportExtractor
import json

extractor = CreditReportExtractor("report.pdf")
records = extractor.extract_with_detailed_parsing()

with open("records.json", "w") as f:
    json.dump(records, f, indent=2)
```

### Pattern 3: Batch Processing

```python
from pdf_table_extractor import CreditReportExtractor
import pandas as pd

pdfs = ["r1.pdf", "r2.pdf", "r3.pdf"]
all_data = []

for pdf in pdfs:
    ext = CreditReportExtractor(pdf)
    all_data.extend(ext.extract_tables())

pd.concat(all_data).to_csv("combined.csv")
```

### Pattern 4: Try Multiple Methods

```python
from pdf_table_extractor import CreditReportExtractor
from alternative_extractors import CamelotExtractor, TabulaExtractor

pdf = "report.pdf"

# Try pdfplumber
try:
    tables = CreditReportExtractor(pdf).extract_tables()
    if tables: print(f"✓ pdfplumber: {len(tables)} tables")
except: pass

# Try Camelot
try:
    tables = CamelotExtractor(pdf).extract_tables()
    if tables: print(f"✓ Camelot: {len(tables)} tables")
except: pass

# Try Tabula
try:
    tables = TabulaExtractor(pdf).extract_tables()
    if tables: print(f"✓ Tabula: {len(tables)} tables")
except: pass
```

## 📋 Table Structure

The extractor is designed for tables with this structure:

| Column | Type | Description |
|--------|------|-------------|
| No | Integer | Record number |
| Date | Date | Account opening date |
| Status | String | Account status code |
| Capacity | String | Account capacity |
| Lender Type | String | CB, IB, etc. |
| Facility | String | Facility type |
| Total Outstanding Balance | Decimal | Current balance (RM) |
| Date Balance Updated | Date | Last update date |
| Limit/Inst Amt | Decimal | Credit limit (RM) |
| Prin Repymt Term | String | Repayment term |
| Col Type | String | Collateral type |
| Conduct of Account | Array | 12-month history |
| Legal Status | String | Legal status |
| Date Status Update | Date | Status update date |

## 🔧 Configuration & Customization

### Adjust Table Detection

```python
# In pdf_table_extractor.py, modify table_settings:
table_settings = {
    "vertical_strategy": "lines",      # or "text"
    "horizontal_strategy": "lines",    # or "text"
    "intersection_tolerance": 5,       # pixels
    "min_words_vertical": 3,
    "snap_tolerance": 3,
}
```

### Customize Title Search

```python
# Change the target title
extractor = CreditReportExtractor("report.pdf")
extractor.target_title = "YOUR CUSTOM TABLE TITLE"
```

### Filter Specific Pages

```python
# For alternative extractors
camelot = CamelotExtractor("report.pdf")
tables = camelot.extract_tables(pages="1,3,5")  # Only pages 1, 3, 5
```

## 🧪 Testing Checklist

- [ ] Install dependencies: `pip install -r requirements.txt`
- [ ] Run test script: `python test_extractor.py sample.pdf`
- [ ] Verify CSV output exists and contains data
- [ ] Check JSON output structure
- [ ] Test with multiple PDFs
- [ ] Try alternative extractors if needed

## 📈 Performance Tips

1. **For large PDFs:** Process specific pages only
2. **For batch jobs:** Use multiprocessing
3. **For complex tables:** Use detailed parsing mode
4. **For speed:** Use simple `extract_tables()` method

## 🐛 Common Issues & Solutions

| Issue | Solution |
|-------|----------|
| No tables found | Check PDF contains target title text |
| Malformed output | Use `extract_with_detailed_parsing()` |
| Missing dependencies | Run `pip install -r requirements.txt` |
| Camelot fails | Install ghostscript: `brew install ghostscript` |
| Tabula fails | Install Java: `brew install openjdk` |
| Image-based PDF | Use OCR preprocessing |

## 📦 Dependencies

### Required (Basic)
- `pdfplumber` - Main extraction library
- `pandas` - Data manipulation
- `openpyxl` - Excel export

### Optional (Advanced)
- `camelot-py[cv]` - Complex table extraction
- `tabula-py` - Java-based extraction
- `pdfminer.six` - Low-level PDF parsing

### System (for Optional)
- Ghostscript (for Camelot)
- Java Runtime (for Tabula)

## 🎓 Learning Path

1. **Start:** Run `python test_extractor.py your.pdf`
2. **Learn:** Read `example_usage.py` for patterns
3. **Explore:** Try `alternative_extractors.py` for different methods
4. **Customize:** Modify `pdf_table_extractor.py` for your needs
5. **Deploy:** Integrate into your workflow

## 🚀 Deployment Options

### Standalone Script
```bash
python pdf_table_extractor.py
```

### Module Import
```python
from pdf_table_extractor import CreditReportExtractor
```

### Web Service
```python
# Flask example
from flask import Flask, request, jsonify
from pdf_table_extractor import CreditReportExtractor

app = Flask(__name__)

@app.route('/extract', methods=['POST'])
def extract():
    file = request.files['pdf']
    extractor = CreditReportExtractor(file)
    tables = extractor.extract_tables()
    return jsonify(tables[0].to_dict())
```

### Scheduled Job
```bash
# Crontab example - run daily at 2am
0 2 * * * cd /path/to/project && python example_usage.py
```

## 📊 Output Examples

### CSV Output
```csv
No,Date,Status,Capacity,Lender_Type,Facility,Total_Outstanding_Balance,...
1,23/11/2017,O,OWN,CB,OTLNFNCE,152056.00,...
2,06/04/2018,O,OWN,CB,PCPASCAR,35202.00,...
```

### JSON Output
```json
[
  {
    "No": "1",
    "Date": "23/11/2017",
    "Status": "O",
    "Capacity": "OWN",
    "Lender_Type": "CB",
    "Facility": "OTLNFNCE",
    "Total_Outstanding_Balance": "152056.00",
    ...
  }
]
```

## 🎉 Success Criteria

Your extraction is successful when:
- ✅ All required columns are present
- ✅ Row count matches the PDF
- ✅ Data types are correct (numbers, dates, text)
- ✅ No missing or corrupted data
- ✅ Output files are created successfully

## 📞 Support Resources

- **Quick issues:** Check `QUICKSTART.md`
- **Detailed help:** Read `README.md`
- **Code examples:** See `example_usage.py`
- **Testing:** Use `test_extractor.py`
- **Alternatives:** Try `alternative_extractors.py`

## 🔮 Future Enhancements

Potential improvements:
- OCR support for scanned PDFs
- GUI interface
- Web dashboard
- Database integration
- Multi-format support (Word, HTML)
- Advanced data validation
- Machine learning-based extraction

## 📝 License & Usage

This toolkit is provided as-is for extracting credit report data from PDFs. Use responsibly and ensure compliance with data privacy regulations when handling sensitive financial information.

---

**Created:** 2026-01-19  
**Version:** 1.0  
**Maintained by:** AIgent Credit Team

Happy extracting! 🎉
