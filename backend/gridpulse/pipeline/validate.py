"""Validate raw EIA records before they reach pandas or the database."""

from datetime import UTC, datetime
from typing import NamedTuple

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from gridpulse.pipeline.fetch_eia import EIA_PERIOD_FORMAT


class EIAObservation(BaseModel):
    """One (hour, region, series) reading from EIA."""

    model_config = ConfigDict(populate_by_name=True)

    timestamp: datetime = Field(alias="period")
    region_code: str = Field(alias="respondent")
    series_type: str = Field(alias="type")
    value: float | None = None

    @field_validator("timestamp", mode="before")
    @classmethod
    def _parse_eia_period(cls, raw: object) -> object:
        if isinstance(raw, str):
            return datetime.strptime(raw, EIA_PERIOD_FORMAT).replace(tzinfo=UTC)
        return raw


class ValidationResult(NamedTuple):
    observations: list[EIAObservation]
    rejected: list[str]


def validate_records(records: list[dict]) -> ValidationResult:
    """Split raw records into usable observations and human-readable rejections.

    A malformed record is dropped rather than failing the whole run, because one
    bad hour should not block ingesting the rest of the window.
    """
    observations: list[EIAObservation] = []
    rejected: list[str] = []

    for record in records:
        try:
            observations.append(EIAObservation.model_validate(record))
        except (ValidationError, ValueError) as exc:
            rejected.append(f"{record!r}: {exc}")

    return ValidationResult(observations, rejected)
