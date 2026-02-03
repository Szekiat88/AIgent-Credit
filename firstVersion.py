import json

# Import the shared extraction functions from load_file_version
from load_file_version import (
    extract_iscores_all,
    extract_date_after_label,
    extract_word_after_label,
    extract_int_after_label,
    extract_legal_suits_total,
    read_pdf_text,
)

PDF_DEFAULT = "/mnt/data/AVANT GARDE SOLUTIONS (M) SDN. BHD._Experian_250811.pdf"


def extract_fields(pdf_path: str) -> dict:
    text = read_pdf_text(pdf_path)

    incorporation_date = extract_date_after_label("Incorporation Date", text)
    incorporation_year = int(incorporation_date[-4:]) if incorporation_date else None
    
    # Extract all i-SCORE values in one pass
    credit_score, credit_score_2, credit_score_3 = extract_iscores_all(text)

    data = {
        "i_SCORE": credit_score,
        "i_SCORE_2": credit_score_2,
        "i_SCORE_3": credit_score_3,
        "Incorporation_Year": incorporation_year,
        "Status": extract_word_after_label("Status", text),
        "Private_Exempt_Company": extract_word_after_label("Private Exempt Company", text),

        "Winding_Up_Record": extract_int_after_label("Winding Up Record", text),
        "Credit_Applications_Approved_Last_12_months": extract_int_after_label(
            "Credit Applications Approved for Last 12 months", text
        ),
        "Credit_Applications_Pending": extract_int_after_label("Credit Applications Pending", text),
        "Legal_Action_taken_from_Banking": extract_int_after_label("Legal Action taken (from Banking)", text),
        "Existing_No_of_Facility_from_Banking": extract_int_after_label("Existing No. of Facility (from Banking)", text),

        "Legal_Suits": extract_legal_suits_total(text),
    }

    return data


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--pdf", default=PDF_DEFAULT, help="Path to Experian PDF")
    parser.add_argument("--pretty", action="store_true", help="Pretty JSON output")
    args = parser.parse_args()

    result = extract_fields(args.pdf)
    if args.pretty:
        print(json.dumps(result, indent=2))
    else:
        print(json.dumps(result))
