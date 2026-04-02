from dataclasses import dataclass
from typing import Optional, Any


@dataclass
class AnalyzedWord:
    text: str
    start: Optional[float]
    end: Optional[float]


@dataclass
class AnalyzedCapture:
    phrase: str
    value: Any
    name: Optional[str]


@dataclass
class AnalyzedCommand:
    phrase: str
    rule: str
    code: str
    path: str
    line: int
    captures: list[AnalyzedCapture]


@dataclass
class AnalyzedPhrase:
    phrase: str
    words: list[AnalyzedWord]
    metadata: Optional[dict]
    commands: list[AnalyzedCommand]
