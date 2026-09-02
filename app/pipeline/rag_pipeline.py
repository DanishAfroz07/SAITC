"""Wires safety, retrieval, evidence assessment and generation into the one
call both the API and the CLI depend on. This is the composition target, not
the composition root - it takes fully-built collaborators through its
constructor (Dependency Inversion) and is built by app/wiring.py, so it can
be unit tested with fakes for every collaborator.
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
        chunks = self._reranker.rerank(query, chunks)
        chunks = self._version_resolver.tag_superseded(chunks, self._as_of_date)

        for retrieved in chunks:
            retrieved.chunk.text = self._sanitizer.sanitize(retrieved.chunk.text)

        assessment = self._evidence_analyzer.assess(chunks)
        answer = self._generator.generate(query, assessment)

        safe_text, was_flagged = self._output_guard.check(answer.text)
        if was_flagged:
            answer.text = safe_text
        return answer
