"""Deterministic annual-leave accrual calculator.

Why this exists: Q3 asks for a multi-step date calculation (join date, leave
date, partial-month accrual rule from HR-PRO-011), and across many live
runs the LLM (3B and 7B alike) has gotten this arithmetic wrong in several
different ways, always confidently. Rather than keep tuning a prompt that
demonstrably doesn't make an LLM reliable at arithmetic, this computes the
answer in code - guaranteed correct - and the LLM is not asked to do the
math at all for this narrow, well-defined class of question.

Deliberately narrow: only triggers when the query names two "DD Month"
dates AND asks about annual leave entitlement. Anything else - including
tenure-based entitlements (5+/10+ years, which accrue at a different rate
this does not model) - falls through to the normal RAG pipeline untouched.
"""
import re
from dataclasses import dataclass
from datetime import date

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}
_MONTH_NAMES = {v: k.capitalize() for k, v in _MONTHS.items()}

_DATE_RE = re.compile(
    r"\b(\d{1,2})(?:st|nd|rd|th)?\s+(" + "|".join(_MONTHS) + r")\b", re.IGNORECASE
)
_LEAVE_KEYWORDS_RE = re.compile(r"\bannual leave\b.*\bentitle", re.IGNORECASE | re.DOTALL)
_TENURE_GUARD_RE = re.compile(r"\b(\d+|five|ten)\s+years?\s+(of\s+)?service\b", re.IGNORECASE)

_STANDARD_DAYS_PER_MONTH = 2  # HR-PRO-011 section 3: standard 24-day entitlement


@dataclass
class LeaveCalculation:
    working_days: int
    explanation: str


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        next_month_first = date(year + 1, 1, 1)
    else:
        next_month_first = date(year, month + 1, 1)
    return (next_month_first - date(year, month, 1)).days


def _completed_months(join_date: date, leave_date: date) -> tuple[int, list[str]]:
    """HR-PRO-011 section 4: a partial month counts as complete if 15+
    calendar days were served in it; otherwise it's disregarded. Applies at
    both ends. Verified against HR-PRO-011's own worked example (20 June ->
    30 November = 5 completed months) before trusting this for real answers.
    """
    steps: list[str] = []
    months = 0

    if (join_date.year, join_date.month) == (leave_date.year, leave_date.month):
        days = (leave_date - join_date).days + 1
        counted = days >= 15
        steps.append(
            f"{join_date.day} to {leave_date.day} {_MONTH_NAMES[join_date.month]} is {days} "
            f"calendar days, which {'meets' if counted else 'is below'} the 15-day threshold, "
            f"so it {'counts as one completed month' if counted else 'is disregarded'}."
        )
        return (1 if counted else 0), steps

    last_day_of_join_month = _days_in_month(join_date.year, join_date.month)
    first_span = last_day_of_join_month - join_date.day + 1
    first_counts = first_span >= 15
    steps.append(
        f"{join_date.day} to {last_day_of_join_month} {_MONTH_NAMES[join_date.month]} is "
        f"{first_span} calendar days, which {'meets' if first_counts else 'is below'} the "
        f"15-day threshold, so {_MONTH_NAMES[join_date.month]} "
        f"{'counts as a completed month' if first_counts else 'is disregarded'}."
    )
    if first_counts:
        months += 1

    y, m = join_date.year, join_date.month + 1
    if m > 12:
        y, m = y + 1, 1
    full_months: list[str] = []
    while (y, m) < (leave_date.year, leave_date.month):
        full_months.append(_MONTH_NAMES[m])
        months += 1
        m += 1
        if m > 12:
            y, m = y + 1, 1
    if full_months:
        steps.append(f"{', '.join(full_months)} {'is' if len(full_months) == 1 else 'are'} fully completed month(s).")

    last_span = leave_date.day
    last_counts = last_span >= 15
    steps.append(
        f"1 to {leave_date.day} {_MONTH_NAMES[leave_date.month]} is {last_span} calendar days, "
        f"which {'meets' if last_counts else 'is below'} the 15-day threshold, so "
        f"{_MONTH_NAMES[leave_date.month]} {'counts as a completed month' if last_counts else 'is disregarded'}."
    )
    if last_counts:
        months += 1

    return months, steps


def try_compute(query: str, as_of_date: date) -> LeaveCalculation | None:
    if not _LEAVE_KEYWORDS_RE.search(query) or _TENURE_GUARD_RE.search(query):
        return None

    matches = _DATE_RE.findall(query)
    if len(matches) != 2:
        return None

    def to_date(day_str: str, month_str: str) -> date:
        month = _MONTHS[month_str.lower()]
        year = as_of_date.year
        return date(year, month, int(day_str))

    try:
        join_date = to_date(*matches[0])
        leave_date = to_date(*matches[1])
    except ValueError:
        return None
    if leave_date <= join_date:
        return None

    months, steps = _completed_months(join_date, leave_date)
    working_days = months * _STANDARD_DAYS_PER_MONTH

    explanation = (
        f"An employee joining on {join_date.day} {_MONTH_NAMES[join_date.month]} and leaving on "
        f"{leave_date.day} {_MONTH_NAMES[leave_date.month]} accrues annual leave under the "
        f"standard 24-day entitlement, at 2 working days per completed month (HR-POL-002). "
        f"{' '.join(steps)} That's {months} completed month{'s' if months != 1 else ''} in total, "
        f"so the accrued entitlement is {months} x 2 = {working_days} working days "
        f"(HR-PRO-011's partial-month accrual rule)."
    )
    return LeaveCalculation(working_days=working_days, explanation=explanation)
