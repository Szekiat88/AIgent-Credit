import argparse
import json
from typing import Any, Dict, Optional

from Detailed_Credit_Report_Extractor import extract_detailed_credit_report
from Non_Bank_Lender_Credit_Information import extract_non_bank_lender_credit_information
from load_file_version import extract_fields, pick_pdf_file


def merge_reports(pdf_path: str) -> Dict[str, Any]:
    summary_report = extract_fields(pdf_path)
    detailed_report = extract_detailed_credit_report(pdf_path)
    non_bank_report = extract_non_bank_lender_credit_information(pdf_path)

    return {
        "pdf_file": pdf_path,
        "summary_report": summary_report,
        "detailed_credit_report": detailed_report,
        "non_bank_lender_credit_information": non_bank_report,
    }


def resolve_pdf_path(arg_pdf: Optional[str]) -> Optional[str]:
    if arg_pdf:
        return arg_pdf
    return pick_pdf_file()


def main() -> None:
    parser = argparse.ArgumentParser(description="Merge summary and detailed credit report extracts.")
    parser.add_argument("--pdf", help="Path to Experian PDF")
    parser.add_argument("--output", default="merged_credit_report.json", help="Output JSON file")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    pdf_path = resolve_pdf_path(args.pdf)
    if not pdf_path:
        print("❌ No PDF selected.")
        return

    merged = merge_reports(pdf_path)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(merged, f, indent=2 if args.pretty else None, ensure_ascii=False)

    print(f"✅ Merged report saved to {args.output}")


if __name__ == "__main__":
    main()
