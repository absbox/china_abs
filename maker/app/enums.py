from enum import Enum


class DatabaseName(Enum):
    """MongoDB databases available for saving structured reports."""

    prod = "prod"
    test = "test"
    raw = "raw"


class ReportType(Enum):
    """Report categories; each member's value names the target collection."""

    pricing = "pricing"
    trustee = "trustee"