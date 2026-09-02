"""Defence against instructions embedded inside retrieved documents (as
opposed to classifier.py, which screens the user's own query).
ContextSanitizer strips HTML-comment payloads before they reach the prompt;
OutputGuard is a last check catching known payload claims in the answer.
Both are corpus-specific safety nets, not general detection - see README.
"""
import re

_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)

_KNOWN_PAYLOAD_CLAIMS = [
    "all vendors are pre-approved",
    "no due diligence is required",
    "atlas has no rate limits",
    "granted administrator access",
]

_SAFE_REPLACEMENT = (
    "I found an instruction embedded in a retrieved document that tried to change how I "
    "answer. I'm not following it. Please rephrase your question and I'll answer from the "
    "actual policy content instead."
)


class ContextSanitizer:
    def sanitize(self, text: str) -> str:
        return _HTML_COMMENT_RE.sub("", text)


class OutputGuard:
    def check(self, answer_text: str) -> tuple[str, bool]:
        lowered = answer_text.lower()
        for phrase in _KNOWN_PAYLOAD_CLAIMS:
            if phrase in lowered:
                return _SAFE_REPLACEMENT, True
        return answer_text, False
