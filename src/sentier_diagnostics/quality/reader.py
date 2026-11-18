"""Read observations with field provenance and keep self-reported claims separate."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .contract import ClaimAsEvidence, Observation, Plain


def computed(name: str, value: Plain, how: str) -> Observation:
    """An observation of a value computed in this run, with how it was computed."""
    return Observation(name=name, value=value, how=how)


class Reader:
    """Reads one record: evidence with :meth:`read`, claims with :meth:`cite`.

    ``record`` holds the fields; ``where`` says, for each field, the label of the file it
    came from (``links``, ``mapping``, …); a field without its own label takes ``default``.
    """

    def __init__(
        self,
        record: Mapping[str, Any],
        where: Mapping[str, str],
        *,
        claims: Mapping[str, str],
        default: str | None = None,
    ) -> None:
        self._record = record
        self._claims = claims
        self._where = where
        self._default = default
        self.cited: dict[str, Any] = {}

    def _at(self, field: str) -> str:
        label = self._where.get(field, self._default)
        if label is None:
            raise KeyError(f"no file is named for the field {field!r}")
        return f"{label}:{field}"

    def read(self, field: str) -> Any:
        """The value of ``field`` as evidence. A claim raises :class:`ClaimAsEvidence`."""
        why = self._claims.get(field)
        if why is not None:
            raise ClaimAsEvidence(
                f"{field!r} is a claim and may not be read as evidence: {why}. Cite it, and "
                "derive the verdict from what the record holds"
            )
        if field not in self._record:
            raise KeyError(f"the record has no field {field!r}")
        return self._record[field]

    def observe(self, field: str, name: str | None = None) -> Observation:
        """Read ``field`` as evidence and make the observation of it, named ``name``."""
        value = self.read(field)
        if isinstance(value, (list, tuple)):
            value = ";".join(str(item) for item in value)
        return Observation(name=name or field, value=value, at=self._at(field))

    def cite(self, field: str) -> Any:
        """The value of ``field`` as a claim: shown, never judged."""
        value = self._record.get(field)
        self.cited[field] = value
        return value
