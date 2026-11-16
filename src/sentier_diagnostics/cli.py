"""The command `sentier-diagnostics`: check, build, summarise and show diagnostics files.

    sentier-diagnostics check FILE [FILE ...]      exit 1 if any file is not one a page shows
    sentier-diagnostics build DESCRIPTION --out FILE
    sentier-diagnostics summary FILE
    sentier-diagnostics page FILE --out FOLDER
    sentier-diagnostics example --out FOLDER
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, breakdown, chain, example, fileformat, from_tables, page, summary


def _load(path: Path):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"), parse_constant=chain._refuse)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ValueError(f"{path}: cannot be read ({error})") from None


def check(paths) -> int:
    failed = 0
    for path in paths:
        try:
            data = _load(path)
        except ValueError as error:
            print(f"FAIL {error}")
            failed += 1
            continue
        if isinstance(data, dict) and data.get("format") == breakdown.FORMAT:
            errors = breakdown.errors(data)
        else:
            errors = fileformat.errors(data)
            size = Path(path).stat().st_size
            if size > fileformat.MAX_BYTES:
                errors.append(f"{size} bytes, and a page holds {fileformat.MAX_BYTES} at most: list fewer items")
            if not errors:
                found, absent = page.named_breakdowns(data, Path(path).parent)
                for name, one in found.items():
                    errors += [f"{name}: {e}" for e in breakdown.errors(one) or breakdown.against(one, data)]
                for name in absent:
                    print(f"note {path}: names the breakdown {name}, which is not beside it (not checked)")
        if errors:
            failed += 1
            print(f"FAIL {path}")
            for line in errors:
                print(f"  {line}")
        else:
            print(f"ok   {path}")
    return 1 if failed else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="sentier-diagnostics", description=__doc__.splitlines()[0])
    parser.add_argument("--version", action="version", version=f"sentier-diagnostics {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    one = commands.add_parser("check", help="check diagnostics and breakdown files")
    one.add_argument("files", nargs="+", type=Path)
    one = commands.add_parser("build", help="build a diagnostics file from CSV tables")
    one.add_argument("description", type=Path)
    one.add_argument("--out", type=Path, required=True)
    one = commands.add_parser("summary", help="print a diagnostics file as Markdown")
    one.add_argument("file", type=Path)
    one = commands.add_parser("page", help="write the static page of a diagnostics file")
    one.add_argument("file", type=Path)
    one.add_argument("--out", type=Path, required=True)
    one = commands.add_parser("example", help="write the made-up example and its page")
    one.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)

    try:
        if args.command == "check":
            return check(args.files)
        if args.command == "build":
            chain.write(from_tables.build(args.description), args.out)
            print(f"wrote {args.out}")
            return 0
        if args.command == "summary":
            print(summary.text(chain.read(args.file)), end="")
            return 0
        if args.command == "page":
            data = chain.read(args.file)
            found, absent = page.named_breakdowns(data, args.file.parent)
            where = page.write(data, args.out, found)
            for name in absent:
                print(f"note: the breakdown {name} is not beside the file; the page says so")
            print(f"wrote {where}")
            return 0
        if args.command == "example":
            data = example.build()
            chain.write(data, args.out / chain.FILE)
            one = example.wheat_breakdown()
            breakdown.write(one, args.out / "p01-fix-1.json")
            where = page.write(data, args.out / "page", {"p01-fix-1.json": one})
            print(f"wrote {args.out / chain.FILE} and {where}")
            return 0
    except (ValueError, KeyError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2
