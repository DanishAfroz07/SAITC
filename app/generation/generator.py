"""Turns retrieved, assessed evidence into a grounded, cited Answer. Owns no
decision logic of its own - the outcome was already decided by
EvidenceAnalyzer, and the wording per outcome lives in prompts.py.
"""
from app.generation.citations import build_citations
from app.generation.llm import ChatClient
from app.generation.prompts import build_messages
from app.models import Answer, EvidenceAssessment


class AnswerGenerator:
    def __init__(self, chat_client: ChatClient) -> None:
        self._chat_client = chat_client

    def generate(self, query: str, assessment: EvidenceAssessment) -> Answer:
        messages = build_messages(query, assessment)
        text = self._chat_client.complete(messages)
        citations = build_citations(assessment.chunks)
        return Answer(text=text, citations=citations, outcome=assessment.outcome)
