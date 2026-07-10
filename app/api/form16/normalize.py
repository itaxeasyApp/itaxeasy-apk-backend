"""
Normalize the OCR service's Form 16 response into one stable schema.

This is a faithful Python port of the mapping that previously lived in the app
(`form16Extraction.service.ts → normalizeApiResponse`). Keeping it server-side
means the app receives clean, predictable fields instead of guessing at the many
possible OCR key shapes (flat keys, nested `part_a`/`part_b`, arrays, etc.).

`normalize_ocr_response` is a pure function — no I/O — so it is unit-tested
directly against sample OCR payloads.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# ----------------------------------------------------------------- primitives


def to_number(value: Any) -> Optional[float]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if _is_finite(float(value)) else None
    if isinstance(value, str) and value.strip():
        try:
            parsed = float(value.replace(",", ""))
        except ValueError:
            return None
        return parsed if _is_finite(parsed) else None
    return None


def _is_finite(x: float) -> bool:
    return x == x and x not in (float("inf"), float("-inf"))


def read_text(value: Any) -> Optional[str]:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_first_line(value: Any) -> Optional[str]:
    text = read_text(value)
    if not text:
        return None
    first = re.split(r"\r?\n", text)[0].strip()
    return first or None


def as_record(value: Any) -> Optional[dict]:
    if isinstance(value, dict):
        return value
    return None


def get_record(source: Optional[dict], key: str) -> Optional[dict]:
    if source is None:
        return None
    return as_record(source.get(key))


def get_nested_number(source: Optional[dict], key: str, nested_key: str) -> Optional[float]:
    rec = as_record(source.get(key)) if source else None
    if rec is None:
        return None
    return to_number(rec.get(nested_key))


def get_array_item(value: Any, index: int = 0) -> Any:
    if isinstance(value, list):
        return value[index] if 0 <= index < len(value) else None
    return value


def read_text_at(value: Any, index: int = 0) -> Optional[str]:
    return read_text(get_array_item(value, index))


def to_number_at(value: Any, index: int = 0) -> Optional[float]:
    return to_number(get_array_item(value, index))


def first_text(*values: Any) -> Optional[str]:
    for value in values:
        text = read_text(value)
        if text:
            return text
    return None


def first_number(*values: Any) -> Optional[float]:
    for value in values:
        number = to_number(value)
        if number is not None:
            return number
    return None


def _num(*values: Any) -> float:
    """first_number(...) defaulting to 0.0 (mirrors the app's `?? 0`)."""
    n = first_number(*values)
    return n if n is not None else 0.0


def normalize_text(text: str) -> str:
    text = text.replace("\x00", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_address_lines(value: Optional[str]) -> list[str]:
    if not value:
        return []
    parts = re.split(r"\r?\n|,", value)
    return [p.strip() for p in parts if p.strip()]


# ------------------------------------------------------------- payload unwrap


def extract_data(payload: Any) -> dict:
    if not isinstance(payload, dict):
        return {}
    for key in ("data", "result", "parsed", "parsedData", "extracted", "form16"):
        inner = payload.get(key)
        if isinstance(inner, dict):
            return inner
    return payload


# ------------------------------------------------------------------ normalize


def normalize_ocr_response(payload: Any, file_name: str) -> dict:
    data = extract_data(payload)

    part_a = as_record(data.get("part_a")) or as_record(data.get("partA")) or as_record(
        data.get("form16_part_a")
    )
    part_b = as_record(data.get("part_b")) or as_record(data.get("partB")) or as_record(
        data.get("form16_part_b")
    )

    salary_details = get_record(
        part_b, "details_of_salary_paid_and_any_other_income_and_tax_deducted"
    ) or as_record(
        data.get("details_of_salary_paid_and_any_other_income_and_tax_deducted")
    )
    gross_salary_block = get_record(salary_details, "gross_salary")
    exemptions_block = get_record(
        salary_details, "less_allowances_to_the_extent_exempt_under_section_10"
    )
    section16_block = get_record(salary_details, "less_deductions_under_section_16")
    chapter_via_block = get_record(salary_details, "deductions_under_chapter_vi_a")
    other_income_block = get_record(
        salary_details,
        "add_any_other_income_reported_by_the_employee_under_as_per_section_192_2b",
    )
    tds_summary = get_record(part_a, "summary_of_amount_paid_or_credited_and_tax_deducted")
    tds_summary_total = get_record(tds_summary, "total")

    raw_text = normalize_text(
        first_text(
            data.get("rawText"),
            data.get("raw_text"),
            data.get("text"),
            data.get("extractedText"),
            data.get("extracted_text"),
            data.get("form16Text"),
            data.get("form16_text"),
            part_a.get("rawText") if part_a else None,
            part_b.get("rawText") if part_b else None,
        )
        or ""
    )

    employee_name = first_text(
        data.get("employeeName"),
        data.get("employee_name"),
        part_a.get("name_of_employee") if part_a else None,
        part_a.get("name_of_employee_of_the_employee") if part_a else None,
        read_first_line(
            part_a.get("name_and_address_of_the_employee_or_specified_senior_citizen")
        )
        if part_a
        else None,
    )

    employee_pan = first_text(
        data.get("employeePan"),
        data.get("employee_pan"),
        data.get("pan"),
        data.get("panNumber"),
        data.get("pan_number"),
        part_a.get("employee_pan") if part_a else None,
        part_a.get("pan_of_employee") if part_a else None,
        part_a.get("pan_of_the_employee_or_specified_senior_citizen") if part_a else None,
    )

    employer_pan = first_text(
        data.get("employerPan"),
        data.get("employer_pan"),
        part_a.get("pan_of_the_deductor") if part_a else None,
        part_a.get("employer_pan") if part_a else None,
    )

    employer_tan = first_text(
        data.get("tan"),
        data.get("tan_number"),
        data.get("employerTan"),
        data.get("employer_tan"),
        part_a.get("tan_of_the_deductor") if part_a else None,
        part_a.get("tan") if part_a else None,
    )

    assessment_year = first_text(
        data.get("assessmentYear"),
        data.get("assessment_year"),
        data.get("ay"),
        data.get("financialYear"),
        data.get("financial_year"),
        part_a.get("assesment_year") if part_a else None,
        part_a.get("assessment_year") if part_a else None,
    )

    employer_name = first_text(
        data.get("employerName"),
        data.get("employer_name"),
        data.get("employer"),
        data.get("companyName"),
        data.get("company_name"),
        part_a.get("name_and_address_of_the_employer_or_specified_bank") if part_a else None,
    )

    employer_address = first_text(data.get("employerAddress"), data.get("employer_address"))
    employee_address = first_text(
        data.get("employeeAddress"),
        data.get("employee_address"),
        part_a.get("address_of_the_employee") if part_a else None,
    )
    phone = first_text(
        data.get("phone"),
        data.get("employerPhone"),
        data.get("employer_phone"),
        data.get("mobile"),
        data.get("employeePhone"),
        data.get("employee_phone"),
    )

    gross_salary = _num(
        data.get("grossSalary"),
        data.get("gross_salary"),
        data.get("total_salary"),
        data.get("salary_gross"),
        data.get("salary"),
        data.get("gross_income"),
        gross_salary_block.get("total") if gross_salary_block else None,
    )

    salary_chargeable = _num(
        data.get("salaryChargeable"),
        data.get("salary_chargeable"),
        data.get("income_chargeable"),
        data.get("chargeable_salary"),
        data.get("income_from_salary"),
        to_number_at(salary_details.get("income_chargeable_under_the_head_salaries"), 1)
        if salary_details
        else None,
        to_number_at(
            salary_details.get(
                "total_amount_of_salary_received_from_current_employer_1d_2h"
            ),
            1,
        )
        if salary_details
        else None,
    )

    gross_total_income = _num(
        data.get("grossTotalIncome"),
        data.get("gross_total_income"),
        to_number_at(salary_details.get("gross_total_income"), 1) if salary_details else None,
        to_number_at(salary_details.get("gross_total_income_before_deductions"), 1)
        if salary_details
        else None,
    )

    house_property_income = _num(
        data.get("housePropertyIncome"),
        data.get("house_property_income"),
        data.get("income_from_house_property"),
        to_number_at(
            other_income_block.get(
                "income_or_admissible_loss_from_house_property_reported_by_employee_offered_for_tds"
            ),
            0,
        )
        if other_income_block
        else None,
    )

    standard_deduction = _num(
        data.get("standardDeduction"),
        data.get("standard_deduction"),
        data.get("deduction_standard"),
        to_number_at(section16_block.get("standard_deduction_under_section_16_ia"), 0)
        if section16_block
        else None,
    )

    other_income = _num(
        data.get("otherIncome"),
        data.get("other_income"),
        data.get("income_from_other_sources"),
        to_number_at(
            other_income_block.get("income_under_the_head_other_sources_offered_for_tds"), 0
        )
        if other_income_block
        else None,
        to_number_at(
            salary_details.get("total_amount_of_other_income_reported_by_the_employee"), 1
        )
        if salary_details
        else None,
    )

    section80c = _num(
        data.get("section80C"),
        data.get("section_80c"),
        data.get("deduction80C"),
        get_nested_number(
            chapter_via_block,
            "deduction_in_respect_of_life_insurance_premia_pf_etc_under_section_80c",
            "deductible_amount",
        ),
    )

    section80d = _num(
        data.get("section80D"),
        data.get("section_80d"),
        data.get("deduction80D"),
        get_nested_number(
            chapter_via_block,
            "deduction_in_respect_of_health_insurance_premia_under_section_80d",
            "deductible_amount",
        ),
    )

    section80ccd1b = _num(
        data.get("section80CCD1B"),
        data.get("section_80ccd1b"),
        data.get("deduction80CCD1B"),
        get_nested_number(
            chapter_via_block,
            "deductions_in_respect_of_amount_paid_or_deposited_to_notified_pension_scheme_under_section_80ccd_1b",
            "deductible_amount",
        ),
    )

    chapter_via_total = _num(
        data.get("chapterVIDeductionTotal"),
        data.get("chapter_vi_a_total"),
        salary_details.get("aggregate_of_deductible_amount_under_chapter_vi_A")
        if salary_details
        else None,
        get_nested_number(
            chapter_via_block,
            "total_amount_deductible_under_any_other_provisions_of_chapter_vi_a",
            "deductible_amount",
        ),
    )

    taxable_income = _num(
        data.get("taxableIncome"),
        data.get("taxable_income"),
        salary_details.get("total_taxable_income") if salary_details else None,
    )

    tax_on_total_income = _num(
        data.get("taxOnTotalIncome"),
        data.get("tax_on_total_income"),
        salary_details.get("tax_on_total_income") if salary_details else None,
    )

    rebate_87a = _num(
        data.get("rebateUnderSection87A"),
        data.get("rebate_under_section_87a"),
        salary_details.get("rebate_under_section_87a_if_applicable") if salary_details else None,
    )

    surcharge = _num(
        data.get("surcharge"),
        salary_details.get("surcharge_wherever_applicable") if salary_details else None,
    )

    cess = _num(
        data.get("healthAndEducationCess"),
        data.get("health_and_education_cess"),
        salary_details.get("health_and_education_cess") if salary_details else None,
    )

    tax_payable = _num(
        data.get("taxPayable"),
        data.get("tax_payable"),
        salary_details.get("tax_payable") if salary_details else None,
    )

    net_tax_payable = _num(
        data.get("netTaxPayable"),
        data.get("net_tax_payable"),
        salary_details.get("net_tax_payable") if salary_details else None,
    )

    total_tax_deducted = _num(
        data.get("totalTaxDeducted"),
        data.get("total_tax_deducted"),
        tds_summary_total.get("total_amt_of_tax_deducted") if tds_summary_total else None,
        tds_summary_total.get("total_amt_of_tax_deducted_at_source")
        if tds_summary_total
        else None,
        tds_summary_total.get("total_amt_of_tax_deducted_at_source_from_salary")
        if tds_summary_total
        else None,
    )

    total_tax_deposited = _num(
        data.get("totalTaxDeposited"),
        data.get("total_tax_deposited"),
        tds_summary_total.get("total_amt_of_tax_deposited_or_remitted")
        if tds_summary_total
        else None,
    )

    regime_raw = read_text(data.get("taxRegime"))
    opting = (
        read_text(salary_details.get("whether_opting_for_taxation_us_115bac"))
        if salary_details
        else None
    )
    if regime_raw in ("old", "new"):
        tax_regime: Optional[str] = regime_raw
    elif opting == "Yes":
        tax_regime = "new"
    elif opting == "No":
        tax_regime = "old"
    else:
        tax_regime = None

    warnings_raw = data.get("warnings")
    warnings: list[str] = []
    if isinstance(warnings_raw, list):
        for w in warnings_raw:
            t = read_text(w)
            if t:
                warnings.append(t)

    detected = [
        employee_name,
        employee_pan,
        employer_pan,
        employer_tan,
        assessment_year,
        employer_name,
        gross_salary if gross_salary > 0 else None,
        salary_chargeable if salary_chargeable > 0 else None,
        gross_total_income if gross_total_income > 0 else None,
        taxable_income if taxable_income > 0 else None,
        tax_on_total_income if tax_on_total_income > 0 else None,
        total_tax_deducted if total_tax_deducted > 0 else None,
        net_tax_payable if net_tax_payable > 0 else None,
        section80c if section80c > 0 else None,
        section80d if section80d > 0 else None,
        section80ccd1b if section80ccd1b > 0 else None,
    ]
    detected_count = len([x for x in detected if x])

    if not raw_text and detected_count == 0:
        warnings.append(
            "The OCR service did not return parseable Form 16 data. "
            "Please verify the parse_form16 response mapping."
        )

    confidence = "high" if detected_count >= 5 else "medium" if detected_count >= 3 else "low"

    # The OCR extractor emits a full, cleanly-keyed part_a/part_b breakdown. Pass it
    # through so the app can render every row. The table-parser path uses a different
    # shape, so we only forward the OCR one (gated on extraction_method).
    is_ocr = read_text(data.get("extraction_method")) == "ocr"
    part_a_out = data.get("part_a") if is_ocr and isinstance(data.get("part_a"), dict) else None
    part_b_out = data.get("part_b") if is_ocr and isinstance(data.get("part_b"), dict) else None

    return {
        "fileName": file_name,
        "assessmentYear": assessment_year,
        "employerName": employer_name,
        "employerAddress": employer_address,
        "employerTan": employer_tan,
        "employerPan": employer_pan,
        "employeeName": employee_name,
        "employeeAddress": employee_address,
        "employeePan": employee_pan,
        "phone": phone,
        "grossSalary": gross_salary,
        "grossTotalIncome": gross_total_income,
        "salaryChargeable": salary_chargeable,
        "standardDeduction": standard_deduction,
        "housePropertyIncome": house_property_income,
        "otherIncome": other_income,
        "section80C": section80c,
        "section80D": section80d,
        "section80CCD1B": section80ccd1b,
        "chapterViaTotal": chapter_via_total,
        "taxableIncome": taxable_income,
        "taxOnTotalIncome": tax_on_total_income,
        "rebateUnderSection87A": rebate_87a,
        "surcharge": surcharge,
        "healthAndEducationCess": cess,
        "taxPayable": tax_payable,
        "netTaxPayable": net_tax_payable,
        "totalTaxDeducted": total_tax_deducted,
        "totalTaxDeposited": total_tax_deposited,
        "taxRegime": tax_regime,
        "confidence": confidence,
        "warnings": warnings,
        "partA": part_a_out,
        "partB": part_b_out,
        "rawText": raw_text,
    }
