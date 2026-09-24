#!/usr/bin/env python3
"""Builds docs/test_cases.xlsx: >=20 UiPath/API test cases spanning the happy
path, business exceptions, and system exceptions, per docs/SDD.md sec 5."""
from openpyxl import Workbook

COLUMNS = ["test_id", "scenario", "input", "expected_result", "exception_type", "result"]

rows = [
    ("TC01", "True lookup claim, high agreement",
     "claim='the total fee for MCA semester 1 is 95000', table=fee_structure.csv",
     "verdict=TRUE, answered (agreement>=lambda), HTTP 200", "None", ""),
    ("TC02", "False lookup claim (near-miss), high agreement",
     "claim='the total fee for MCA semester 1 is 99000', table=fee_structure.csv",
     "verdict=FALSE, answered, HTTP 200", "None", ""),
    ("TC03", "True count claim",
     "claim='there are 10 rows in the fee structure table', table=fee_structure.csv",
     "verdict=TRUE, answered, HTTP 200", "None", ""),
    ("TC04", "True aggregation claim (average)",
     "claim='the average sgpa across all students is below 8', table=semester_results.csv",
     "verdict=TRUE, answered, HTTP 200", "None", ""),
    ("TC05", "False comparison/eligibility claim",
     "claim='aatir khan is eligible for the scholarship', table=scholarship_eligibility.csv",
     "verdict=FALSE, answered, HTTP 200", "None", ""),
    ("TC06", "Empty claim string",
     "claim='', table=fee_structure.csv",
     "HTTP 400, detail='claim is missing or empty'", "Business", ""),
    ("TC07", "Missing table file",
     "claim='x', table_path='does_not_exist.csv'",
     "HTTP 422, detail='table_path does not exist...'", "Business", ""),
    ("TC08", "Malformed / unparsable CSV (ragged rows)",
     "claim='this table cannot be parsed', table=malformed_table.csv",
     "HTTP 422, detail='could not parse table: Error tokenizing data...' (pandas ParserError caught)", "Business", ""),
    ("TC09", "Neither table_path nor table_csv given",
     "claim='x' only, no table field",
     "HTTP 400, detail='one of table_path or table_csv is required'", "Business", ""),
    ("TC10", "Duplicate claim_id in batch",
     "two rows in claims.xlsx share claim_id=C010",
     "Dispatcher: second row rejected by ValidateClaim.xaml ('duplicate claim_id'); Orchestrator Reference collision as second line of defense", "Business", ""),
    ("TC11", "LLM unavailable (no API key)",
     "ANTHROPIC_API_KEY unset, POST /verify with a valid claim+table",
     "HTTP 503, detail='LLM unavailable: ANTHROPIC_API_KEY is not set'", "System", ""),
    ("TC12", "API unreachable from UiPath",
     "Stop the uvicorn process, run CallVerifierAPI.xaml",
     "HTTP Request activity throws connection error -> Retry Scope retries up to ApiRetryCount -> System exception after exhaustion", "System", ""),
    ("TC13", "LLM call exhausts internal retries (simulated rate limiting)",
     "Force repeated 429 from Anthropic API (mock)",
     "src/llm_client.py exhausts max_retries -> raises -> API returns 503 -> UiPath Retry Scope engages", "System", ""),
    ("TC14", "Low execution agreement -> abstain",
     "Ambiguous claim where K=5 checks disagree (e.g. contested column name)",
     "verdict=ABSTAIN, sent_to_review=true, row appended to results/review_queue.xlsx with status=Pending", "None (expected abstention)", ""),
    ("TC15", "All K checks invalid JSON -> UNVERIFIABLE",
     "Claim phrased so the LLM cannot produce parseable JSON checks (simulated by malformed prompt)",
     "verdict=ABSTAIN, reason='no valid executed check (UNVERIFIABLE)', routed to review", "None (expected abstention)", ""),
    ("TC16", "Health check while LLM key present",
     "GET /health with ANTHROPIC_API_KEY set",
     "HTTP 200, {status: ok, llm_available: true, model: <configured model>}", "None", ""),
    ("TC17", "Health check while LLM key absent",
     "GET /health with ANTHROPIC_API_KEY unset",
     "HTTP 200, {status: ok, llm_available: false, ...} (health itself never fails)", "None", ""),
    ("TC18", "Uncalibrated fallback threshold",
     "POST /verify before results/conformal_thresholds.json exists",
     "Only unanimous-agreement (score=1.0) claims are answered; all others abstain with reason mentioning 'uncalibrated fallback threshold'", "None (expected conservative behaviour)", ""),
    ("TC19", "Review ticket escalation after N days",
     "A Pending row in review_queue.xlsx with created_at older than EscalationDays",
     "Escalate.xaml sends supervisor email and updates status to Escalated; row is not re-escalated on the next run", "None", ""),
    ("TC20", "Inline table_csv path (no table_path)",
     "POST /verify with table_csv='a,b\\n1,2\\n3,4' and a matching claim",
     "HTTP 200, parsed via load_generic_table(io.StringIO(...)), normal verdict flow", "None", ""),
    ("TC21", "Zero-row / zero-column table",
     "table_csv='' (empty string) treated as missing per current validation, OR a header-only CSV with 0 data rows",
     "HTTP 422, detail='table parsed to zero rows/columns' for header-only case; HTTP 400 if table_csv is the empty string (falls under 'missing table reference')", "Business", ""),
    ("TC22", "Business exception is not retried",
     "POST /verify returns 422; CallVerifierAPI.xaml Retry Scope condition evaluated",
     "Retry Scope does NOT retry (BusinessRuleException excluded from retry condition); transaction fails immediately as Business", "Business", ""),
    ("TC23", "End-to-end batch run via Dispatcher + Performer",
     "Full input/claims.xlsx (16 rows, 4 deliberately bad) through Dispatcher then Performer",
     "12 valid rows reach CNV_Claims queue; 4 bad rows logged as business exceptions at dispatch; Performer produces a mix of Successful and review-queue outcomes matching TC01-TC10 expectations", "Mixed", ""),
]

wb = Workbook()
ws = wb.active
ws.title = "test_cases"
ws.append(COLUMNS)
for r in rows:
    ws.append(list(r))
for col_letter, width in zip("ABCDEF", [8, 34, 55, 55, 14, 12]):
    ws.column_dimensions[col_letter].width = width
wb.save("docs/test_cases.xlsx")
print(f"Wrote docs/test_cases.xlsx with {len(rows)} test cases")
