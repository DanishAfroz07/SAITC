"""Generates the 13-document PDF corpus and corpus_manifest.json from
scripts/corpus_content.py.

Why this script exists: this project was built from the assignment's PDFs as
extracted text pasted into a conversation, not from the original PDF files on
disk. Rendering that same text back into real PDFs gives the ingestion
pipeline (which reads actual PDF files via PyMuPDF, per the assignment) real
input to run against, without waiting on locating the original files.

If you have the original assignment PDFs, you can use them instead: drop
them into data/documents/ with the same file names as corpus_manifest.json
expects, and skip this script entirely - app/ingestion/parser.py reads
metadata from the manifest either way, so nothing else changes.

Usage: python scripts/build_corpus.py
"""
import json
import sys
from pathlib import Path

from fpdf import FPDF

sys.path.insert(0, str(Path(__file__).resolve().parent))
from corpus_content import DOCUMENTS, MANIFEST  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DOCUMENTS_DIR = ROOT / "data" / "documents"
MANIFEST_PATH = ROOT / "data" / "corpus_manifest.json"


def _render_pdf(doc: dict, out_path: Path) -> None:
    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.set_margins(left=10, top=15, right=10)
    pdf.add_page()

    pdf.set_font("Helvetica", "B", 16)
    pdf.multi_cell(0, 9, doc["title"])
    pdf.ln(2)

    pdf.set_font("Helvetica", "", 10)
    header = (
        f"Document ID: {doc['document_id']}    Version: {doc['version']}\n"
        f"Effective Date: {doc['effective_date']}    Owner: {doc['owner']}\n"
        f"Classification: {doc['classification']}    "
        f"Supersedes: {doc['supersedes'] or 'N/A'}"
    )
    pdf.multi_cell(0, 6, header)
    pdf.ln(4)

    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, doc["body"])

    pdf.output(str(out_path))


def main() -> None:
    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)

    for doc in DOCUMENTS:
        out_path = DOCUMENTS_DIR / doc["file"]
        _render_pdf(doc, out_path)
        print(f"Wrote {out_path.relative_to(ROOT)}")

    MANIFEST_PATH.write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    print(f"Wrote {MANIFEST_PATH.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
