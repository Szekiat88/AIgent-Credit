# Workflow Guide: Credit Report PDF Extraction

## 📋 Complete Workflow

```
START
  │
  ▼
┌─────────────────────────────────────────┐
│   1. INSTALLATION & SETUP               │
│                                         │
│   Option A: Automated                   │
│   → Run: ./install.sh (Mac/Linux)      │
│   → Run: install.bat (Windows)         │
│                                         │
│   Option B: Manual                      │
│   → Run: pip install -r requirements.txt│
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   2. VERIFY INSTALLATION                │
│                                         │
│   → Run: python test_extractor.py      │
│   → Should show: ✓ All dependencies OK │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   3. PREPARE YOUR PDF                   │
│                                         │
│   Requirements:                         │
│   • Text-based PDF (not scanned)       │
│   • Contains table title:               │
│     "DETAILED CREDIT REPORT             │
│      (BANKING ACCOUNTS)"                │
│   • Readable table structure            │
└─────────────────┬───────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────┐
│   4. CHOOSE YOUR METHOD                 │
└─────────────────┬───────────────────────┘
                  │
         ┌────────┴────────┬──────────┐
         │                 │          │
         ▼                 ▼          ▼
    ┌────────┐      ┌──────────┐  ┌──────────┐
    │ Simple │      │ Detailed │  │  Batch   │
    │  Mode  │      │   Mode   │  │   Mode   │
    └────┬───┘      └─────┬────┘  └─────┬────┘
         │                │              │
         │                │              │
         ▼                ▼              ▼
    ┌─────────────────────────────────────────┐
    │   5A. SIMPLE EXTRACTION                 │
    │                                         │
    │   from pdf_table_extractor import      │
    │       CreditReportExtractor             │
    │                                         │
    │   ext = CreditReportExtractor(pdf)     │
    │   tables = ext.extract_tables()        │
    │   tables[0].to_csv("out.csv")          │
    │                                         │
    │   Output: CSV file                      │
    │   Use when: Simple table structure     │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   5B. DETAILED EXTRACTION               │
    │                                         │
    │   from pdf_table_extractor import      │
    │       CreditReportExtractor             │
    │   import json                           │
    │                                         │
    │   ext = CreditReportExtractor(pdf)     │
    │   records = ext.extract_with_          │
    │             detailed_parsing()          │
    │   with open("out.json", "w") as f:     │
    │       json.dump(records, f)             │
    │                                         │
    │   Output: JSON with nested data         │
    │   Use when: Complex multi-row records   │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   5C. BATCH PROCESSING                  │
    │                                         │
    │   pdfs = ["r1.pdf", "r2.pdf", ...]     │
    │   all_data = []                         │
    │                                         │
    │   for pdf in pdfs:                      │
    │       ext = CreditReportExtractor(pdf) │
    │       tables = ext.extract_tables()    │
    │       all_data.extend(tables)           │
    │                                         │
    │   combined = pd.concat(all_data)       │
    │   combined.to_csv("combined.csv")      │
    │                                         │
    │   Output: Combined CSV from all PDFs    │
    │   Use when: Multiple PDF files          │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
    ┌─────────┐              ┌──────────┐
    │ SUCCESS │              │  FAILED  │
    └────┬────┘              └─────┬────┘
         │                         │
         ▼                         ▼
    ┌─────────────────────────────────────────┐
    │   6A. SUCCESS - VERIFY OUTPUT           │
    │                                         │
    │   Check:                                │
    │   ✓ Output files exist                  │
    │   ✓ Row count is correct               │
    │   ✓ All columns present                │
    │   ✓ Data looks accurate                │
    │                                         │
    │   Next: Use the data in your app       │
    └─────────────────────────────────────────┘

    ┌─────────────────────────────────────────┐
    │   6B. TROUBLESHOOTING                   │
    │                                         │
    │   Problem: No tables found              │
    │   → Check PDF contains target title     │
    │   → Try: alternative_extractors.py      │
    │                                         │
    │   Problem: Malformed output             │
    │   → Use: extract_with_detailed_parsing()│
    │   → Try: CamelotExtractor              │
    │                                         │
    │   Problem: Missing data                 │
    │   → Check PDF is text-based            │
    │   → Adjust table_settings parameters    │
    │                                         │
    │   Problem: Import errors                │
    │   → Reinstall: pip install -r req...    │
    │   → Check Python version (3.8+)        │
    └─────────────────┬───────────────────────┘
                      │
                      ▼
    ┌─────────────────────────────────────────┐
    │   7. USE YOUR DATA                      │
    │                                         │
    │   Options:                              │
    │   • Import to Excel for analysis       │
    │   • Load into database                 │
    │   • Process with Python/R              │
    │   • Generate reports                   │
    │   • Feed into ML models                │
    └─────────────────────────────────────────┘
                      │
                      ▼
                    END
```

