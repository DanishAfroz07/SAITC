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

# Observed live, more than once, on a 3B model: it sometimes invents its own
# "System Prompt:"-style opening line as answer formatting (not an actual
# leak - the real prompt is never in there), but it reads exactly like a
# prompt-injection compliance failure to anyone reviewing the output. The
# system prompt instructs against this; this is the mechanical backstop for
# when that instruction alone isn't reliably followed - strip just the
# offending opening line (and anything else on that same line, e.g.
# "System Prompt: Conflict in refund window..."), keep the substantive
# answer that follows it.
_LEADING_SYSTEM_HEADER_RE = re.compile(
    r"^\s*system\s+(prompt|message|instructions?)\s*[:\-]?.*\n+", re.IGNORECASE
)


class ContextSanitizer:
    def sanitize(self, text: str) -> str:
        return _HTML_COMMENT_RE.sub("", text)


class OutputGuard:
    def check(self, answer_text: str) -> tuple[str, bool]:
        text = answer_text
        flagged = False

        stripped = _LEADING_SYSTEM_HEADER_RE.sub("", text, count=1)
        if stripped != text:
            text = stripped
            flagged = True

        lowered = text.lower()
        for phrase in _KNOWN_PAYLOAD_CLAIMS:
            if phrase in lowered:
                return _SAFE_REPLACEMENT, True

        return text, flagged
