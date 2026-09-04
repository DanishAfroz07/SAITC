from datetime import date

from app.generation.leave_calculator import try_compute

AS_OF = date(2026, 8, 27)


def test_matches_hr_pro_011s_own_worked_example():
    # HR-PRO-011's own worked example states the answer is 10 working days -
    # if this calculator disagreed with the source document, it would be
    # worse than not having one at all.
    result = try_compute(
        "An employee on the standard 24-day entitlement joins on 20 June and leaves on "
        "30 November of the same year. How much annual leave are they entitled to?",
        AS_OF,
    )
    assert result is not None
    assert result.working_days == 10


def test_assignment_q3_case():
    result = try_compute(
        "An employee joins on 1 March and leaves on 15 September. How much annual leave "
        "are they entitled to?",
        AS_OF,
    )
    assert result is not None
    assert result.working_days == 14
    assert "HR-PRO-011" in result.explanation


def test_exactly_15_days_in_partial_month_counts_as_complete():
    # HR-PRO-011: "15 calendar days or more" - this is the boundary itself.
    result = try_compute(
        "An employee joins on 1 January and leaves on 15 February. How much annual leave "
        "are they entitled to?",
        AS_OF,
    )
    assert result is not None
    # Jan (31 days, full) + Feb 1-15 (15 days, meets threshold) = 2 months = 4 days
    assert result.working_days == 4


def test_14_days_in_partial_month_is_disregarded():
    result = try_compute(
        "An employee joins on 1 January and leaves on 14 February. How much annual leave "
        "are they entitled to?",
        AS_OF,
    )
    assert result is not None
    # Jan (full) + Feb 1-14 (14 days, below threshold, disregarded) = 1 month = 2 days
    assert result.working_days == 2


def test_does_not_trigger_on_unrelated_dates():
    result = try_compute("What happened between 1 March and 15 September in the price list?", AS_OF)
    assert result is None


def test_does_not_trigger_on_tenure_based_entitlement():
    # 5+/10+ year tenure accrues at a different rate this calculator doesn't model -
    # falling through to the normal RAG pipeline is safer than guessing.
    result = try_compute(
        "An employee with 5 years of service joins on 1 March and leaves on 15 September. "
        "How much annual leave are they entitled to?",
        AS_OF,
    )
    assert result is None


def test_does_not_trigger_without_two_dates():
    result = try_compute("How much annual leave am I entitled to?", AS_OF)
    assert result is None


def test_does_not_trigger_when_leave_date_before_join_date():
    result = try_compute(
        "An employee joins on 15 September and leaves on 1 March. How much annual leave "
        "are they entitled to?",
        AS_OF,
    )
    assert result is None
