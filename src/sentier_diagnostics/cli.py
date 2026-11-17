"""The command `sentier-diagnostics`: check, build, summarise and show diagnostics files.

sentier-diagnostics check FILE [FILE ...]      exit 1 if any file is not one a page shows
                                               (a matrix beside a file is checked against it,
                                               a fixes file against the file it names)
sentier-diagnostics build DESCRIPTION --out FILE
sentier-diagnostics summary FILE
sentier-diagnostics page FILE --out FOLDER
sentier-diagnostics example --out FOLDER
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__, breakdown, chain, example, fileformat, fixes, from_tables, matrix, page, summary


def check(paths) -> int:
    failed = 0
    for path in paths:
        try:
            data = fileformat.load_json(path)
        except ValueError as error:
            print(f"FAIL {error}")
            failed += 1
            continue
        if isinstance(data, dict) and data.get("format") == breakdown.FORMAT:
            errors = breakdown.errors(data)
        elif isinstance(data, dict) and str(data.get("format", "")).startswith(matrix.FAMILY):
            errors = matrix.errors(data)  # against its file when the file is checked
        elif isinstance(data, dict) and str(data.get("format", "")).startswith(fixes.FAMILY):
            errors = fixes.errors(data)
            size = Path(path).stat().st_size
            if size > fixes.MAX_BYTES:
                errors.append(f"{size} bytes, and a page loads {fixes.MAX_BYTES} at most")
            if not errors:
                errors = fixes.beside(data, Path(path).parent)
            if not errors:
                print(f"note {path}: {fixes.size_note(data)}")
        else:
            errors = fileformat.errors(data)
            size = Path(path).stat().st_size
            if size > fileformat.MAX_BYTES:
                errors.append(
                    f"{size} bytes, and a page holds {fileformat.MAX_BYTES} at most: list fewer items"
                )
            if not errors:
                try:
                    found, absent = page.named_breakdowns(data, Path(path).parent)
                except ValueError as error:
                    found, absent = {}, []
                    errors.append(str(error))
                errors += page.breakdown_errors(data, found)
                for name in absent:
                    print(f"note {path}: names the breakdown {name}, which is not beside it (not checked)")
                if data.get("matrix"):
                    try:
                        if page.named_matrix(data, Path(path).parent) is None:
                            print(
                                f"note {path}: names the matrix {data['matrix']['file']}, which is not beside it (not checked)"
                            )
                    except ValueError as error:
                        errors.append(str(error))
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
    one = commands.add_parser("check", help="check diagnostics, breakdown, matrix and fixes files")
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
            data, full = from_tables.build_with_matrix(args.description)
            chain.write(data, args.out)
            if full is None:
                print(f"wrote {args.out}")
                return 0
            beside = matrix.write(full, Path(args.out).parent / data["matrix"]["file"])
            print(f"wrote {args.out} and its matrix {beside}")
            return 0
        if args.command == "summary":
            print(summary.text(chain.read(args.file)), end="")
            return 0
        if args.command == "page":
            data = chain.read(args.file)
            found, absent = page.named_breakdowns(data, args.file.parent)
            full = page.named_matrix(data, args.file.parent)
            where = page.write(data, args.out, found, full)
            for name in absent:
                print(f"note: the breakdown {name} is not beside the file; the page says so")
            if data.get("matrix") and full is None:
                print(
                    f"note: the matrix {data['matrix']['file']} is not beside the file; the page shows the listed items and says so"
                )
            print(f"wrote {where}")
            return 0
        if args.command == "example":
            data = example.build()
            chain.write(data, args.out / chain.FILE)
            one = example.wheat_breakdown()
            breakdown.write(one, args.out / "p01-fix-1.json")
            where = page.write(data, args.out / "page", {"p01-fix-1.json": one})
            local, full = example.build_local()
            chain.write(local, args.out / "local" / chain.FILE)
            matrix.write(full, args.out / "local" / local["matrix"]["file"])
            local_page = page.write(local, args.out / "local" / "page", None, full)
            print(
                f"wrote {args.out / chain.FILE} and {where}; the local example and its matrix: {local_page}"
            )
            return 0
    except (ValueError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 2
