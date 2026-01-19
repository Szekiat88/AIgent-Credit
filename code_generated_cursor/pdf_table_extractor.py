"""
PDF Table Extractor for Credit Reports
Extracts tables with title "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
"""

import pdfplumber
import pandas as pd
import re
from typing import List, Dict, Optional, Tuple


class CreditReportExtractor:
    """Extract credit report tables from PDF documents."""
    
    def __init__(self, pdf_path: str):
        """
        Initialize the extractor with a PDF file path.
        
        Args:
            pdf_path: Path to the PDF file
        """
        self.pdf_path = pdf_path
        self.target_title = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
    
    def extract_tables(self) -> List[pd.DataFrame]:
        """
        Extract all tables with the target title from the PDF.
        
        Returns:
            List of DataFrames containing the extracted tables
        """
        tables = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                # Extract text to find the title
                text = page.extract_text()
                
                if text and self.target_title in text:
                    print(f"Found target table on page {page_num}")
                    
                    # Extract tables from this page
                    page_tables = page.extract_tables()
                    
                    for table in page_tables:
                        if table and len(table) > 0:
                            # Check if this is the correct table by looking at first few rows
                            if self._is_target_table(table):
                                df = self._process_table(table)
                                tables.append(df)
                                print(f"  Extracted table with {len(df)} rows")
        
        return tables
    
    def _is_target_table(self, table: List[List]) -> bool:
        """
        Check if the extracted table is the target table.
        
        Args:
            table: Raw table data
            
        Returns:
            True if this is the target table
        """
        # Look for characteristic column headers in the first few rows
        table_str = str(table[:5]).upper()
        keywords = ["OUTSTANDING", "BALANCE", "FACILITY", "CONDUCT", "ACCOUNT"]
        matches = sum(1 for keyword in keywords if keyword in table_str)
        return matches >= 3
    
    def _process_table(self, raw_table: List[List]) -> pd.DataFrame:
        """
        Process and clean the raw table data.
        
        Args:
            raw_table: Raw table data from pdfplumber
            
        Returns:
            Cleaned DataFrame
        """
        # Create DataFrame
        df = pd.DataFrame(raw_table)
        
        # Find the header row (usually contains key column names)
        header_row_idx = self._find_header_row(df)
        
        if header_row_idx is not None:
            # Use the found row as headers
            df.columns = df.iloc[header_row_idx]
            df = df.iloc[header_row_idx + 1:].reset_index(drop=True)
        
        # Clean up the data
        df = df.replace('', None)
        df = df.replace('None', None)
        
        return df
    
    def _find_header_row(self, df: pd.DataFrame) -> Optional[int]:
        """
        Find the row containing column headers.
        
        Args:
            df: DataFrame to search
            
        Returns:
            Index of header row, or None if not found
        """
        for idx, row in df.iterrows():
            row_str = ' '.join([str(cell) for cell in row if cell]).upper()
            if 'OUTSTANDING' in row_str or 'FACILITY' in row_str or 'BALANCE' in row_str:
                return idx
        return 0  # Default to first row
    
    def extract_with_detailed_parsing(self) -> List[Dict]:
        """
        Extract tables with more detailed parsing for complex structures.
        This method handles merged cells and multi-row records better.
        
        Returns:
            List of dictionaries containing parsed records
        """
        records = []
        
        with pdfplumber.open(self.pdf_path) as pdf:
            for page_num, page in enumerate(pdf.pages, 1):
                text = page.extract_text()
                
                if text and self.target_title in text:
                    print(f"Processing page {page_num} with detailed parsing")
                    
                    # Extract tables with custom settings
                    table_settings = {
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                        "intersection_tolerance": 5,
                    }
                    
                    tables = page.extract_tables(table_settings)
                    
                    for table in tables:
                        if table and self._is_target_table(table):
                            parsed_records = self._parse_banking_records(table)
                            records.extend(parsed_records)
        
        return records
    
    def _parse_banking_records(self, table: List[List]) -> List[Dict]:
        """
        Parse banking account records from the table.
        
        Args:
            table: Raw table data
            
        Returns:
            List of dictionaries, each representing a banking account
        """
        records = []
        current_record = None
        
        # Find where the actual data starts (skip headers)
        data_start_idx = self._find_data_start(table)
        
        for i, row in enumerate(table[data_start_idx:], data_start_idx):
            # Check if this is a new record (has a number in first column or date in second)
            if row[0] and str(row[0]).strip() and str(row[0]).strip().isdigit():
                # Save previous record if exists
                if current_record:
                    records.append(current_record)
                
                # Start new record
                current_record = {
                    'No': row[0],
                    'Date': row[1] if len(row) > 1 else None,
                    'Status': row[2] if len(row) > 2 else None,
                    'Capacity': row[3] if len(row) > 3 else None,
                    'Lender_Type': row[4] if len(row) > 4 else None,
                    'Facility': row[5] if len(row) > 5 else None,
                    'Total_Outstanding_Balance': row[6] if len(row) > 6 else None,
                    'Date_Balance_Updated': row[7] if len(row) > 7 else None,
                    'Limit_Inst_Amt': row[8] if len(row) > 8 else None,
                    'Prin_Repymt_Term': row[9] if len(row) > 9 else None,
                    'Col_Type': row[10] if len(row) > 10 else None,
                    'Conduct_History': [],
                }
            elif current_record and len(row) > 5:
                # This might be a facility detail row
                facility = row[5] if len(row) > 5 else None
                if facility and str(facility).strip():
                    # Add facility details
                    current_record['facilities'] = current_record.get('facilities', [])
                    current_record['facilities'].append({
                        'Facility': facility,
                        'Outstanding_Balance': row[6] if len(row) > 6 else None,
                        'Date_Updated': row[7] if len(row) > 7 else None,
                        'Limit': row[8] if len(row) > 8 else None,
                        'Term': row[9] if len(row) > 9 else None,
                    })
        
        # Don't forget the last record
        if current_record:
            records.append(current_record)
        
        return records
    
    def _find_data_start(self, table: List[List]) -> int:
        """
        Find where the actual data starts (skip title and headers).
        
        Args:
            table: Raw table data
            
        Returns:
            Index where data starts
        """
        for idx, row in enumerate(table):
            # Look for "OUTSTANDING CREDIT" or similar markers
            row_str = ' '.join([str(cell) for cell in row if cell]).upper()
            if 'OUTSTANDING CREDIT' in row_str:
                return idx + 1
        
        # If not found, look for numeric first column (record number)
        for idx, row in enumerate(table):
            if row[0] and str(row[0]).strip().isdigit():
                return idx
        
        return 3  # Default: skip first 3 rows (title, headers, etc.)


