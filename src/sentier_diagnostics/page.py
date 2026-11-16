"""The static page: three files that need no build step, no server and no network.

`write(data, folder)` copies `index.html`, `diagnostics.js` and `diagnostics.css` into a
folder and writes the file beside them as `data.js`, so that the page opens from disk by
a double click (a browser does not let a page read a JSON file from disk by itself). The
breakdowns the file names go into `breakdowns.js` the same way. Served over HTTP, the
page can also read a JSON file named in its address (`index.html?file=diagnostics.json`),
and it can open a file a reader chooses.

The page shows what the file says. It works out no class, no direction and no count.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from importlib import resources
from pathlib import Path

from . import breakdown, fileformat

ASSETS = ("index.html", "diagnostics.js", "diagnostics.css")


def as_script(name: str, value) -> str:
    """A value as a script that assigns it: ASCII only, and no `</` that could end the
    element, so that no text of a file can be read as markup."""
    text = json.dumps(value, ensure_ascii=True, allow_nan=False, separators=(",", ":"))
    text = text.replace("</", "<\\/")
    return f"window.{name} = {text};\n"


def assets() -> dict[str, Path]:
    """The page's own files by name, for a site that copies them into its assets and
    writes `data.js` itself (`as_script("SENTIER_DIAGNOSTICS", data)`). The paths are those
    of the installed package."""
    source = resources.files(__package__) / "page"
    return {name: Path(str(source / name)) for name in ASSETS}


def write(data: Mapping, folder: Path, breakdowns: Mapping[str, Mapping] | None = None) -> Path:
    """The page and its data in `folder`; returns the path of `index.html`."""
    found = fileformat.errors(data)
    if found:
        raise ValueError("not a diagnostics file: " + "; ".join(found[:10]))
    for name, one in (breakdowns or {}).items():
        errors = breakdown.errors(one) + breakdown.against(one, data)
        if errors:
            raise ValueError(f"{name}: " + "; ".join(errors))
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    source = resources.files(__package__) / "page"
    for name in ASSETS:
        with resources.as_file(source / name) as path:
            shutil.copyfile(path, folder / name)
    (folder / "data.js").write_text(as_script("SENTIER_DIAGNOSTICS", data), encoding="utf-8")
    (folder / "breakdowns.js").write_text(
        as_script("SENTIER_DIAGNOSTICS_BREAKDOWNS", dict(breakdowns or {})), encoding="utf-8"
    )
    return folder / "index.html"


def named_breakdowns(data: Mapping, beside: Path) -> tuple[dict, list[str]]:
    """The breakdowns a file names that lie beside it, read; and the names of those that
    do not (a project may keep them to itself)."""
    found, absent = {}, []
    names = sorted({f for item in data["items"] for f in (item["breakdowns"] or {}).values()})
    for name in names:
        path = Path(beside) / name
        if not path.is_file():
            absent.append(name)
            continue
        found[name] = json.loads(path.read_text(encoding="utf-8"))
    return found, absent
