"""FastAPI wrapper around the numeric-verification pipeline, built to be
driven by a UiPath REFramework Performer (see docs/SDD.md). Run with:

    uvicorn api.server:app --host 127.0.0.1 --port 8008

Contract (docs/SDD.md "CallVerifierAPI.xaml" depends on this exactly):
  POST /verify  -> 200 {verdict, agreement_score, executed_checks,
                         computed_values, reason, latency_ms, claim_id}
                -> 400 bad input (missing claim / no table reference)
                -> 422 unparsable table (bad path, malformed CSV, empty table)
                -> 503 LLM unavailable (no API key, or LLM calls exhausted retries)
  GET  /health  -> 200 {status, llm_available, model}
"""
from __future__ import annotations
import io
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from src.conformal import apply_threshold
from src.llm_client import LLMClient, load_config
from src.review_queue import append_review_row
from src.table_utils import load_generic_table
from src.verifier import verify_claim_df

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    handlers=[
        logging.FileHandler(Path("results/logs/api.log"), encoding="utf-8"),
        logging.StreamHandler(),
    ],
)
Path("results/logs").mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("verifier-api")

app = FastAPI(title="Certified Numeric Verification API", version="1.0")
# Local demo frontend (static HTML opened via file:// or a local static server)
# needs to call this API cross-origin; this is a local-only dev server, not a
# public deployment, so an open CORS policy is appropriate here.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
)

CONFIG = load_config()
CLIENT = LLMClient(CONFIG)
DEFAULT_MODEL = CONFIG["models"]["default"]
DEFAULT_K = CONFIG["experiment"]["k_checks"]
DEFAULT_TEMP = CONFIG["models"]["available"][0]["temperature_checks"]
REVIEW_QUEUE_PATH = str(Path(CONFIG["paths"]["results_dir"]) / "review_queue.xlsx")
THRESHOLDS_PATH = Path(CONFIG["paths"]["results_dir"]) / "conformal_thresholds.json"


def _load_thresholds() -> dict:
    if THRESHOLDS_PATH.exists():
        import json
        return json.loads(THRESHOLDS_PATH.read_text())
    return {}


class VerifyRequest(BaseModel):
    claim: str
    table_path: Optional[str] = None
    table_csv: Optional[str] = None
    claim_id: Optional[str] = None
    table_id: Optional[str] = None
    alpha: float = Field(default=0.05, description="Target risk level; must be one of the calibrated alphas.")
    model: Optional[str] = None


class VerifyResponse(BaseModel):
    claim_id: str
    verdict: str
    agreement_score: float
    executed_checks: list
    computed_values: list
    reason: str
    latency_ms: float
    sent_to_review: bool


@app.get("/health")
async def health():
    return {"status": "ok", "llm_available": CLIENT.available(), "model": DEFAULT_MODEL}


@app.post("/verify", response_model=VerifyResponse)
async def verify(req: VerifyRequest):
    start = time.time()
    claim_id = req.claim_id or str(uuid.uuid4())
    table_id = req.table_id or (Path(req.table_path).stem if req.table_path else "inline_table")

    if not req.claim or not req.claim.strip():
        raise HTTPException(status_code=400, detail="`claim` is missing or empty")
    if not req.table_path and not req.table_csv:
        raise HTTPException(status_code=400, detail="one of `table_path` or `table_csv` is required")

    try:
        if req.table_path:
            p = Path(req.table_path)
            if not p.exists():
                raise HTTPException(status_code=422, detail=f"table_path does not exist: {req.table_path}")
            df = load_generic_table(str(p))
        else:
            df = load_generic_table(io.StringIO(req.table_csv))
        if df.shape[1] == 0 or df.shape[0] == 0:
            raise HTTPException(status_code=422, detail="table parsed to zero rows/columns")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"could not parse table: {e}")

    if not CLIENT.available():
        raise HTTPException(status_code=503, detail="LLM unavailable: ANTHROPIC_API_KEY is not set")

    model = req.model or DEFAULT_MODEL
    try:
        result = await verify_claim_df(CLIENT, model, req.claim, df, k=DEFAULT_K,
                                        temperature=DEFAULT_TEMP, method="ours")
    except Exception as e:
        logger.exception("LLM call failed for claim_id=%s", claim_id)
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")

    agreement = result.get("agreement_score", 0.0)
    verdict = result["verdict"]
    thresholds = _load_thresholds()
    lam = thresholds.get(str(req.alpha))
    computed_values = [c["result"].get("computed_value") for c in result.get("executed_checks", [])
                        if c.get("result", {}).get("ok")]

    if lam is None:
        # not yet calibrated -- conservative fallback: only answer on unanimous agreement
        lam = 1.0
        reason_suffix = " (uncalibrated fallback threshold: requires full agreement)"
    else:
        reason_suffix = f" (alpha={req.alpha}, calibrated lambda={lam:.3f})"

    answered = bool(apply_threshold([agreement], lam)[0]) if verdict != "UNVERIFIABLE" else False
    sent_to_review = not answered

    if answered:
        final_verdict = verdict
        reason = "answered: agreement >= calibrated threshold" + reason_suffix
    else:
        final_verdict = "ABSTAIN"
        reason = ("abstained: agreement below calibrated threshold" + reason_suffix
                  if verdict != "UNVERIFIABLE" else "abstained: no valid executed check (UNVERIFIABLE)")
        append_review_row(REVIEW_QUEUE_PATH, claim_id, req.claim, table_id, verdict,
                           agreement, result.get("executed_checks", []), reason)

    latency_ms = (time.time() - start) * 1000
    logger.info("claim_id=%s table_id=%s verdict=%s agreement=%.3f answered=%s latency_ms=%.1f",
                claim_id, table_id, final_verdict, agreement, answered, latency_ms)

    return VerifyResponse(
        claim_id=claim_id, verdict=final_verdict, agreement_score=agreement,
        executed_checks=result.get("executed_checks", []), computed_values=computed_values,
        reason=reason, latency_ms=latency_ms, sent_to_review=sent_to_review,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request, exc):
    logger.exception("unhandled error")
    return JSONResponse(status_code=500, content={"detail": f"internal error: {exc}"})
