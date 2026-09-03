"""Runs the pipeline against evaluation/questions.json and writes
results.json + a human-readable results.md table.

Requires Ollama running locally with both configured models pulled, and the
corpus already ingested (`python -m app.main ingest`). See README for how
this would be extended into a more rigorous evaluation harness.
"""
import json
import time
from pathlib import Path

from app.wiring import build_rag_pipeline

QUESTIONS_PATH = Path(__file__).parent / "questions.json"
RESULTS_JSON_PATH = Path(__file__).parent / "results.json"
RESULTS_MD_PATH = Path(__file__).parent / "results.md"


def main() -> None:
    questions = json.loads(QUESTIONS_PATH.read_text(encoding="utf-8"))
    pipeline = build_rag_pipeline()

    results = []
    for item in questions:
        start = time.perf_counter()
        answer = pipeline.answer(item["question"])
        elapsed = time.perf_counter() - start
        results.append(
            {
                "id": item["id"],
                "question": item["question"],
                "answer": answer.text,
                "outcome": answer.outcome.value,
                "retrieval_confidence": answer.retrieval_confidence.value,
                "citations": [c.document_id for c in answer.citations],
                "elapsed_seconds": round(elapsed, 2),
            }
        )
        print(f"[{item['id']}] {item['question']} -> {answer.outcome.value} ({elapsed:.1f}s)")

    RESULTS_JSON_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")

    lines = [
        "| # | Question | Outcome | Confidence | Citations | Answer |",
        "|---|---|---|---|---|---|",
    ]
    for r in results:
        answer_preview = r["answer"].replace("\n", " ").replace("|", "/")[:220]
        lines.append(
            f"| {r['id']} | {r['question']} | {r['outcome']} | {r['retrieval_confidence']} | "
            f"{', '.join(r['citations'])} | {answer_preview} |"
        )
    RESULTS_MD_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nWrote {RESULTS_JSON_PATH} and {RESULTS_MD_PATH}")


if __name__ == "__main__":
    main()
