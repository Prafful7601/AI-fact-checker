"""Streamlit demo -- secondary to the UiPath automation, which is the primary
deliverable (see docs/PDD.md, docs/SDD.md). Two tabs:
1. Reviewer Dashboard: reads results/review_queue.xlsx (the same file the
   UiPath Performer writes to / reads from) so a human reviewer can see what
   is Pending/Escalated without opening Excel.
2. Live Verifier: an ad-hoc "upload a table, type a claim" tester that calls
   the same POST /verify endpoint UiPath calls, for demos and debugging.

Run: streamlit run demo/app.py   (start `uvicorn api.server:app` separately
for the Live Verifier tab to work.)
"""
import io
import json
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
REVIEW_QUEUE_PATH = ROOT / "results" / "review_queue.xlsx"
API_BASE = st.sidebar.text_input("Verifier API base URL", "http://127.0.0.1:8008")

EXAMPLE_TABLES = {
    "Fee structure": ROOT / "input" / "tables" / "fee_structure.csv",
    "Semester results": ROOT / "input" / "tables" / "semester_results.csv",
    "Scholarship eligibility": ROOT / "input" / "tables" / "scholarship_eligibility.csv",
}
EXAMPLE_CLAIMS = {
    "Fee structure": [
        ("True", "the total fee for MCA semester 1 is 95000"),
        ("False", "the total fee for MCA semester 1 is 99000"),
        ("Near-miss (magnitude)", "the total fee for MCA semester 1 is 9500"),
    ],
    "Semester results": [
        ("True", "prafful gupta has a cgpa of 8.9 in semester 3"),
        ("False", "prafful gupta has a cgpa of 9.9 in semester 3"),
        ("Near-miss (digit swap)", "prafful gupta has a cgpa of 9.8 in semester 3"),
    ],
    "Scholarship eligibility": [
        ("True", "rohit verma is eligible for the scholarship"),
        ("False", "aatir khan is eligible for the scholarship"),
        ("Near-miss (off-by-one)", "neha sharma has a family income of 260000"),
    ],
}

st.set_page_config(page_title="Certified Numeric Verification", layout="wide")
st.title("Certified Numeric Verification -- Demo")
st.caption(
    "Primary deliverable is the UiPath REFramework automation (docs/PDD.md, "
    "docs/SDD.md). This app is a secondary reviewer dashboard + live tester."
)

tab_dash, tab_live = st.tabs(["📋 Reviewer Dashboard", "🔍 Live Verifier"])

with tab_dash:
    st.subheader("Human review queue")
    if not REVIEW_QUEUE_PATH.exists():
        st.info(
            "results/review_queue.xlsx does not exist yet -- it is created "
            "automatically the first time a claim abstains (see api/server.py)."
        )
    else:
        df = pd.read_excel(REVIEW_QUEUE_PATH)
        col1, col2, col3 = st.columns(3)
        col1.metric("Total tickets", len(df))
        col2.metric("Pending", int((df["status"] == "Pending").sum()) if "status" in df else 0)
        col3.metric("Resolved / Escalated", int((df["status"] != "Pending").sum()) if "status" in df else 0)
        status_filter = st.multiselect(
            "Filter by status", options=sorted(df["status"].unique()) if "status" in df else [],
            default=list(df["status"].unique()) if "status" in df else [],
        )
        shown = df[df["status"].isin(status_filter)] if "status" in df and status_filter else df
        st.dataframe(shown, use_container_width=True)
        if st.button("Refresh"):
            st.rerun()

with tab_live:
    st.subheader("Try a claim against a table")
    source = st.radio("Table source", ["Preloaded example", "Upload your own CSV"], horizontal=True)

    if source == "Preloaded example":
        table_name = st.selectbox("Example table", list(EXAMPLE_TABLES.keys()))
        table_path = EXAMPLE_TABLES[table_name]
        df_preview = pd.read_csv(table_path)
        st.dataframe(df_preview, use_container_width=True)
        example_pick = st.selectbox(
            "Example claim (true / false / near-miss)",
            [f"{label}: {claim}" for label, claim in EXAMPLE_CLAIMS[table_name]],
        )
        default_claim = example_pick.split(": ", 1)[1]
        table_csv_content = table_path.read_text()
    else:
        uploaded = st.file_uploader("Upload a CSV table", type=["csv"])
        if uploaded is not None:
            table_csv_content = uploaded.getvalue().decode("utf-8")
            st.dataframe(pd.read_csv(io.StringIO(table_csv_content)), use_container_width=True)
        else:
            table_csv_content = None
        default_claim = ""

    claim = st.text_input("Claim", value=default_claim)
    alpha = st.select_slider("Target risk level (alpha)", options=[0.02, 0.05, 0.10], value=0.05)

    if st.button("Verify", type="primary"):
        if not table_csv_content or not claim.strip():
            st.error("Provide both a table and a non-empty claim.")
        else:
            try:
                resp = requests.post(
                    f"{API_BASE}/verify",
                    json={"claim": claim, "table_csv": table_csv_content, "alpha": alpha},
                    timeout=120,
                )
            except requests.exceptions.ConnectionError:
                st.error(
                    "Could not reach the Verifier API. Start it with:\n\n"
                    "`uvicorn api.server:app --host 127.0.0.1 --port 8008`"
                )
                resp = None

            if resp is not None:
                if resp.status_code != 200:
                    st.error(f"API error {resp.status_code}: {resp.json().get('detail')}")
                else:
                    result = resp.json()
                    verdict = result["verdict"]
                    color = {"TRUE": "green", "FALSE": "red", "ABSTAIN": "orange"}.get(verdict, "gray")
                    st.markdown(f"### Verdict: :{color}[{verdict}]")
                    st.write(f"Agreement score: **{result['agreement_score']:.2f}**  |  "
                             f"Latency: {result['latency_ms']:.0f} ms")
                    if result["sent_to_review"]:
                        st.warning("⚠️ Sent to human review -- appended to results/review_queue.xlsx")
                    st.caption(result["reason"])

                    st.markdown("#### K generated checks and their executed results")
                    for i, chk in enumerate(result["executed_checks"], 1):
                        with st.expander(f"Check {i}"):
                            st.json(chk.get("check") or {"raw_text": chk.get("raw_text")})
                            st.write("Executed result:", chk.get("result"))
