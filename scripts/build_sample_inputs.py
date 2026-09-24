#!/usr/bin/env python3
"""Builds input/claims.xlsx: the sample UiPath bot input. Includes 3 college
tables x (true, false, near-miss) claims, plus deliberately bad rows for
exception-handling tests: missing table, empty claim, malformed CSV,
duplicate claim_id."""
from openpyxl import Workbook

rows = [
    # claim_id, claim, table_file
    ("C001", "the total fee for MCA semester 1 is 95000", "fee_structure.csv"),
    ("C002", "the total fee for MCA semester 1 is 99000", "fee_structure.csv"),  # false / near-miss
    ("C003", "the tuition fee for BTech CSE semester 1 is 80000", "fee_structure.csv"),
    ("C004", "there are 10 rows in the fee structure table", "fee_structure.csv"),
    ("C005", "prafful gupta has a cgpa of 8.9 in semester 3", "semester_results.csv"),
    ("C006", "prafful gupta has a cgpa of 9.9 in semester 3", "semester_results.csv"),  # false
    ("C007", "karan mehta has 3 backlogs", "semester_results.csv"),
    ("C008", "the average sgpa across all students is below 8", "semester_results.csv"),  # true (mean ~= 7.93)
    ("C009", "rohit verma is eligible for the scholarship", "scholarship_eligibility.csv"),
    ("C010", "aatir khan is eligible for the scholarship", "scholarship_eligibility.csv"),  # false
    ("C011", "neha sharma has a family income of 250000", "scholarship_eligibility.csv"),
    ("C012", "neha sharma has a family income of 260000", "scholarship_eligibility.csv"),  # near-miss
    # deliberately bad rows for exception-handling tests
    ("C013", "the total fee for MBA semester 1 is 135000", "does_not_exist.csv"),  # missing table
    ("C014", "", "fee_structure.csv"),  # empty claim
    ("C015", "this table cannot be parsed", "malformed_table.csv"),  # malformed CSV
    ("C010", "duplicate claim id test case", "scholarship_eligibility.csv"),  # duplicate claim_id (reuses C010)
]

wb = Workbook()
ws = wb.active
ws.title = "claims"
ws.append(["claim_id", "claim", "table_file"])
for r in rows:
    ws.append(list(r))
wb.save("input/claims.xlsx")
print(f"Wrote input/claims.xlsx with {len(rows)} rows (including 4 deliberately bad rows)")
