from datetime import date

from app.ingestion.chunker import SectionChunker
from app.models import DocumentMetadata

METADATA = DocumentMetadata(
    document_id="TEST-001",
    title="Test Doc",
    version="1.0",
    effective_date=date(2026, 1, 1),
    owner="Test",
    classification="Internal",
    supersedes=None,
    file_name="test.pdf",
)

SAMPLE_TEXT = """1. Purpose
This is the purpose section explaining things in plain prose.

2. Approval thresholds
Value of commitment | Approval required
Up to SAR 5,000 | Line manager
SAR 5,001 to SAR 25,000 | Department head

Some closing prose after the table.
"""


def test_table_rows_are_kept_in_a_single_chunk():
    chunks = SectionChunker(max_chars=1000).chunk(SAMPLE_TEXT, METADATA)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "Line manager" in table_chunks[0].text
    assert "Department head" in table_chunks[0].text


def test_prose_and_table_are_separate_chunks_in_the_same_section():
    chunks = SectionChunker(max_chars=1000).chunk(SAMPLE_TEXT, METADATA)
    section_chunks = [c for c in chunks if c.section.startswith("2.")]
    assert any(c.is_table for c in section_chunks)
    assert any(not c.is_table for c in section_chunks)
    assert "Some closing prose" in "".join(c.text for c in section_chunks if not c.is_table)


def test_long_prose_is_split_into_more_than_one_chunk():
    paragraphs = "\n\n".join(f"Paragraph number {i} with some filler words to add length." for i in range(20))
    long_text = f"1. Purpose\n{paragraphs}\n"
    chunks = SectionChunker(max_chars=200).chunk(long_text, METADATA)
    assert len(chunks) > 1
    assert all(not c.is_table for c in chunks)


def test_document_header_before_first_heading_is_not_lost():
    text = "Some preamble line before any numbered section.\n\n1. Purpose\nBody text.\n"
    chunks = SectionChunker(max_chars=1000).chunk(text, METADATA)
    assert any("preamble" in c.text for c in chunks)


def test_stray_blank_line_inside_a_table_does_not_split_it():
    # Regression test: PDF text extraction can insert a spurious blank line
    # between a table's header row and its body rows (observed in the
    # generated corpus's SALES-PL-2026 "Implementation and services" table).
    # That must not be read as a paragraph break inside the table.
    text = (
        "5. Implementation and services\n\n"
        "Service | Price\n\n"
        "Standard onboarding | Included\n"
        "Data migration | SAR 9,500 per source system\n"
    )
    chunks = SectionChunker(max_chars=1000).chunk(text, METADATA)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "Service | Price" in table_chunks[0].text
    assert "Data migration" in table_chunks[0].text


def test_table_row_starting_with_a_number_is_not_misread_as_a_heading():
    # Regression test for a real bug found by tracing HR-PRO-011's
    # partial-month rule through the pipeline: a table row like "15 calendar
    # days or more | Counts as..." matches the numbered-heading pattern
    # (digits, whitespace, text) just as well as a genuine heading like
    # "4.2 Annual leave entitlement" does. Without excluding table rows,
    # such a row got misread as starting a new section, silently truncating
    # the table at exactly that row. Also affected HR-POL-002 ("5 years or
    # more | ...") and FIN-POL-007 ("6 hours or more | ...") in the real
    # corpus.
    text = (
        "4. Treatment of partial months\n"
        "A period of service that does not make up a whole month is treated as follows.\n"
        "Days served in the partial month | Treatment\n"
        "15 calendar days or more | Counts as one completed month, full accrual granted\n"
        "Fewer than 15 calendar days | Disregarded, no accrual granted for that month\n"
    )
    chunks = SectionChunker(max_chars=1000).chunk(text, METADATA)
    table_chunks = [c for c in chunks if c.is_table]
    assert len(table_chunks) == 1
    assert "15 calendar days or more" in table_chunks[0].text
    assert "Fewer than 15 calendar days" in table_chunks[0].text
