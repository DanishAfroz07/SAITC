"""Wires safety, retrieval, reranking, evidence assessment and generation
into the one `answer()` call the API and CLI both use. Built by app/wiring.py.
"""
from datetime import date

from app.generation.generator import AnswerGenerator
from app.models import Answer, EvidenceOutcome, InputVerdict
from app.retrieval.evidence_analyzer import EvidenceAnalyzer
from app.retrieval.reranker import Reranker
from app.retrieval.retriever import Retriever
from app.retrieval.version_resolver import VersionResolver
from app.safety.classifier import InputClassifier
from app.safety.guardrails import ContextSanitizer, OutputGuard

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

    def answer(self, query: str) -> Answer:
        verdict = self._classifier.classify(query)
        if verdict is not InputVerdict.SAFE:
            return Answer(text=_REFUSAL_TEXT[verdict], citations=[], outcome=EvidenceOutcome.INSUFFICIENT)

        chunks = self._retriever.retrieve(query)
        chunks = self._version_resolver.tag_superseded(chunks, self._as_of_date)

        for retrieved in chunks:
            retrieved.chunk.text = self._sanitizer.sanitize(retrieved.chunk.text)

        # Evidence is assessed on the full retrieved set BEFORE reranking, so
        # reranking can never hide one side of a detected conflict. Reranking
        # then reorders the decided chunk set for a cleaner generation
        # context, and only narrows it (rerank_top_n) when that's safe - i.e.
        # not for CONFLICTING/AMBIGUOUS, where every chunk must stay visible.
        assessment = self._evidence_analyzer.assess(chunks)
        assessment.chunks = self._reranker.rerank(query, assessment.chunks)
        if assessment.outcome == EvidenceOutcome.SUFFICIENT:
            assessment.chunks = assessment.chunks[: self._rerank_top_n]

        answer = self._generator.generate(query, assessment)

        safe_text, was_flagged = self._output_guard.check(answer.text)
        if was_flagged:
            answer.text = safe_text
        return answer