def main():
    """Example usage of the CreditReportExtractor."""
    
    # Example 1: Basic extraction
    pdf_path = "credit_report.pdf"  # Replace with your PDF path
    
    extractor = CreditReportExtractor(pdf_path)
    
    print("=" * 80)
    print("METHOD 1: Basic Table Extraction")
    print("=" * 80)
    
    try:
        tables = extractor.extract_tables()
        
        if tables:
            for i, df in enumerate(tables, 1):
                print(f"\nTable {i}:")
                print(df.head())
                print(f"\nShape: {df.shape}")
                
                # Save to CSV
                output_file = f"credit_report_table_{i}.csv"
                df.to_csv(output_file, index=False)
                print(f"Saved to {output_file}")
        else:
            print("No tables found with the specified title.")
    
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
    except Exception as e:
        print(f"Error during extraction: {e}")
    
    print("\n" + "=" * 80)
    print("METHOD 2: Detailed Parsing")
    print("=" * 80)
    
    try:
        records = extractor.extract_with_detailed_parsing()
        
        if records:
            print(f"\nExtracted {len(records)} records")
            print("\nFirst record:")
            print(records[0])
            
            # Convert to DataFrame for easier viewing
            df_records = pd.DataFrame(records)
            print(f"\nRecords DataFrame shape: {df_records.shape}")
            print(df_records.head())
            
            # Save to JSON for complex nested data
            import json
            with open('credit_report_records.json', 'w') as f:
                json.dump(records, f, indent=2, default=str)
            print("\nSaved detailed records to credit_report_records.json")
        else:
            print("No records found.")
    
    except FileNotFoundError:
        print(f"Error: PDF file not found at {pdf_path}")
    except Exception as e:
        print(f"Error during detailed parsing: {e}")


if __name__ == "__main__":
    main()
