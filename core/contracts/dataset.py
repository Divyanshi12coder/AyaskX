from dataclasses import dataclass
from typing import Iterable

@dataclass(frozen=True)
class FieldContract:
    name: str
    semantic_type: str
    unit: str | None = None
    nullable: bool = True
    min_value: float | None = None
    max_value: float | None = None

@dataclass(frozen=True)
class DatasetContract:
    name: str
    fields: tuple[FieldContract, ...]
    primary_key: tuple[str, ...] = ()

    @property
    def field_names(self) -> tuple[str, ...]:
        return tuple(f.name for f in self.fields)

    def required_fields(self) -> Iterable[FieldContract]:
        return (f for f in self.fields if not f.nullable)
