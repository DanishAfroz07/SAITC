"""Entrypoint. Run as a module from the project root:

  python -m app.main          starts the HTTP API (default)
  python -m app.main ingest   ingests the full corpus once, via the CLI
  python -m app.main chat     interactive question/answer REPL

(`python app/main.py` does NOT work - `app` only resolves as a package when
started with `-m` from the project root.)
"""
import argparse
import logging

import uvicorn
from fastapi import FastAPI

from app.api.controllers import document_controller, health_controller, ingest_controller, query_controller
from app.config import settings
from app.models import RetrievalConfidence
from app.wiring import build_ingestion_pipeline, build_rag_pipeline

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

app = FastAPI(title="Cerulean Systems RAG Assistant")
app.include_router(health_controller.router)
app.include_router(query_controller.router)
app.include_router(ingest_controller.router)
app.include_router(document_controller.router)


def _run_serve() -> None:
    print(f"Starting API on http://{settings.api_host}:{settings.api_port} - docs at /docs")
    uvicorn.run(app, host=settings.api_host, port=settings.api_port)


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
        if answer.retrieval_confidence is not RetrievalConfidence.NOT_APPLICABLE:
            print(f"Retrieval confidence: {answer.retrieval_confidence.value}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Cerulean Systems RAG assistant")
    subparsers = parser.add_subparsers(dest="command")
    subparsers.add_parser("serve", help="Start the HTTP API (also the default with no command)")
    subparsers.add_parser("ingest", help="Ingest the full document corpus into the vector store")
    subparsers.add_parser("chat", help="Ask the assistant questions interactively")
    args = parser.parse_args()

    if args.command == "ingest":
        _run_ingest()
    elif args.command == "chat":
        _run_chat()
    else:
        _run_serve()


if __name__ == "__main__":
    main()
