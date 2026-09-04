"""Wires safety, retrieval, reranking, evidence assessment and generation
into the one `answer()` call the API and CLI both use. Built by app/wiring.py.
"""
from datetime import date

from app.generation.generator import AnswerGenerator
from app.generation.leave_calculator import try_compute
from app.models import Answer, Citation, DocumentMetadata, EvidenceOutcome, InputVerdict
from app.retrieval.evidence_analyzer import EvidenceAnalyzer
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import Retriever
from app.retrieval.version_resolver import VersionResolver
from app.safety.classifier import InputClassifier
from app.safety.guardrails import ContextSanitizer, OutputGuard

# Documents the deterministic leave calculator's answer is grounded in:
# HR-POL-002 sets the base entitlement, HR-PRO-011 is the operative
# accrual/partial-month rule it actually applies.
_LEAVE_CALCULATION_SOURCE_DOCS = ("HR-POL-002", "HR-PRO-011")

_REFUSAL_TEXT: dict[InputVerdict, str] = {
    InputVerdict.OUT_OF_SCOPE: (
        "I can't help with bypassing company policy or approval processes. If there's a "
        "legitimate case for an exception, it needs to go through the process itself."
    ),
    InputVerdict.INJECTION_ATTEMPT: (
        "I can't share my system instructions. I'm happy to answer questions about Cerulean "
        "Systems' policies and documents instead."
    ),
}


class RagPipeline:
    def __init__(
        self,
        classifier: InputClassifier,
        retriever: Retriever,
        reranker: Reranker,
        rerank_top_n: int,
        version_resolver: VersionResolver,
        evidence_analyzer: EvidenceAnalyzer,
        sanitizer: ContextSanitizer,
        generator: AnswerGenerator,
        output_guard: OutputGuard,
        as_of_date: date,
        manifest_by_id: dict[str, DocumentMetadata],
    ) -> None:
        self._classifier = classifier
        self._retriever = retriever
        self._reranker = reranker
        self._rerank_top_n = rerank_top_n
        self._version_resolver = version_resolver
        self._evidence_analyzer = evidence_analyzer
        self._sanitizer = sanitizer
        self._generator = generator
        self._output_guard = output_guard
        self._as_of_date = as_of_date
        self._manifest_by_id = manifest_by_id

    def answer(self, query: str) -> Answer:
        verdict = self._classifier.classify(query)
        if verdict is not InputVerdict.SAFE:
            return Answer(text=_REFUSAL_TEXT[verdict], citations=[], outcome=EvidenceOutcome.INSUFFICIENT)

        calculated = try_compute(query, self._as_of_date)
        if calculated is not None:
            return Answer(text=calculated.explanation, citations=self._leave_calculation_citations(), outcome=EvidenceOutcome.SUFFICIENT)

        chunks = self._retriever.retrieve(query)
        chunks = self._version_resolver.tag_superseded(chunks, self._as_of_date)

        for retrieved in chunks:
            retrieved.chunk.text = self._sanitizer.sanitize(retrieved.chunk.text)

        # Evidence is assessed on the full retrieved set BEFORE reranking, so
        # reranking can never hide one side of a detected conflict. Reranking
        # then reorders the FULL set - assessment.chunks always stays this
        # full, reordered set, since citations and the mechanical answer
        # notes (superseded values, tenure tiers) need to see everything
        # that was actually relevant, not just what fits in a lean prompt.
        # prompt_chunks is the separately-narrowed subset (rerank_top_n,
        # SUFFICIENT only - CONFLICTING/AMBIGUOUS need every chunk visible)
        # that's the ONLY thing actually shown to the model.
        assessment = self._evidence_analyzer.assess(query, chunks)
        assessment.chunks = self._reranker.rerank(query, assessment.chunks)
        prompt_chunks = assessment.chunks
        if assessment.outcome == EvidenceOutcome.SUFFICIENT:
            prompt_chunks = assessment.chunks[: self._rerank_top_n]

        answer = self._generator.generate(query, assessment, prompt_chunks=prompt_chunks)

        safe_text, was_flagged = self._output_guard.check(answer.text)
        if was_flagged:
            answer.text = safe_text
        return answer

    def _leave_calculation_citations(self) -> list[Citation]:
        citations = []
        for doc_id in _LEAVE_CALCULATION_SOURCE_DOCS:
            meta = self._manifest_by_id.get(doc_id)
            if meta is not None:
                citations.append(Citation(document_id=meta.document_id, title=meta.title, effective_date=meta.effective_date))
        return citations