## 🔄 Decision Tree: Which Method to Use?

```
Do you need to extract a single PDF?
│
├─ YES → Is the table simple (uniform rows)?
│        │
│        ├─ YES → Use: extract_tables()
│        │        └─ Code: See QUICKSTART.md
│        │
│        └─ NO → Is it complex (merged cells, multi-row)?
│                 │
│                 ├─ YES → Use: extract_with_detailed_parsing()
│                 │        └─ Code: See example_usage.py
│                 │
│                 └─ UNSURE → Run: python test_extractor.py
│                            └─ Compare both methods
│
└─ NO → Do you have multiple PDFs?
         │
         ├─ Few PDFs (< 10) → Use: Batch script
         │                     └─ Code: See example_usage.py
         │
         └─ Many PDFs (10+) → Use: Parallel processing
                               └─ Code: Add multiprocessing
```

## 🛠️ Extraction Method Selector

```
┌─────────────────────────────────────────────────────┐
│           Which Extractor Should I Use?             │
└─────────────────────────────────────────────────────┘

START → Is pdfplumber working?
        │
        ├─ YES → Great! Use pdf_table_extractor.py
        │        └─ Fast, reliable, good for most cases
        │
        └─ NO → Does the table have clear borders?
                │
                ├─ YES → Try: CamelotExtractor
                │        │  (alternative_extractors.py)
                │        └─ Best for bordered tables
                │
                └─ NO → Is the PDF complex?
                        │
                        ├─ YES → Try: TabulaExtractor
                        │        │  (alternative_extractors.py)
                        │        └─ Java-based, very robust
                        │
                        └─ STILL NO → Check if PDF is:
                                      │
                                      ├─ Scanned image? 
                                      │  └─ Need OCR first
                                      │
                                      ├─ Encrypted?
                                      │  └─ Decrypt first
                                      │
                                      └─ Corrupted?
                                         └─ Try repair tools
```

## 📊 Data Flow Diagram

```
┌──────────────┐
│  PDF File    │
│              │
│  ┌────────┐  │
│  │ Table  │  │  ← Contains: DETAILED CREDIT REPORT
│  │  Data  │  │              (BANKING ACCOUNTS)
│  └────────┘  │
└──────┬───────┘
       │
       │ Read & Parse
       ▼
┌──────────────────────────────────┐
│   Credit Report Extractor        │
│                                  │
│  ┌────────────────────────────┐  │
│  │ 1. Detect Table Title      │  │
│  └────────────────────────────┘  │
│              │                   │
│              ▼                   │
│  ┌────────────────────────────┐  │
│  │ 2. Extract Table Structure │  │
│  │    • Headers               │  │
│  │    • Rows                  │  │
│  │    • Cells                 │  │
│  └────────────────────────────┘  │
│              │                   │
│              ▼                   │
│  ┌────────────────────────────┐  │
│  │ 3. Parse Data              │  │
│  │    • Account numbers       │  │
│  │    • Balances              │  │
│  │    • Dates                 │  │
│  │    • Status codes          │  │
│  └────────────────────────────┘  │
│              │                   │
│              ▼                   │
│  ┌────────────────────────────┐  │
│  │ 4. Structure Records       │  │
│  │    • Clean data            │  │
│  │    • Validate format       │  │
│  │    • Handle missing values │  │
│  └────────────────────────────┘  │
└──────────────┬───────────────────┘
               │
               │ Output
               ▼
       ┌───────┴────────┬──────────┐
       │                │          │
       ▼                ▼          ▼
  ┌─────────┐     ┌─────────┐  ┌──────────┐
  │   CSV   │     │  Excel  │  │   JSON   │
  │  File   │     │  File   │  │   File   │
  └────┬────┘     └────┬────┘  └────┬─────┘
       │               │            │
       └───────┬───────┴────────────┘
               │
               ▼
       ┌───────────────┐
       │  Your         │
       │  Application  │
       │               │
       │  • Analysis   │
       │  • Reporting  │
       │  • Database   │
       │  • Dashboard  │
       └───────────────┘
```

## 🎯 Step-by-Step Example

### Scenario: Extract credit report from a single PDF

