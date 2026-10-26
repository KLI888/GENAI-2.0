"""Answer-level evaluation against verified facts in data/answer_bank.json.

Retrieval coverage (app.evaluate) says the right page was found. This module checks
the *answer text*: whether it contains the verified facts, avoids known-wrong
strings, and cites a source. Items without verified facts are reported as
unscored and never counted as passes.

Run with: python -m app.evaluate_answers [--with-planner]
"""
import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BANK = ROOT / "data" / "answer_bank.json"
REPORT = ROOT / "data" / "answer_evaluation_report.json"

def score_answer(item, result):
    """Pure scoring of one answer result against one gold item."""
    text = (result.get("answer") or "")
    lowered = text.casefold()
    groups = item.get("must_include") or []
    missing = []
    for group in groups:
        if not any(str(option).casefold() in lowered for option in group):
            missing.append(group[0] if group else "")
    forbidden = [value for value in item.get("must_not_include") or [] if str(value).casefold() in lowered]
    cited = bool(result.get("sources"))
    fallback = bool(result.get("fallback"))
    scored = bool(groups)
    passed = scored and not missing and not forbidden and not fallback and cited
    return {
        "id": item["id"],
        "scored": scored,
        "passed": passed,
        "missing_facts": missing,
        "forbidden_found": forbidden,
        "cited": cited,
        "fallback": fallback,
        "generation": result.get("generation"),
    }

def summarize(results):
    scored = [r for r in results if r["scored"]]
    return {
        "total": len(results),
        "scored": len(scored),
        "unscored": len(results) - len(scored),
        "passed": sum(r["passed"] for r in scored),
        "pass_rate_scored": round(sum(r["passed"] for r in scored) / len(scored), 3) if scored else None,
        "cited_rate": round(sum(r["cited"] for r in results) / len(results), 3) if results else None,
        "fallback_rate": round(sum(r["fallback"] for r in results) / len(results), 3) if results else None,
        "generation_counts": dict(Counter(r["generation"] for r in results)),
    }

def evaluate(use_planner=False):
    from .main import answer  # imported lazily: loads the full app
    bank = json.loads(BANK.read_text(encoding="utf-8"))
    results = []
    for item in bank["items"]:
        result = answer(item["question"], None)
        results.append(score_answer(item, result))
    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "model_query_planner": use_planner,
        "summary": summarize(results),
        "results": results,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"Full report saved to {REPORT}")
    return report

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PCCOE answer-level evaluation.")
    parser.add_argument("--with-planner", action="store_true", help="Use model query planning (uses provider quota).")
    evaluate(use_planner=parser.parse_args().with_planner)
