from __future__ import annotations
from pydantic import BaseModel


class LogEntry(BaseModel):
    timestamp: float
    level: str
    logger: str
    message: str
    pathname: str


class LogsLastResponse(BaseModel):
    entries: list[LogEntry]
    total_buffered: int
    capacity: int
