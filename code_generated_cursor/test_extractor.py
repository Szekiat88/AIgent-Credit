"""
Test script for the Credit Report PDF Table Extractor.
Run this to verify the installation and test extraction on your PDF.
"""

import sys
import os
from pathlib import Path


def check_dependencies():
    """Check if required dependencies are installed."""
    print("=" * 80)
    print("CHECKING DEPENDENCIES")
    print("=" * 80)
    
    dependencies = {
        'pdfplumber': False,
        'pandas': False,
        'openpyxl': False,
        'camelot': False,
        'tabula': False,
    }
    
    # Check pdfplumber
    try:
        import pdfplumber
        dependencies['pdfplumber'] = True
        print("✓ pdfplumber installed")
    except ImportError:
        print("✗ pdfplumber NOT installed - pip install pdfplumber")
    
    # Check pandas
    try:
        import pandas
        dependencies['pandas'] = True
        print("✓ pandas installed")
    except ImportError:
        print("✗ pandas NOT installed - pip install pandas")
    
    # Check openpyxl
    try:
        import openpyxl
        dependencies['openpyxl'] = True
        print("✓ openpyxl installed (for Excel export)")
    except ImportError:
        print("✗ openpyxl NOT installed - pip install openpyxl")
    
    # Check camelot (optional)
    try:
        import camelot
        dependencies['camelot'] = True
        print("✓ camelot installed (optional)")
    except ImportError:
        print("⚠ camelot NOT installed (optional) - pip install camelot-py[cv]")
    
    # Check tabula (optional)
    try:
        import tabula
        dependencies['tabula'] = True
        print("✓ tabula installed (optional)")
    except ImportError:
        print("⚠ tabula NOT installed (optional) - pip install tabula-py")
    
    print("\n" + "-" * 80)
    
    # Check if minimum requirements are met
    if dependencies['pdfplumber'] and dependencies['pandas']:
        print("✓ Minimum requirements met! Ready to extract tables.")
        return True
    else:
        print("✗ Missing required dependencies. Please install them:")
        print("  pip install -r requirements.txt")
        return False


def test_extraction(pdf_path: str):
    """
    Test the extraction on a given PDF file.
    
    Args:
        pdf_path: Path to the PDF file
    """
    print("\n" + "=" * 80)
    print(f"TESTING EXTRACTION ON: {pdf_path}")
    print("=" * 80)
    
    # Check if file exists
    if not os.path.exists(pdf_path):
        print(f"✗ Error: File not found - {pdf_path}")
        return False
    
    print(f"✓ File found: {os.path.getsize(pdf_path)} bytes")
    
    # Import the extractor
    try:
        from pdf_table_extractor import CreditReportExtractor
    except ImportError as e:
        print(f"✗ Error importing extractor: {e}")
        return False
    
    # Test basic extraction
    print("\n" + "-" * 80)
    print("TEST 1: Basic Table Extraction")
    print("-" * 80)
    
    try:
        extractor = CreditReportExtractor(pdf_path)
        tables = extractor.extract_tables()
        
        if tables:
            print(f"✓ Success! Found {len(tables)} table(s)")
            
            for i, df in enumerate(tables, 1):
                print(f"\n  Table {i}:")
                print(f"    Rows: {len(df)}")
                print(f"    Columns: {len(df.columns)}")
                print(f"    Column names: {list(df.columns)[:5]}...")  # First 5 columns
                
                if len(df) > 0:
                    print(f"\n    First row sample:")
                    first_row = df.iloc[0]
                    for col in df.columns[:3]:  # Show first 3 columns
                        print(f"      {col}: {first_row[col]}")
                
                # Try to save
                output_file = f"test_output_table_{i}.csv"
                df.to_csv(output_file, index=False)
                print(f"\n    ✓ Saved to: {output_file}")
        else:
            print("⚠ No tables found with the target title.")
            print("  Possible reasons:")
            print("  - PDF doesn't contain 'DETAILED CREDIT REPORT (BANKING ACCOUNTS)'")
            print("  - Table structure is too complex")
            print("  - PDF is image-based (needs OCR)")
    
    except Exception as e:
        print(f"✗ Error during extraction: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # Test detailed parsing
    print("\n" + "-" * 80)
    print("TEST 2: Detailed Parsing")
    print("-" * 80)
    
    try:
        records = extractor.extract_with_detailed_parsing()
        
        if records:
            print(f"✓ Success! Found {len(records)} record(s)")
            
            if records:
                print(f"\n  First record structure:")
                for key, value in list(records[0].items())[:5]:  # First 5 fields
                    print(f"    {key}: {value}")
                
                # Try to save
                import json
                output_file = "test_output_records.json"
                with open(output_file, 'w') as f:
                    json.dump(records, f, indent=2, default=str)
                print(f"\n  ✓ Saved to: {output_file}")
        else:
            print("⚠ No records found.")
    
    except Exception as e:
        print(f"✗ Error during detailed parsing: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 80)
    print("TESTING COMPLETE")
    print("=" * 80)
    
    return True


def find_pdf_files():
    """Find PDF files in the current directory."""
    pdf_files = list(Path('.').glob('*.pdf'))
    return [str(f) for f in pdf_files]


def interactive_mode():
    """Run the test in interactive mode."""
    print("\n" + "=" * 80)
    print("CREDIT REPORT PDF TABLE EXTRACTOR - TEST MODE")
    print("=" * 80)
    
    # Check dependencies first
    if not check_dependencies():
        print("\n❌ Please install required dependencies first.")
        print("   Run: pip install -r requirements.txt")
        return
    
    # Look for PDF files
    print("\n" + "-" * 80)
    print("LOOKING FOR PDF FILES")
    print("-" * 80)
    
    pdf_files = find_pdf_files()
    
    if pdf_files:
        print(f"Found {len(pdf_files)} PDF file(s) in current directory:")
        for i, pdf in enumerate(pdf_files, 1):
            size_mb = os.path.getsize(pdf) / (1024 * 1024)
            print(f"  {i}. {pdf} ({size_mb:.2f} MB)")
        
        # Ask user to select
        print("\nEnter the number of the PDF to test (or 'q' to quit):")
        choice = input("> ").strip()
        
        if choice.lower() == 'q':
            print("Exiting...")
            return
        
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(pdf_files):
                test_extraction(pdf_files[idx])
            else:
                print("Invalid selection.")
        except ValueError:
            print("Invalid input.")
    else:
        print("No PDF files found in current directory.")
        print("\nPlease provide the path to your PDF file:")
        pdf_path = input("> ").strip()
        
        if pdf_path and os.path.exists(pdf_path):
            test_extraction(pdf_path)
        else:
            print("File not found.")


def main():
    """Main function."""
    print("""
╔════════════════════════════════════════════════════════════════════════════╗
║                   CREDIT REPORT PDF TABLE EXTRACTOR                        ║
║                              TEST UTILITY                                  ║
╚════════════════════════════════════════════════════════════════════════════╝
""")
    
    if len(sys.argv) > 1:
        # Command-line mode: python test_extractor.py <pdf_file>
        pdf_path = sys.argv[1]
        
        # Check dependencies
        if not check_dependencies():
            sys.exit(1)
        
        # Test extraction
        success = test_extraction(pdf_path)
        sys.exit(0 if success else 1)
    else:
        # Interactive mode
        interactive_mode()


if __name__ == "__main__":
    main()
