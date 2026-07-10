"""
Unit tests for the Form 16 OCR normalization (pure function, no I/O).

Covers the three response shapes the OCR service can emit — nested
part_a/part_b, flat keys, and a `data`-wrapped payload — plus the empty case.
"""
from app.api.form16.normalize import normalize_ocr_response
from app.api.form16.schemas import Form16Data


NESTED_PAYLOAD = {
    "part_a": {
        "name_of_employee": "Rohit Sharma",
        "pan_of_the_employee_or_specified_senior_citizen": "ABCDE1234F",
        "pan_of_the_deductor": "AAACX1234M",
        "tan_of_the_deductor": "DELX12345A",
        "assessment_year": "2025-26",
        "name_and_address_of_the_employer_or_specified_bank": "XYZ Technologies Pvt Ltd",
        "summary_of_amount_paid_or_credited_and_tax_deducted": {
            "total": {
                "total_amt_of_tax_deducted": 56000,
                "total_amt_of_tax_deposited_or_remitted": 56000,
            }
        },
    },
    "part_b": {
        "details_of_salary_paid_and_any_other_income_and_tax_deducted": {
            "gross_salary": {"total": 780000},
            "less_deductions_under_section_16": {
                "standard_deduction_under_section_16_ia": [50000]
            },
            "deductions_under_chapter_vi_a": {
                "deduction_in_respect_of_life_insurance_premia_pf_etc_under_section_80c": {
                    "deductible_amount": 150000
                },
                "deduction_in_respect_of_health_insurance_premia_under_section_80d": {
                    "deductible_amount": 25000
                },
            },
            "total_taxable_income": 730000,
            "tax_payable": 58240,
            "net_tax_payable": 58240,
            "health_and_education_cess": 2240,
            "whether_opting_for_taxation_us_115bac": "No",
        }
    },
}


def test_nested_part_a_part_b():
    r = normalize_ocr_response(NESTED_PAYLOAD, "form16.pdf")

    assert r["fileName"] == "form16.pdf"
    assert r["employeeName"] == "Rohit Sharma"
    assert r["employeePan"] == "ABCDE1234F"
    assert r["employerPan"] == "AAACX1234M"
    assert r["employerTan"] == "DELX12345A"
    assert r["assessmentYear"] == "2025-26"
    assert r["employerName"] == "XYZ Technologies Pvt Ltd"

    assert r["grossSalary"] == 780000
    assert r["standardDeduction"] == 50000
    assert r["section80C"] == 150000
    assert r["section80D"] == 25000
    assert r["taxableIncome"] == 730000
    assert r["taxPayable"] == 58240
    assert r["netTaxPayable"] == 58240
    assert r["healthAndEducationCess"] == 2240
    assert r["totalTaxDeducted"] == 56000
    assert r["totalTaxDeposited"] == 56000

    assert r["taxRegime"] == "old"  # opting for 115BAC = "No"
    assert r["confidence"] == "high"  # many fields detected
    assert r["warnings"] == []

    # The normalized dict must satisfy the API contract.
    Form16Data(**r)


def test_flat_keys_and_indian_number_format():
    payload = {
        "employee_name": "Asha Verma",
        "employee_pan": "PQRSX9999K",
        "assessment_year": "2024-25",
        "gross_salary": "5,00,000",  # Indian comma grouping
        "section80C": 100000,
        "total_tax_deducted": 12000,
    }
    r = normalize_ocr_response(payload, "flat.pdf")

    assert r["employeeName"] == "Asha Verma"
    assert r["employeePan"] == "PQRSX9999K"
    assert r["assessmentYear"] == "2024-25"
    assert r["grossSalary"] == 500000  # commas stripped and parsed
    assert r["section80C"] == 100000
    assert r["totalTaxDeducted"] == 12000
    Form16Data(**r)


def test_data_wrapped_payload():
    payload = {"data": {"employee_name": "Wrapped User", "gross_salary": 100}}
    r = normalize_ocr_response(payload, "wrapped.pdf")
    assert r["employeeName"] == "Wrapped User"
    assert r["grossSalary"] == 100


def test_empty_payload_is_low_confidence_with_warning():
    r = normalize_ocr_response({}, "empty.pdf")
    assert r["confidence"] == "low"
    assert r["assessmentYear"] is None
    assert r["grossSalary"] == 0
    assert any("did not return parseable" in w for w in r["warnings"])
    Form16Data(**r)


def test_non_dict_payload_does_not_crash():
    r = normalize_ocr_response("garbage", "x.pdf")
    assert r["confidence"] == "low"
    assert r["grossSalary"] == 0
