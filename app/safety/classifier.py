"""Flags user-side prompt injection / policy-bypass intent before a query
reaches retrieval or generation. Regex-based - fast and auditable, but not a
general jailbreak detector (see README limitations).
"""
import re

from app.models import InputVerdict

_EXTRACTION_PATTERNS = [
    r"\brepeat\b.*\b(instructions|system prompt|prompt)\b",
    r"\b(reveal|print|show|output|share|give)\b.*\b(system prompt|your instructions|the instructions)\b",
    r"\bwhat (are|were) your (instructions|system prompt)\b",
    r"\bignore (all |any )?(previous|prior|your) instructions\b",
    r"\bdisregard (all |any )?(previous|prior|your) instructions\b",
    r"\bword for word\b",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"\bignore\b.*\b(the )?(compan(y|y's)|polic(y|ies))\b",
    r"\bbypass\b.*\b(approval|process|policy|control)\b",
    r"\bhow (to|do i) (bypass|circumvent|get around|work around)\b",
    r"\bwithout (approval|authoriz|authoris)\b",
]

_extraction_re = re.compile("|".join(_EXTRACTION_PATTERNS), re.IGNORECASE)
_out_of_scope_re = re.compile("|".join(_OUT_OF_SCOPE_PATTERNS), re.IGNORECASE)


class InputClassifier:
    def classify(self, query: str) -> InputVerdict:
        if _extraction_re.search(query):
            return InputVerdict.INJECTION_ATTEMPT
        if _out_of_scope_re.search(query):
            return InputVerdict.OUT_OF_SCOPE
        return InputVerdict.SAFE
