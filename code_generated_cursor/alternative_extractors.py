"""
Alternative PDF table extraction methods using different libraries.
Use these if pdfplumber doesn't work well for your specific PDF format.
"""

import pandas as pd
from typing import List, Optional


class CamelotExtractor:
    """
    Extract tables using Camelot (good for tables with clear borders).
    
    Installation: pip install camelot-py[cv]
    Requires: ghostscript (brew install ghostscript on Mac)
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.target_title = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
    
    def extract_tables(self, pages: str = 'all') -> List[pd.DataFrame]:
        """
        Extract tables using Camelot.
        
        Args:
            pages: Page numbers to process (e.g., '1', '1,2,3', 'all')
            
        Returns:
            List of DataFrames
        """
        try:
            import camelot
        except ImportError:
            print("Camelot not installed. Install with: pip install camelot-py[cv]")
            return []
        
        tables = []
        
        # Try lattice mode first (for tables with lines)
        print("Trying Camelot with lattice mode (tables with borders)...")
        table_list = camelot.read_pdf(
            self.pdf_path,
            pages=pages,
            flavor='lattice',
            line_scale=40
        )
        
        if not table_list:
            # Try stream mode (for tables without lines)
            print("Trying Camelot with stream mode (tables without borders)...")
            table_list = camelot.read_pdf(
                self.pdf_path,
                pages=pages,
                flavor='stream',
                edge_tol=50
            )
        
        for i, table in enumerate(table_list):
            print(f"Table {i+1}: {table.parsing_report}")
            df = table.df
            
            # Check if this is the target table
            table_str = df.to_string().upper()
            if 'OUTSTANDING' in table_str or 'FACILITY' in table_str:
                tables.append(df)
                print(f"  ✓ Found target table ({df.shape[0]} rows, {df.shape[1]} cols)")
        
        return tables


class TabulaExtractor:
    """
    Extract tables using Tabula (Java-based, very robust).
    
    Installation: pip install tabula-py
    Requires: Java Runtime Environment
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.target_title = "DETAILED CREDIT REPORT (BANKING ACCOUNTS)"
    
    def extract_tables(self, pages: str = 'all') -> List[pd.DataFrame]:
        """
        Extract tables using Tabula.
        
        Args:
            pages: Page numbers to process (e.g., 1, '1,2,3', 'all')
            
        Returns:
            List of DataFrames
        """
        try:
            import tabula
        except ImportError:
            print("Tabula not installed. Install with: pip install tabula-py")
            return []
        
        tables = []
        
        print("Extracting tables with Tabula...")
        
        # Read all tables from PDF
        dfs = tabula.read_pdf(
            self.pdf_path,
            pages=pages,
            multiple_tables=True,
            lattice=True,  # Use lattice mode for tables with lines
            pandas_options={'header': None}
        )
        
        for i, df in enumerate(dfs):
            # Check if this is the target table
            table_str = df.to_string().upper()
            if 'OUTSTANDING' in table_str or 'FACILITY' in table_str or 'CONDUCT' in table_str:
                tables.append(df)
                print(f"  ✓ Found target table {i+1} ({df.shape[0]} rows, {df.shape[1]} cols)")
        
        return tables


class PDFMinerExtractor:
    """
    Extract text-based content using PDFMiner (low-level, for complex layouts).
    
    Installation: pip install pdfminer.six
    """
    
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
    
    def extract_text_by_page(self) -> List[str]:
        """
        Extract text from each page.
        
        Returns:
            List of text strings, one per page
        """
        try:
            from pdfminer.high_level import extract_pages
            from pdfminer.layout import LTTextContainer
        except ImportError:
            print("PDFMiner not installed. Install with: pip install pdfminer.six")
            return []
        
        pages_text = []
        
        for page_layout in extract_pages(self.pdf_path):
            page_text = ""
            for element in page_layout:
                if isinstance(element, LTTextContainer):
                    page_text += element.get_text()
            pages_text.append(page_text)
        
        return pages_text
    
    def find_table_pages(self) -> List[int]:
        """
        Find pages containing the target table title.
        
        Returns:
            List of page numbers (1-indexed)
        """
        pages_text = self.extract_text_by_page()
        target_pages = []
        
        for i, text in enumerate(pages_text, 1):
            if "DETAILED CREDIT REPORT (BANKING ACCOUNTS)" in text:
                target_pages.append(i)
        
        return target_pages


def compare_extractors(pdf_path: str):
    """
    Compare results from different extraction methods.
    
    Args:
        pdf_path: Path to the PDF file
    """
    print("=" * 80)
    print("COMPARING PDF EXTRACTION METHODS")
    print("=" * 80)
    
    # 1. pdfplumber
    print("\n1. pdfplumber Method")
    print("-" * 80)
    try:
        from pdf_table_extractor import CreditReportExtractor
        extractor = CreditReportExtractor(pdf_path)
        tables = extractor.extract_tables()
        print(f"Result: Found {len(tables)} table(s)")
        if tables:
            print(f"First table shape: {tables[0].shape}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 2. Camelot
    print("\n2. Camelot Method")
    print("-" * 80)
    try:
        camelot_ext = CamelotExtractor(pdf_path)
        tables = camelot_ext.extract_tables()
        print(f"Result: Found {len(tables)} table(s)")
        if tables:
            print(f"First table shape: {tables[0].shape}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 3. Tabula
    print("\n3. Tabula Method")
    print("-" * 80)
    try:
        tabula_ext = TabulaExtractor(pdf_path)
        tables = tabula_ext.extract_tables()
        print(f"Result: Found {len(tables)} table(s)")
        if tables:
            print(f"First table shape: {tables[0].shape}")
    except Exception as e:
        print(f"Error: {e}")
    
    # 4. PDFMiner (just find pages)
    print("\n4. PDFMiner Method (page detection)")
    print("-" * 80)
    try:
        pdfminer_ext = PDFMinerExtractor(pdf_path)
        pages = pdfminer_ext.find_table_pages()
        print(f"Result: Found target table on page(s): {pages}")
    except Exception as e:
        print(f"Error: {e}")
    
    print("\n" + "=" * 80)
    print("Comparison complete!")


if __name__ == "__main__":
    pdf_path = "credit_report.pdf"  # Replace with your PDF path
    
    try:
        compare_extractors(pdf_path)
    except FileNotFoundError:
        print(f"File not found: {pdf_path}")
        print("Please update the pdf_path variable with your actual PDF path.")
