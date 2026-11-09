"""Read-only, flat-folder completeness checker. Python 3.10+; stdlib only."""
from __future__ import annotations
import argparse
import csv
import json
import re
import stat
import sys
import unicodedata
from pathlib import Path

class InputError(ValueError):
    """The plan or directory cannot be checked safely and unambiguously."""

def filename_key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()

def validate_filename(name: str) -> None:
    if not name or name in {".", ".."} or len(name) > 180 or len(name.encode("utf-8")) > 180:
        raise InputError("invalid output filename")
    if name != name.strip() or name.endswith("."):
        raise InputError("output filenames cannot have outer whitespace or a trailing dot")
    if any(c in '<>:"/\\|?*' or unicodedata.category(c).startswith("C") for c in name):
        raise InputError("output filenames must be a single portable filename")
    stem = name.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(?:COM|LPT)[1-9¹²³]", stem):
        raise InputError("reserved Windows filename")

def read_plan(path: Path) -> list[dict[str, str]]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.reader(handle, strict=True)
            if next(reader, None) != ["id", "file"]:
                raise InputError("CSV header must be exactly: id,file")
            rows: list[dict[str, str]] = []
            ids: set[str] = set()
            files: set[str] = set()
            for row in reader:
                if len(row) != 2:
                    raise InputError(f"CSV record ending on line {reader.line_num}: expected 2 fields")
                ident, filename = row
                if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", ident):
                    raise InputError(f"CSV line {reader.line_num}: id must use letters, digits, _ or -")
                if ident in ids:
                    raise InputError(f"CSV line {reader.line_num}: duplicate id")
                validate_filename(filename)
                key = filename_key(filename)
                if key in files:
                    raise InputError(f"CSV line {reader.line_num}: duplicate or case-equivalent filename")
                ids.add(ident)
                files.add(key)
                rows.append({"id": ident, "file": filename})
            if not rows:
                raise InputError("plan must contain at least one output")
            return rows
    except (OSError, UnicodeError, csv.Error) as exc:
        raise InputError(f"cannot read plan: {exc}") from exc

def inspect(plan: list[dict[str, str]], output_dir: Path) -> dict:
    try:
        mode = output_dir.lstat().st_mode
        if not stat.S_ISDIR(mode):
            raise InputError("output must be an ordinary directory, not a file or symlink")
        entries = sorted(output_dir.iterdir(), key=lambda p: p.name)
        sizes: dict[str, int] = {}
        blocked: list[str] = []
        for entry in entries:
            info = entry.lstat()
            if not stat.S_ISREG(info.st_mode):
                blocked.append(entry.name)
            else:
                sizes[entry.name] = info.st_size
    except OSError as exc:
        raise InputError(f"cannot inspect output directory: {exc}") from exc
    expected = {row["file"] for row in plan}
    missing = [row for row in plan if row["file"] not in sizes]
    empty = [row for row in plan if row["file"] in sizes and sizes[row["file"]] == 0]
    extra = sorted(set(sizes) - expected)
    ok = len(plan) - len(missing) - len(empty)
    return {"status": "FAIL" if missing or empty or extra or blocked else "PASS",
            "expected": len(plan), "ok": ok, "missing": missing,
            "empty": empty, "extra": extra, "blocked": blocked}

def summary(result: dict) -> str:
    return (f"{result['status']} expected={result['expected']} ok={result['ok']} "
            f"missing={len(result['missing'])} empty={len(result['empty'])} "
            f"extra={len(result['extra'])} blocked={len(result['blocked'])}")

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--json", action="store_true", help="print a machine-readable report")
    args = parser.parse_args(argv)
    try:
        result = inspect(read_plan(args.plan), args.output)
    except InputError as exc:
        print(json.dumps({"status": "ERROR", "message": str(exc)}, ensure_ascii=True), file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    else:
        print(summary(result))
        for category in ("missing", "empty", "extra", "blocked"):
            for item in result[category]:
                # Escape control characters instead of executing terminal sequences.
                print(f"{category.upper()} {json.dumps(item, ensure_ascii=True)}")
    return 0 if result["status"] == "PASS" else 1

if __name__ == "__main__":
    raise SystemExit(main())