```bash
# Step 1: Navigate to project directory
cd "/Users/newuser/Documents/GitHub/AIgent Credit"

# Step 2: Ensure dependencies are installed
pip install -r requirements.txt

# Step 3: Run test to verify setup
python test_extractor.py

# Step 4: Place your PDF in the directory
# Or note its full path

# Step 5: Create a simple script
cat > extract_my_report.py << 'EOF'
from pdf_table_extractor import CreditReportExtractor

# Your PDF file
pdf_file = "my_credit_report.pdf"

# Create extractor
extractor = CreditReportExtractor(pdf_file)

# Extract tables
tables = extractor.extract_tables()

# Save to CSV
if tables:
    output_file = "extracted_credit_report.csv"
    tables[0].to_csv(output_file, index=False)
    print(f"✓ Extracted {len(tables[0])} rows")
    print(f"✓ Saved to: {output_file}")
else:
    print("✗ No tables found")
EOF

# Step 6: Run your script
python extract_my_report.py

# Step 7: Check output
ls -lh extracted_credit_report.csv
head extracted_credit_report.csv
```

## 🔍 Quality Checklist

After extraction, verify:

```
□ Output file created successfully
□ File size is reasonable (not empty or too small)
□ Number of rows matches PDF
□ All expected columns present:
  □ No
  □ Date
  □ Status
  □ Capacity
  □ Lender Type
  □ Facility
  □ Total Outstanding Balance
  □ Date Balance Updated
  □ Limit/Inst Amt
  □ Prin Repymt Term
  □ Col Type
  □ Conduct of Account
  □ Legal Status
  □ Date Status Update
□ Data types look correct (numbers are numbers, dates are dates)
□ No obvious missing or corrupted data
□ Special characters handled correctly
```

## 📁 File Selection Guide

```
What do I run?
│
├─ First time setup?
│  └─ Run: install.sh (or install.bat on Windows)
│
├─ Want to test if it works?
│  └─ Run: python test_extractor.py your_file.pdf
│
├─ Need quick examples?
│  └─ Read: QUICKSTART.md
│
├─ Want detailed documentation?
│  └─ Read: README.md
│
├─ Ready to extract (single PDF)?
│  └─ Use: pdf_table_extractor.py
│  └─ Or: python example_usage.py (modify the path)
│
├─ Need to extract multiple PDFs?
│  └─ Use: example_usage.py → batch_process_pdfs()
│
├─ First method not working?
│  └─ Try: alternative_extractors.py
│
└─ Understanding the system?
   └─ Read: PROJECT_SUMMARY.md (this file)
```

## 🚦 Status Indicators

When running extraction, look for these indicators:

```
✓ Success indicators:
  • "Found target table on page X"
  • "Extracted table with Y rows"
  • "Saved to output.csv"

⚠ Warning indicators:
  • "No tables found with the specified title"
  • "Table might be incomplete"
  • "Could not parse some rows"

✗ Error indicators:
  • "File not found"
  • "Module not installed"
  • "PDF could not be opened"
```

## 🎓 Learning Path

```
Beginner    → Read QUICKSTART.md
            → Run test_extractor.py
            → Try example_usage.py with your PDF

Intermediate → Understand pdf_table_extractor.py
             → Modify extraction parameters
             → Try different output formats

Advanced    → Explore alternative_extractors.py
            → Customize parsing logic
            → Add new features
            → Integrate with your systems
```

## 📞 Getting Help

```
Issue                         → Solution
────────────────────────────────────────────────
Installation fails            → Check Python version (need 3.8+)
                              → Read install errors carefully
                              → Try manual: pip install pdfplumber

Can't find table              → Verify PDF has target title
                              → Check PDF is text-based
                              → Try: python test_extractor.py

Output looks wrong            → Try: extract_with_detailed_parsing()
                              → Try: alternative_extractors.py
                              → Adjust table_settings

Performance is slow           → Process specific pages only
                              → Use simpler extraction method
                              → Try multiprocessing for batches

Still stuck?                  → Review README.md troubleshooting
                              → Check file permissions
                              → Verify PDF is not corrupted
```

---

**Quick Reference Card**

```
┌─────────────────────────────────────────────────────────┐
│                   QUICK COMMANDS                        │
├─────────────────────────────────────────────────────────┤
│ Install       │ pip install -r requirements.txt         │
│ Test          │ python test_extractor.py file.pdf       │
│ Extract       │ python example_usage.py                 │
│ Help          │ Read QUICKSTART.md or README.md         │
└─────────────────────────────────────────────────────────┘
```

Happy extracting! 🎉
