"""The data object between the sources and the rendering.

Every field may be None. The rendering then leaves the value out instead of
showing a zero: a zero would be a statement we cannot make.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Gauge:
    """A reading with its label and the time it resets."""

    key: str
    label: str
    percent: float
    resets_at: Optional[datetime] = None


@dataclass
class Status:
    week: Optional[Gauge] = None
    scoped: Optional[Gauge] = None
    five_hour: Optional[Gauge] = None
    context: Optional[Gauge] = None
    plan: Optional[str] = None
    plan_tier: Optional[str] = None
    model: Optional[str] = None
    effort: Optional[str] = None
    directory: Optional[str] = None
    branch: Optional[str] = None
    cost_usd: Optional[float] = None
    cc_version: Optional[str] = None
    context_size: Optional[int] = None
    project: Optional[str] = None
    project_usd: Optional[float] = None
