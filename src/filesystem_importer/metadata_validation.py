
"""Validation and normalisation of proposed metadata values."""

import re
from datetime import date


MONTHS = (
    "January", "February", "March", "April",
    "May", "June", "July", "August",
    "September", "October", "November", "December",
)

WEEKDAYS = (
    "Monday", "Tuesday", "Wednesday", "Thursday",
    "Friday", "Saturday", "Sunday",
)

SEASONS = ("Spring", "Summer", "Autumn", "Winter")

TEMPORAL_DESCRIPTORS = (
    "Morning", "Afternoon", "Night", "Early", "Late", "Day",
)


def _normalise_date(year: int, month: int, day: int) -> str | None:
    """Return a valid date in dd-mmm-yyyy format."""
    try:
        parsed = date(year, month, day)
    except ValueError:
        return None

    return f"{parsed.day:02d}-{MONTHS[parsed.month - 1][:3]}-{parsed.year:04d}"


def year_validate(value: str | None) -> str | None:
    """Validate and normalise a proposed Year value.

    Accepted values are calendar years, recognised full dates, month
    names, weekdays, seasons and temporal descriptors.

    Ambiguous numeric dates retain their unambiguous four-digit year.
    Invalid or unrecognised values return None.
    """
    if not isinstance(value, str):
        return None

    candidate = value.strip()
    if not candidate:
        return None

    # A four-digit calendar year.
    if re.fullmatch(r"\d{4}", candidate):
        year = int(candidate)
        if 1 <= year <= 9999:
            return str(year)
        return None

    # Numeric dates with a four-digit year.
    numeric_date = re.fullmatch(
        r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})",
        candidate,
    )
    if numeric_date:
        first, second, year = map(int, numeric_date.groups())

        if first > 12 and second <= 12:
            # Day/month/year.
            return _normalise_date(year, second, first)

        if second > 12 and first <= 12:
            # Month/day/year.
            return _normalise_date(year, first, second)

        if first <= 12 and second <= 12:
            # Ambiguous day/month versus month/day.
            return str(year)

        return None


    # ISO date: yyyy-mm-dd.
    iso_date = re.fullmatch(
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        candidate,
    )
    if iso_date:
        year, month, day = map(int, iso_date.groups())
        return _normalise_date(year, month, day)

    # Day-month-year numeric forms, using '-' or '/'.
    numeric_date = re.fullmatch(
        r"(\d{1,2})[-/](\d{1,2})[-/](\d{4})",
        candidate,
    )
    if numeric_date:
        day, month, year = map(int, numeric_date.groups())
        return _normalise_date(year, month, day)

    # Day Month Year, e.g. 25 October 2024.
    textual_date = re.fullmatch(
        r"(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})",
        candidate,
    )
    if textual_date:
        day = int(textual_date.group(1))
        month_name = textual_date.group(2).capitalize()
        if month_name not in MONTHS:
            return None
        month = MONTHS.index(month_name) + 1
        year = int(textual_date.group(3))
        return _normalise_date(year, month, day)

    # Month Day, Year, e.g. October 25, 2024.
    textual_date = re.fullmatch(
        r"([A-Za-z]+)\s+(\d{1,2}),?\s+(\d{4})",
        candidate,
    )
    if textual_date:
        month_name = textual_date.group(1).capitalize()
        if month_name not in MONTHS:
            return None
        month = MONTHS.index(month_name) + 1
        day = int(textual_date.group(2))
        year = int(textual_date.group(3))
        return _normalise_date(year, month, day)

    # Recognised temporal descriptors.
    for terms in (MONTHS, WEEKDAYS, SEASONS, TEMPORAL_DESCRIPTORS):
        for term in terms:
            if candidate.casefold() == term.casefold():
                return term

    return None

