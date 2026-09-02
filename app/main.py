"""Single entrypoint for the whole app.

- `uvicorn app.main:app --reload` serves the FastAPI HTTP API.
- `python -m app.main ingest` runs ingestion once from the CLI.
- `python -m app.main chat` opens an interactive question/answer REPL.

Both CLI commands and the API call the same app.wiring composition root, so
there is exactly one code path for "ask a question" and one for "ingest".
"""
import argparse
import logging

from fastapi import FastAPI

from app.api.routes import router
from app.wiring import build_ingestion_pipeline, build_rag_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Cerulean Systems RAG Assistant")
app.include_router(router)


def _run_ingest() -> None:
    report = build_ingestion_pipeline().run()
    print(
        f"Ingested {report.documents_processed} documents into {report.chunks_created} chunks "
        f"({report.table_chunks} table chunks) in {report.elapsed_seconds:.2f}s"
    )


def _run_chat() -> None:
    pipeline = build_rag_pipeline()
    print("Cerulean Systems assistant. Type a question, or 'exit' to quit.")
    while True:
        try:
            question = input("\n> ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not question or question.lower() in {"exit", "quit"}:
            break
        answer = pipeline.answer(question)
        print(f"\n{answer.text}")
        if answer.citations:
            sources = ", ".join(f"[{c.document_id}]" for c in answer.citations)
            print(f"\nSources: {sources}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cerulean Systems RAG assistant CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("ingest", help="Ingest the document corpus into the vector store")
    subparsers.add_parser("chat", help="Ask the assistant questions interactively")
    args = parser.parse_args()

    if args.command == "ingest":
        _run_ingest()
    elif args.command == "chat":
        _run_chat()


if __name__ == "__main__":
    main()
