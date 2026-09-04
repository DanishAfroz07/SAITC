from datetime import date

from app.generation.generator import AnswerGenerator
from app.models import Chunk, DocumentMetadata, EvidenceAssessment, EvidenceOutcome, RetrievedChunk


class _FakeChatClient:
    def __init__(self, response: str) -> None:
        self._response = response

    def complete(self, messages) -> str:
        return self._response


def _meta(doc_id: str, title: str, effective_date: date, supersedes: str | None) -> DocumentMetadata:
    return DocumentMetadata(
        document_id=doc_id,
        title=title,
        version="1.0",
        effective_date=effective_date,
        owner="Owner",
        classification="External",
        supersedes=supersedes,
        file_name=f"{doc_id}.pdf",
    )


def _rc(meta: DocumentMetadata, superseded: bool = False) -> RetrievedChunk:
    chunk = Chunk(
        chunk_id=f"{meta.document_id}-1",
        document_id=meta.document_id,
        section="1. Subscription plans",
        text="text",
        is_table=True,
        metadata=meta,
        superseded=superseded,
    )
    return RetrievedChunk(chunk=chunk, score=0.8)


def test_sufficient_answer_gets_a_supersession_note_when_an_old_value_is_in_context():
    # Regression test for a real bug (assignment Q4): the model was asked,
    # twice, in two separate prompt revisions, to mention a superseded
    # value alongside the current one - and skipped it anyway in live
    # testing even with the data right there in context. This guarantees
    # the fact gets stated regardless, built from metadata, not generated
    # text.
    old_meta = _meta("SALES-PL-2025", "Atlas Platform Price List", date(2025, 1, 1), "SALES-PL-2024 v1.2")
    new_meta = _meta("SALES-PL-2026", "Atlas Platform Price List", date(2026, 3, 1), "SALES-PL-2025 v1.0")
    assessment = EvidenceAssessment(
        outcome=EvidenceOutcome.SUFFICIENT,
        chunks=[_rc(old_meta, superseded=True), _rc(new_meta, superseded=False)],
        reason="test",
    )
    generator = AnswerGenerator(chat_client=_FakeChatClient("The current price is SAR 5,200 per month."))

    answer = generator.generate("What is the current price?", assessment)

    assert "SAR 5,200" in answer.text  # the model's own answer is preserved
    assert "supersedes" in answer.text.lower()
    assert "2025-01-01" in answer.text
    assert "2026-03-01" in answer.text


def test_no_supersession_note_when_nothing_is_superseded():
    meta = _meta("HR-POL-002", "Leave and Time Off Policy", date(2026, 1, 1), "HR-POL-002 v3.6")
    assessment = EvidenceAssessment(
        outcome=EvidenceOutcome.SUFFICIENT,
        chunks=[_rc(meta, superseded=False)],
        reason="test",
    )
    original_text = "Employees get 24 working days of annual leave per year."
    generator = AnswerGenerator(chat_client=_FakeChatClient(original_text))

    answer = generator.generate("What is the annual leave policy?", assessment)

    assert answer.text == original_text  # untouched - nothing to note


def test_sufficient_answer_gets_tenure_tier_note_when_hr_pol_002_table_is_in_context():
    # Regression test for a real bug (assignment Q1): the model was asked
    # to state every tenure tier's specific number, not just that
    # entitlement "increases with service" - and kept giving only the base
    # case in live testing even with an explicit instruction and example.
    # This guarantees the actual numbers appear, parsed straight from the
    # retrieved table text.
    table_text = (
        "Completed years of service | Annual leave entitlement\n"
        "Less than 5 years | 24 working days per year\n"
        "5 years or more | 30 working days per year\n"
        "10 years or more | 32 working days per year"
    )
    meta = _meta("HR-POL-002", "Leave and Time Off Policy", date(2026, 1, 1), "HR-POL-002 v3.6")
    chunk = Chunk(
        chunk_id="HR-POL-002-table",
        document_id="HR-POL-002",
        section="4.2 Annual leave entitlement",
        text=table_text,
        is_table=True,
        metadata=meta,
    )
    assessment = EvidenceAssessment(
        outcome=EvidenceOutcome.SUFFICIENT,
        chunks=[RetrievedChunk(chunk=chunk, score=0.75)],
        reason="test",
    )
    original_text = "Permanent employees are entitled to 24 working days of annual leave per year."
    generator = AnswerGenerator(chat_client=_FakeChatClient(original_text))

    answer = generator.generate("What is the company's annual leave policy?", assessment)

    assert "30 working days per year" in answer.text
    assert "32 working days per year" in answer.text


def test_no_supersession_note_for_non_sufficient_outcomes():
    # CONFLICTING already has its own explicit dual-source explanation
    # instruction - this note is a SUFFICIENT-only backstop, not a general
    # supersession announcer that could pile onto an already-thorough answer.
    old_meta = _meta("SALES-PL-2025", "Atlas Platform Price List", date(2025, 1, 1), None)
    new_meta = _meta("SALES-PL-2026", "Atlas Platform Price List", date(2026, 3, 1), "SALES-PL-2025 v1.0")
    assessment = EvidenceAssessment(
        outcome=EvidenceOutcome.CONFLICTING,
        chunks=[_rc(old_meta, superseded=True), _rc(new_meta, superseded=False)],
        reason="test",
    )
    original_text = "Two different figures apply depending on the source."
    generator = AnswerGenerator(chat_client=_FakeChatClient(original_text))

    answer = generator.generate("What refund window applies?", assessment)

    assert answer.text == original_text
