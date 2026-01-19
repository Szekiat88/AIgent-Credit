"""
Simple example demonstrating how to use the CreditReportExtractor
"""

from pdf_table_extractor import CreditReportExtractor
import pandas as pd


def extract_credit_report(pdf_path: str):
    """
    Extract credit report banking accounts from a PDF.
    
    Args:
        pdf_path: Path to the PDF file
    """
    print(f"Processing: {pdf_path}")
    print("-" * 80)
    
    # Initialize the extractor
    extractor = CreditReportExtractor(pdf_path)
    
    # Method 1: Extract as DataFrame (simpler, good for uniform tables)
    print("\n1. Extracting tables as DataFrames...")
    tables = extractor.extract_tables()
    
    if tables:
        for i, df in enumerate(tables, 1):
            print(f"\n   Table {i} - {len(df)} rows, {len(df.columns)} columns")
            print(f"   Columns: {list(df.columns)}")
            
            # Display first few rows
            print("\n   First 3 rows:")
            print(df.head(3).to_string())
            
            # Save to different formats
            csv_file = f"output_table_{i}.csv"
            excel_file = f"output_table_{i}.xlsx"
            
            df.to_csv(csv_file, index=False)
            df.to_excel(excel_file, index=False)
            
            print(f"\n   ✓ Saved to {csv_file}")
            print(f"   ✓ Saved to {excel_file}")
    else:
        print("   No tables found!")
    
    # Method 2: Extract with detailed parsing (better for complex multi-row records)
    print("\n2. Extracting with detailed parsing...")
    records = extractor.extract_with_detailed_parsing()
    
    if records:
        print(f"\n   Found {len(records)} banking account records")
        
        # Display first record
        print("\n   First record:")
        for key, value in records[0].items():
            print(f"      {key}: {value}")
        
        # Save as JSON
        import json
        json_file = "output_records.json"
        with open(json_file, 'w') as f:
            json.dump(records, f, indent=2, default=str)
        print(f"\n   ✓ Saved to {json_file}")
        
        # Convert to flat DataFrame (for records without nested structures)
        try:
            df_flat = pd.DataFrame(records)
            flat_csv = "output_records_flat.csv"
            df_flat.to_csv(flat_csv, index=False)
            print(f"   ✓ Saved to {flat_csv}")
        except Exception as e:
            print(f"   Note: Could not create flat CSV due to nested data: {e}")
    else:
        print("   No records found!")
    
    print("\n" + "-" * 80)
    print("Processing complete!")


def batch_process_pdfs(pdf_paths: list):
    """
    Process multiple PDF files at once.
    
    Args:
        pdf_paths: List of PDF file paths
    """
    print(f"Batch processing {len(pdf_paths)} PDF files...")
    print("=" * 80)
    
    all_tables = []
    all_records = []
    
    for pdf_path in pdf_paths:
        try:
            extractor = CreditReportExtractor(pdf_path)
            
            # Extract tables
            tables = extractor.extract_tables()
            all_tables.extend(tables)
            
            # Extract records
            records = extractor.extract_with_detailed_parsing()
            all_records.extend(records)
            
            print(f"✓ {pdf_path}: {len(tables)} tables, {len(records)} records")
            
        except Exception as e:
            print(f"✗ {pdf_path}: Error - {e}")
    
    # Combine all tables
    if all_tables:
        combined_df = pd.concat(all_tables, ignore_index=True)
        combined_df.to_csv("combined_all_reports.csv", index=False)
        print(f"\n✓ Combined {len(all_tables)} tables into combined_all_reports.csv")
    
    # Save all records
    if all_records:
        import json
        with open("combined_all_records.json", 'w') as f:
            json.dump(all_records, f, indent=2, default=str)
        print(f"✓ Saved {len(all_records)} records to combined_all_records.json")
    
    print("=" * 80)
    print("Batch processing complete!")


if __name__ == "__main__":
    # Example 1: Process a single PDF
    print("EXAMPLE 1: Single PDF Processing")
    print("=" * 80)
    
    # Replace with your actual PDF path
    pdf_file = "credit_report.pdf"
    
    try:
        extract_credit_report(pdf_file)
    except FileNotFoundError:
        print(f"File not found: {pdf_file}")
        print("Please update the pdf_file variable with your actual PDF path.")
    except Exception as e:
        print(f"Error: {e}")
    
    # Example 2: Process multiple PDFs
    print("\n\nEXAMPLE 2: Batch Processing")
    print("=" * 80)
    
    # Replace with your actual PDF paths
    pdf_files = [
        "credit_report_1.pdf",
        "credit_report_2.pdf",
        "credit_report_3.pdf",
    ]
    
    # Uncomment to run batch processing
    # try:
    #     batch_process_pdfs(pdf_files)
    # except Exception as e:
    #     print(f"Error: {e}")
