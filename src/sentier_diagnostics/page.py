"""The page: a frameless body a site holds in its own page, or a page of its own.

`body(data)` is the diagnostics as one element, `<div class="sentier-diagnostics">`, with the
file inside it as JSON: no `<html>`, no `<head>`, no id. A site puts it where it wants and
loads `diagnostics.js` and `diagnostics.css` from `assets()`. The style is scoped to that
element and sets no font and nothing on `:root` or `body`; its colours take the site's tokens
(`--ink`, `--line`, `--surface` ...) where the site sets them.

`write(data, folder)` writes a page of its own: `index.html` with the body in it, the two
assets and `standalone.css`, which sets the tokens and font a site would. It opens from disk
by a double click and needs no server and no network. A local file may name its matrix of
every item (`chain.build_with_matrix`); given it, `write` puts it beside the page as
`matrix.js`, which the page loads after it has drawn.

The page shows what the file says. It works out no class, no direction and no count of
its own: it only adds the file's counts up (the classes that moved into "moved", a step's
counts over its indicators), divides an item's result after by its result before to show
their ratio, and splits one item's difference into the steps' shares.
"""

from __future__ import annotations

import html
import json
import re
import shutil
from collections.abc import Mapping
from importlib import resources
from pathlib import Path

from . import breakdown, fileformat
from . import matrix as matrix_format

#: What a site copies into its assets to hold the body.
ASSETS = ("diagnostics.js", "diagnostics.css")
#: What a page of its own adds: its frame and the template of the body.
STANDALONE = ("index.html", "standalone.css")
TEMPLATE = "body.html"
MATRIX_SCRIPT = "matrix.js"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*")
_ROOT = '<div class="sentier-diagnostics" data-sentier-diagnostics>'


def _json(value) -> str:
    """A value as JSON that no HTML parser reads as markup: ASCII only, and every `<` escaped,
    so that no text of a file can end the element that holds it or open a comment."""
    text = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    return text.replace("<", "\\u003c")


def as_script(name: str, value) -> str:
    """A value as a script that assigns it (`window.NAME = ...;`), for a site that keeps the
    data in a file of its own; the page reads `SENTIER_DIAGNOSTICS`,
    `SENTIER_DIAGNOSTICS_BREAKDOWNS` and `SENTIER_DIAGNOSTICS_MATRIX`."""
    return f"window.{name} = {_json(value)};\n"


def matrix_script(matrix: Mapping) -> str:
    """A matrix as the script beside a page: it adds the matrix to the list of matrices handed
    to the pages of a document (`SENTIER_DIAGNOSTICS_MATRICES`) rather than setting one
    global, so that two pages in one host each take the matrix of their own file."""
    return f"(window.SENTIER_DIAGNOSTICS_MATRICES = window.SENTIER_DIAGNOSTICS_MATRICES || []).push({_json(matrix)});\n"


def _read(name: str) -> str:
    return (resources.files(__package__) / "page" / name).read_text(encoding="utf-8")


def assets(standalone: bool = False) -> dict[str, Path]:
    """The page's own files by name, as paths of the installed package: the script and the
    style a site copies, and with `standalone` also the frame of a page of its own and the
    template of the body."""
    source = resources.files(__package__) / "page"
    names = ASSETS + ((*STANDALONE, TEMPLATE) if standalone else ())
    return {name: Path(str(source / name)) for name in names}


def _checked(data: Mapping, breakdowns: Mapping[str, Mapping]) -> None:
    found = fileformat.errors(data)
    if found:
        raise ValueError("not a diagnostics file: " + "; ".join(found[:10]))
    errors = breakdown_errors(data, breakdowns)
    if errors:
        raise ValueError("; ".join(errors))


def body(
    data: Mapping,
    *,
    breakdowns: Mapping[str, Mapping] | None = None,
    base: str = "",
    title: bool = True,
    matrix: str | None = None,
) -> str:
    """The diagnostics as one element for a site's page, the file and its breakdowns inside.

    `base` is put before the names of the files the page loads (breakdowns, the matrix), for
    a site that keeps them elsewhere than the page. `title=False` leaves the heading to the
    site. `matrix` names the file of the matrix the page loads after it has drawn, where it
    is not the one the file names (a site that serves `matrix.json` needs none).
    """
    return _body(data, breakdowns=breakdowns, base=base, title=title, matrix=matrix, standalone=False)


