"""Reading tables of results and of items from CSV, by the names in their header.

A table of results has one row per item and one column per indicator:

    item,x:climate,x:water
    p01,0.52,1.25
    p02,,3.0

The header names `item` and every indicator id the run compares, each once, in any
order. A column is found by its name, never by its place: two tables with their columns
in another order are read alike. An unknown column, a missing one or one named twice is
refused, and so is a cell that is not a finite number. An empty cell is a missing
result, never zero.

A table of items names `item` and `unit` (the item's reference unit, which keeps floors
apart), and may name `name`, `place` and `group`.

This reads tables a project wrote; it reads no database. Standard library only.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Iterable
from pathlib import Path

ITEM_COLUMNS = ("item", "unit", "name", "place", "group")


class TableError(ValueError):
    """A table that cannot be read; the message names the file, the row and the column."""


def _header(path: Path, rows) -> list[str]:
    try:
        header = next(rows)
    except StopIteration:
        raise TableError(f"{path}: empty") from None
    header = [h.strip() for h in header]
    if header and header[0].startswith("﻿"):
        header[0] = header[0][1:]
    twice = sorted({h for h in header if header.count(h) > 1})
    if twice:
        raise TableError(f"{path}: columns named twice: {', '.join(twice)}")
    return header


def number(text: str, where: str) -> float | None:
    """A cell as a result: empty is missing; anything but a finite number is refused.

    >>> number("1.5", "x"), number(" ", "x"), number("-2e-3", "x")
    (1.5, None, -0.002)
    """
    text = text.strip()
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        raise TableError(f"{where}: {text!r} is not a number") from None
    if not math.isfinite(value):
        raise TableError(f"{where}: {text!r} is not a finite number")
    return value


def read_results(path: Path, indicators: Iterable[str]) -> dict[str, dict[str, float | None]]:
    """`{indicator: {item: result}}` from a table of results, fail-closed."""
    path = Path(path)
    wanted = list(indicators)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.reader(handle)
        header = _header(path, rows)
        expected = {"item", *wanted}
        unknown, missing = set(header) - expected, expected - set(header)
        if unknown or missing:
            raise TableError(
                f"{path}: the header must name `item` and every indicator once"
                + (f"; unknown: {', '.join(sorted(unknown))}" if unknown else "")
                + (f"; missing: {', '.join(sorted(missing))}" if missing else "")
            )
        at = {name: header.index(name) for name in expected}
        found: dict[str, dict[str, float | None]] = {i: {} for i in wanted}
        seen = set()
        for line, row in enumerate(rows, start=2):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise TableError(f"{path}, row {line}: {len(row)} cells, the header has {len(header)}")
            item = row[at["item"]].strip()
            if not item:
                raise TableError(f"{path}, row {line}: no item")
            if item in seen:
                raise TableError(f"{path}, row {line}: item {item!r} a second time")
            seen.add(item)
            for indicator in wanted:
                found[indicator][item] = number(row[at[indicator]], f"{path}, row {line}, {indicator}")
    return found


def read_items(path: Path) -> dict[str, dict[str, str | None]]:
    """`{item: {"unit", "name", "place", "group"}}` from a table of items."""
    path = Path(path)
    with path.open(newline="", encoding="utf-8") as handle:
        rows = csv.reader(handle)
        header = _header(path, rows)
        unknown = set(header) - set(ITEM_COLUMNS)
        if unknown or not {"item", "unit"} <= set(header):
            raise TableError(
                f"{path}: a table of items names `item` and `unit`, and may name "
                f"`name`, `place` and `group`" + (f"; unknown: {', '.join(sorted(unknown))}" if unknown else "")
            )
        found = {}
        for line, row in enumerate(rows, start=2):
            if not any(cell.strip() for cell in row):
                continue
            if len(row) != len(header):
                raise TableError(f"{path}, row {line}: {len(row)} cells, the header has {len(header)}")
            record = {name: (row[header.index(name)].strip() or None) for name in header}
            item = record.pop("item")
            if not item:
                raise TableError(f"{path}, row {line}: no item")
            if item in found:
                raise TableError(f"{path}, row {line}: item {item!r} a second time")
            found[item] = {k: record.get(k) for k in ("unit", "name", "place", "group")}
    return found
