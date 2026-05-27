"""
parser.py — Parses card checker result files and filters by status.

Handles the standard result format:
    card : XXXXXXXXXXXXXXXX|MM|YYYY|CVV
    response : ...
    status : Charged / Declined / Insufficient
    time : XX.Xs
"""

import re
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CardEntry:
    """Represents a single card entry from a result file."""
    card: str = ""
    response: str = ""
    status: str = ""
    time: str = ""
    bin_number: str = ""

    def __post_init__(self):
        # Extract first 6 digits as BIN
        digits = re.sub(r"[^\d]", "", self.card.split("|")[0] if "|" in self.card else self.card)
        self.bin_number = digits[:6] if len(digits) >= 6 else digits


@dataclass
class ParseResult:
    """Holds the full parsed result from a file."""
    title: str = ""
    total: int = 0
    checked: int = 0
    charged_count: int = 0
    insufficient_count: int = 0
    declined_count: int = 0
    charged: list = field(default_factory=list)
    insufficient: list = field(default_factory=list)
    all_entries: list = field(default_factory=list)


def parse_result_file(content: str, filter_statuses: Optional[list] = None) -> ParseResult:
    """
    Parse a card checker result file and filter entries by status.

    Args:
        content: Raw text content of the result file.
        filter_statuses: List of status keywords to extract (case-insensitive).
                        Defaults to ["Charged", "Insufficient"].

    Returns:
        ParseResult with filtered card entries.
    """
    if filter_statuses is None:
        filter_statuses = ["Charged", "Insufficient"]

    # Normalize filter keywords to lowercase for matching
    filter_lower = [s.lower() for s in filter_statuses]

    result = ParseResult()

    lines = content.splitlines()

    # --- Parse the header ---
    for line in lines[:15]:
        line_stripped = line.strip()
        if not line_stripped or line_stripped.startswith("===="):
            continue

        # Title is usually the first non-empty line
        if not result.title and ":" not in line_stripped:
            result.title = line_stripped
            continue

        # Parse key : value pairs in header
        if ":" in line_stripped:
            key, _, value = line_stripped.partition(":")
            key = key.strip().lower()
            value = value.strip()

            if key == "total":
                result.total = _safe_int(value)
            elif key == "checked":
                result.checked = _safe_int(value)
            elif key == "charged":
                result.charged_count = _safe_int(value)
            elif key == "insufficient":
                result.insufficient_count = _safe_int(value)
            elif key == "declined":
                result.declined_count = _safe_int(value)

    # --- Parse card blocks ---
    current_entry = {}

    for line in lines:
        line_stripped = line.strip()

        # Skip empty lines and separators
        if not line_stripped or line_stripped.startswith("===="):
            continue

        # Separator between card blocks
        if line_stripped.startswith("________"):
            if current_entry.get("card"):
                entry = CardEntry(
                    card=current_entry.get("card", ""),
                    response=current_entry.get("response", ""),
                    status=current_entry.get("status", ""),
                    time=current_entry.get("time", ""),
                )
                result.all_entries.append(entry)

                # Check if this entry matches our filter
                if entry.status.lower() in filter_lower:
                    if entry.status.lower() == "charged":
                        result.charged.append(entry)
                    elif entry.status.lower() == "insufficient":
                        result.insufficient.append(entry)

            current_entry = {}
            continue

        # Parse key : value lines
        if ":" in line_stripped:
            # Split on first " : " (with spaces around colon)
            match = re.match(r"^(\w+)\s*:\s*(.*)$", line_stripped)
            if match:
                key = match.group(1).strip().lower()
                value = match.group(2).strip()
                current_entry[key] = value

    # Handle the last block if file doesn't end with separator
    if current_entry.get("card"):
        entry = CardEntry(
            card=current_entry.get("card", ""),
            response=current_entry.get("response", ""),
            status=current_entry.get("status", ""),
            time=current_entry.get("time", ""),
        )
        result.all_entries.append(entry)

        if entry.status.lower() in filter_lower:
            if entry.status.lower() == "charged":
                result.charged.append(entry)
            elif entry.status.lower() == "insufficient":
                result.insufficient.append(entry)

    return result


def _safe_int(value: str) -> int:
    """Safely convert a string to int, returning 0 on failure."""
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0