def _body(data, *, breakdowns, base, title, matrix, standalone) -> str:
    breakdowns = dict(breakdowns or {})
    _checked(data, breakdowns)
    if matrix is not None and not (_NAME.fullmatch(matrix) and ".." not in matrix):
        raise ValueError(f"the matrix {matrix!r} is not a plain file name")
    scripts = f'<script type="application/json" data-sd="data">{_json(data)}</script>\n'
    if breakdowns:
        scripts += f'<script type="application/json" data-sd="breakdowns">{_json(breakdowns)}</script>\n'
    if len(scripts) > fileformat.MAX_BYTES:  # ASCII: one byte per character
        raise ValueError(
            f"the page would hold {len(scripts)} bytes of data, and holds {fileformat.MAX_BYTES} at most: "
            "list fewer items, and keep every item in the matrix"
        )
    attributes = ""
    if base:
        attributes += f' data-sd-base="{html.escape(base, quote=True)}"'
    if matrix:
        attributes += f' data-sd-matrix="{html.escape(matrix, quote=True)}"'
    if standalone:
        attributes += " data-sd-standalone"
    text = _read(TEMPLATE)
    if _ROOT not in text or "<!--data-->" not in text:
        raise RuntimeError("the template of the body has lost its root or its place for the data")
    text = text.replace(_ROOT, _ROOT[:-1] + attributes + ">", 1)
    if not title:
        text = text.replace(
            '<h2 class="sd-title" data-sd="title">', '<h2 class="sd-title" data-sd="title" hidden>', 1
        )
    return text.replace("<!--data-->", scripts.rstrip("\n"), 1)


def write(
    data: Mapping,
    folder: Path,
    breakdowns: Mapping[str, Mapping] | None = None,
    matrix: Mapping | None = None,
) -> Path:
    """A page of its own and its data in `folder`; returns the path of `index.html`. A
    matrix is checked against the file before it is written beside the page."""
    if matrix is not None:
        _checked(data, dict(breakdowns or {}))
        found = matrix_format.errors(matrix) or matrix_format.against(matrix, data)
        if found:
            raise ValueError("not the matrix of this file: " + "; ".join(found[:10]))
    inner = _body(data, breakdowns=breakdowns, base="", title=False,
                  matrix=MATRIX_SCRIPT if matrix is not None else None, standalone=True)  # fmt: skip
    script = matrix_script(matrix) if matrix is not None else None
    if script is not None and len(script) > matrix_format.MAX_BYTES:
        raise ValueError(
            f"{MATRIX_SCRIPT} would be {len(script)} bytes, and a page loads {matrix_format.MAX_BYTES} at most"
        )
    name = html.escape(data["title"], quote=False)
    page = _read("index.html")
    page = page.replace("<!--title-->", name, 1).replace("<!--body-->", f"<h1>{name}</h1>\n{inner}", 1)
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source = resources.files(__package__) / "page"
    for one in (*ASSETS, "standalone.css"):
        with resources.as_file(source / one) as path:
            shutil.copyfile(path, folder / one)
    (folder / "index.html").write_text(page, encoding="utf-8")
    stale = folder / MATRIX_SCRIPT
    if script is not None:
        stale.write_text(script, encoding="utf-8")
    elif stale.exists():
        stale.unlink()  # the matrix of an earlier page: this one names none
    return folder / "index.html"


def breakdown_errors(data: Mapping, breakdowns: Mapping[str, Mapping]) -> list[str]:
    """Everything wrong with the breakdowns given for a checked diagnostics file: each one
    alone, then against every item and step that names it (it must be theirs), or against
    the file where nothing names it."""
    found, broken = [], set()
    for name, one in breakdowns.items():
        errors = breakdown.errors(one)
        if errors:
            broken.add(name)
            found += [f"{name}: {e}" for e in errors]
    named = set()
    for name, item, key in breakdown.namings(data):
        if name in breakdowns and name not in broken:
            named.add(name)
            found += [f"{name}: {e}" for e in breakdown.against(breakdowns[name], data, (item, key))]
    for name in sorted(set(breakdowns) - named - broken):
        found += [f"{name}: {e}" for e in breakdown.against(breakdowns[name], data)]
    return found


def named_breakdowns(data: Mapping, beside: Path) -> tuple[dict, list[str]]:
    """The breakdowns a file names that lie beside it, read; and the names of those that
    do not (a project may keep them to itself). A breakdown that cannot be read is refused
    with its name."""
    found, absent = {}, []
    names = sorted({f for item in data["items"] for f in (item["breakdowns"] or {}).values()})
    for name in names:
        path = Path(beside) / name
        if not path.is_file():
            absent.append(name)
            continue
        found[name] = fileformat.load_json(path)
    return found, absent


def named_matrix(data: Mapping, beside: Path) -> dict | None:
    """The matrix a file names, read from beside it and checked against the file; None where
    it names none or where the matrix is not there (a page then shows the listed items and
    says so). A matrix that is there and not the file's is refused."""
    named = data.get("matrix")
    if not named:
        return None
    path = Path(beside) / named["file"]
    if not path.is_file():
        return None
    return matrix_format.read(path, data)
