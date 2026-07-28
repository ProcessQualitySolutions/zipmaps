"""Bundled zipmap runner — every script as a subcommand, chained in one process.

Each `python scripts/<name>.py` is a fresh interpreter: ~20 ms to start, ~35 ms
to import the library, and 45-60 ms more the first time pymupdf or jsonschema is
touched. Chaining through one process pays that once instead of once per step.

    python scripts/zm.py save mymap                        # single command
    python scripts/zm.py save mymap :: to_json mymap :: render mymap
    python scripts/zm.py --json save mymap :: validate mymap
    python scripts/zm.py --file jobs.json                  # or --stdin

Steps are separated by `::` (no quoting needed in bash, PowerShell, or cmd).
A chain stops at the first failing step unless -k/--keep-going is given; the
steps it did not reach are reported as skipped. A single command with no
separator is a byte-identical passthrough to running that script directly.

Every subcommand's flags are exactly its script's flags, because this dispatches
to that script's own main(argv) rather than redeclaring anything. So
`zm.py save --help` IS `save.py --help`.

Not implemented on purpose: a cross-step cache of validate_folder() results.
Measured, a second validate_folder in the same process costs 1.5 ms — the 60 ms
the first one appears to cost is the lazy `import jsonschema` inside
schema.validate_instance, which running in one process already pays only once.
It would also be dangerous: pipeline.save calls the module-global
validate_folder, while jsonpack holds a bound copy taken at import time, so
patching one path silently leaves the save gate alone. Do not add it.
"""

from __future__ import annotations

import argparse
import importlib
import io
import json
import re
import shlex
import sys
import time
import traceback
from contextlib import nullcontext, redirect_stderr, redirect_stdout
from pathlib import Path

# This file must live in scripts/. Running `python scripts/zm.py` puts scripts/
# on sys.path, which is what lets `import save` work at all and what makes
# print_pdf.py's `from view import PALETTE, read_map` resolve. Insert it
# explicitly so -P / PYTHONSAFEPATH cannot take it away.
SCRIPTS_DIR = Path(__file__).resolve().parent
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import _bootstrap  # noqa: F401,E402  (adds ../src to sys.path)

PROG = "zm.py"
DEFAULT_SEP = "::"

# name -> (module in scripts/, one-line summary). The summaries are the only
# duplicated help text here; the authoritative help is each script's own
# docstring, reachable with `zm.py <cmd> --help`.
COMMANDS: dict[str, str] = {
    "init": "scaffold a working folder (schemata/, pdf/, img/)",
    "save": "run the save pipeline and write <name>.zipmap",
    "open": "extract a .zipmap/.zipmapt, validate, summarize",
    "validate": "check a folder, .zipmap, .zipmapt, or .zipmap.json",
    "to_json": "export a .zipmap.json interchange document",
    "render": "static HTML overlay (embedded PNG + SVG pins)",
    "view": "interactive single-file HTML viewer",
    "print_pdf": "paginated PDF map sheet (needs fpdf2)",
    "make_template": "build a .zipmapt from a folder, .zipmap, or --types",
    "pdf2img": "single-page PDF -> PNG at a DPI (needs pymupdf)",
    "transform": "PDF-space -> pixel-space data conversion",
}
ALIASES = {"json": "to_json", "template": "make_template", "export": "to_json"}

# Globals that take a separate value, so the splitter knows to skip two tokens.
VALUE_GLOBALS = {"--file", "-f", "--sep", "--cd", "--max-output"}

#: Scripts announce what they produced on stdout. init.py says "wrote
#: placeholder img/drawing.png (800x600)" and open.py says "extracted to <dir>";
#: everything else says "wrote <path>" possibly followed by " (12.3 KiB)".
#: Best-effort only — a miss yields [] and never fails a step.
_WROTE = re.compile(r"^(?:wrote(?: placeholder)?|extracted to) (.+?)(?: \([^()]*\))?$")


class ZmError(Exception):
    """A problem with the chain itself, not with any step's work."""


# ---------------------------------------------------------------------------
# parsing


class Step:
    __slots__ = ("cmd", "argv", "tolerant")

    def __init__(self, cmd: str, argv: list[str], tolerant: bool = False):
        self.cmd = cmd
        self.argv = argv
        self.tolerant = tolerant

    def __repr__(self) -> str:
        return f"Step({self.cmd!r}, {self.argv!r}, tolerant={self.tolerant})"

    @property
    def display(self) -> str:
        return " ".join([self.cmd, *self.argv])


def split_globals(argv: list[str]) -> tuple[list[str], list[str]]:
    """Split leading global flags from the chain.

    Globals must precede the first command name; the first bare token ends
    them. Doing this by hand rather than with argparse subparsers is what lets
    every subcommand keep its own flags verbatim, including flags that collide
    with a global name.
    """
    i = 0
    while i < len(argv):
        tok = argv[i]
        if tok == "--":
            i += 1
            break
        if not tok.startswith("-"):
            break
        i += 2 if (tok in VALUE_GLOBALS and "=" not in tok) else 1
    return argv[:i], argv[i:]


def resolve(name: str) -> str:
    return ALIASES.get(name, name)


def parse_chain(tokens: list[str], sep: str) -> list[Step]:
    """Split `a x :: b y` into steps. An empty segment is dropped here and
    caught by plan_errors only when it leaves nothing to run."""
    steps: list[Step] = []
    current: list[str] = []
    for tok in [*tokens, sep]:
        if tok == sep:
            if current:
                steps.append(Step(resolve(current[0]), current[1:]))
            current = []
        else:
            current.append(tok)
    return steps


def tokenize_line(line: str) -> list[str]:
    """Split a job-file line into argv.

    shlex with escaping disabled: the default posix mode eats backslashes,
    which would silently destroy every Windows path in a job file. Quotes still
    group, so --title "Unit 3 CW Iso" works.
    """
    lex = shlex.shlex(line, posix=True)
    lex.whitespace_split = True
    lex.escape = ""
    lex.commenters = "#"
    return list(lex)


def parse_jobs(text: str) -> tuple[list[Step], dict]:
    """Parse a job file: JSON if it starts with { or [, else one command a line."""
    stripped = text.lstrip()
    if stripped[:1] in ("{", "["):
        try:
            doc = json.loads(text)
        except ValueError as exc:
            raise ZmError(f"job file is not valid JSON ({exc})") from exc
        opts = doc if isinstance(doc, dict) else {}
        raw = doc if isinstance(doc, list) else doc.get("steps")
        if not isinstance(raw, list):
            raise ZmError('job file needs a "steps" array')
        steps = []
        for i, entry in enumerate(raw):
            if not isinstance(entry, dict) or not isinstance(entry.get("cmd"), str):
                raise ZmError(f'steps[{i}]: needs a "cmd" string')
            args = entry.get("args", [])
            if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                raise ZmError(f'steps[{i}]: "args" must be an array of strings')
            steps.append(Step(resolve(entry["cmd"]), list(args), bool(entry.get("tolerant"))))
        return steps, opts

    steps = []
    for line in text.splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        tolerant = line.lstrip().startswith("?")
        tokens = tokenize_line(line.lstrip().lstrip("?"))
        if tokens:
            steps.append(Step(resolve(tokens[0]), tokens[1:], tolerant))
    return steps, {}


def plan_errors(steps: list[Step], as_json: bool) -> list[str]:
    """Everything wrong with the plan, so a typo in step 4 runs nothing at all."""
    problems = []
    if not steps:
        problems.append("no commands given")
    for i, step in enumerate(steps, 1):
        if step.cmd not in COMMANDS:
            close = ", ".join(sorted(c for c in COMMANDS if c.startswith(step.cmd[:2])))
            problems.append(
                f"step {i}: unknown command {step.cmd!r}"
                + (f" (did you mean: {close}?)" if close else "")
                + f" — run `{PROG} --list`"
            )
        elif as_json and step.cmd == "to_json" and "--stdout" in step.argv:
            problems.append(
                f"step {i}: `to_json --stdout` writes the document itself to stdout, "
                f"which would embed a base64 PNG in a JSON line — use -o FILE, or run "
                f"it as its own invocation without --json"
            )
    return problems


# ---------------------------------------------------------------------------
# execution


def load_command(name: str):
    """Import a scripts/ module by plain name.

    By name, never from a file path: print_pdf.py does `from view import ...`,
    and loading view under an alias would give it a second, separate copy.
    """
    mod = importlib.import_module(name)
    where = getattr(mod, "__file__", None)
    if not where or Path(where).resolve().parent != SCRIPTS_DIR:
        raise ZmError(f"{name!r} resolved to {where}, not {SCRIPTS_DIR}")
    return mod


class StepResult:
    __slots__ = ("index", "total", "step", "status", "exit_code", "ms",
                 "stdout", "stderr", "outputs", "traceback")

    def __init__(self, index, total, step, status, exit_code, ms,
                 stdout="", stderr="", outputs=None, tb=None):
        self.index, self.total, self.step = index, total, step
        self.status, self.exit_code, self.ms = status, exit_code, ms
        self.stdout, self.stderr = stdout, stderr
        self.outputs = outputs or []
        self.traceback = tb

    def as_dict(self, max_output: int) -> dict:
        def clip(s):
            return s if len(s) <= max_output else s[:max_output]
        d = {
            "type": "step", "i": self.index, "n": self.total,
            "cmd": self.step.cmd, "argv": self.step.argv,
            "status": self.status, "exit_code": self.exit_code,
            "ms": round(self.ms), "stdout": clip(self.stdout),
            "stderr": clip(self.stderr), "outputs": self.outputs,
        }
        if len(self.stdout) > max_output or len(self.stderr) > max_output:
            d["output_truncated"] = True
        if self.traceback:
            d["traceback"] = clip(self.traceback)
        return d


def extract_outputs(text: str) -> list[str]:
    found = []
    for line in text.splitlines():
        m = _WROTE.match(line.strip())
        if m:
            found.append(m.group(1))
    return found


def run_step(step: Step, index: int, total: int, capture: bool) -> StepResult:
    try:
        mod = load_command(step.cmd)
    except Exception:
        return StepResult(index, total, step, "crashed", 70, 0.0,
                          stderr=traceback.format_exc(), tb=traceback.format_exc())

    out, err = io.StringIO(), io.StringIO()
    saved_argv0 = sys.argv[0]
    sys.argv[0] = f"{PROG} {step.cmd}"          # drives argparse's usage line
    tb = None
    t0 = time.perf_counter()
    try:
        if capture:
            with redirect_stdout(out), redirect_stderr(err):
                code = mod.main(step.argv)
        else:
            with nullcontext():
                code = mod.main(step.argv)
        code = 0 if code is None else int(code)
        status = "ok" if code == 0 else "failed"
    except SystemExit as exc:                    # parser.error -> 2, --help -> 0
        c = exc.code
        if c is None:
            code, status = 0, "ok"
        elif isinstance(c, int):
            code = c
            status = "ok" if c == 0 else ("usage_error" if c == 2 else "failed")
        else:                                    # SystemExit("message")
            (err if capture else sys.stderr).write(f"{c}\n")
            code, status = 1, "failed"
    except KeyboardInterrupt:
        raise
    except BaseException:                        # a crash must not eat the chain
        tb = traceback.format_exc()
        (err if capture else sys.stderr).write(tb)
        code, status = 70, "crashed"
    finally:
        sys.argv[0] = saved_argv0
        ms = (time.perf_counter() - t0) * 1000

    so, se = out.getvalue(), err.getvalue()
    return StepResult(index, total, step, status, code, ms, so, se,
                      extract_outputs(so), tb)


def run_chain(steps, *, keep_going, force, as_json, dry_run, max_output) -> int:
    total = len(steps)
    single = total == 1 and not as_json

    if not single:
        for stream in (sys.stdout, sys.stderr):
            if hasattr(stream, "reconfigure"):
                # line buffering so partial output survives a kill on a pipe;
                # errors="replace" so an em dash cannot abort a run on a cp1252 console
                try:
                    stream.reconfigure(line_buffering=True, errors="replace")
                except (ValueError, OSError):
                    pass

    if dry_run:
        for i, s in enumerate(steps, 1):
            print(f"[{i}/{total}] {s.display}" + ("  (tolerant)" if s.tolerant else ""))
        return 0

    if as_json:
        print(json.dumps({"type": "chain_start", "n": total, "cwd": str(Path.cwd()),
                          "keep_going": keep_going}), flush=True)

    t0 = time.perf_counter()
    results, first_bad, ran = [], None, 0

    for i, step in enumerate(steps, 1):
        if not single and not as_json:
            print(f"==> [{i}/{total}] {step.display}", flush=True)

        res = run_step(step, i, total, capture=not single)
        results.append(res)
        ran += 1

        if as_json:
            print(json.dumps(res.as_dict(max_output)), flush=True)
        elif not single:
            if res.stdout:
                sys.stdout.write(res.stdout)
                sys.stdout.flush()
            if res.stderr:
                sys.stderr.write(res.stderr)
                sys.stderr.flush()
            print(f"<-- {res.status} ({res.exit_code}) in {res.ms/1000:.2f}s", flush=True)

        if res.status == "ok" or step.tolerant:
            continue
        if first_bad is None:
            first_bad = res
        # a crash may have left a folder half-regenerated (save unlinks stale
        # img/*.json before rewriting), so later steps must not run on it
        if keep_going and (res.status != "crashed" or force):
            continue
        for j in range(i + 1, total + 1):
            skipped = StepResult(j, total, steps[j - 1], "skipped", None, 0.0)
            results.append(skipped)
            if as_json:
                print(json.dumps(skipped.as_dict(max_output)), flush=True)
        break

    elapsed = (time.perf_counter() - t0) * 1000
    ok_count = sum(1 for r in results if r.status == "ok")
    exit_code = 0 if first_bad is None else (first_bad.exit_code or 1)

    if as_json:
        print(json.dumps({
            "type": "chain", "ok": first_bad is None, "total": total, "ran": ran,
            "failed_at": first_bad.index if first_bad else None,
            "exit_code": exit_code, "ms": round(elapsed),
        }), flush=True)
    elif not single:
        verdict = "ok" if first_bad is None else f"FAILED at step {first_bad.index}"
        print(f"=== chain: {ok_count}/{total} {verdict} in {elapsed/1000:.2f}s", flush=True)

    return exit_code


# ---------------------------------------------------------------------------
# entry point


def _epilog() -> str:
    width = max(len(c) for c in COMMANDS)
    lines = ["commands:"]
    lines += [f"  {c:<{width}}  {s}" for c, s in COMMANDS.items()]
    lines.append("")
    lines.append(f"`{PROG} <command> --help` shows that command's own flags.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    globals_argv, rest = split_globals(argv)

    parser = argparse.ArgumentParser(
        prog=PROG, description=__doc__, epilog=_epilog(),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("-k", "--keep-going", action="store_true",
                        help="continue after a step fails (still stops on a crash)")
    parser.add_argument("--force", action="store_true",
                        help="with -k, continue even after a step crashes")
    parser.add_argument("--json", dest="as_json", action="store_true",
                        help="emit JSON Lines: one object per step, flushed as it finishes")
    parser.add_argument("-f", "--file", help="read the chain from a job file ('-' = stdin)")
    parser.add_argument("--stdin", action="store_true", help="shorthand for --file -")
    parser.add_argument("--sep", default=DEFAULT_SEP,
                        help=f"chain separator (default {DEFAULT_SEP})")
    parser.add_argument("--cd", help="change to this directory before running")
    parser.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    parser.add_argument("--list", action="store_true", help="list the available commands")
    parser.add_argument("--max-output", type=int, default=65536,
                        help="per-step captured output cap in --json mode (default %(default)s)")
    args = parser.parse_args(globals_argv)

    if args.list:
        if args.as_json:
            print(json.dumps({"commands": [{"cmd": c, "summary": s} for c, s in COMMANDS.items()],
                              "aliases": ALIASES}))
        else:
            print(_epilog())
        return 0

    source = "-" if args.stdin else args.file
    try:
        if source:
            if rest:
                raise ZmError("pass a chain or --file, not both")
            text = sys.stdin.read() if source == "-" else Path(source).read_text(encoding="utf-8")
            steps, opts = parse_jobs(text)
            if opts.get("keep_going"):
                args.keep_going = True
        else:
            steps = parse_chain(rest, args.sep)
    except (ZmError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    problems = plan_errors(steps, args.as_json)
    if problems:
        for p in problems:
            print(f"ERROR: {p}", file=sys.stderr)
        return 2

    if args.cd:
        import os

        try:
            os.chdir(args.cd)
        except OSError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 2

    try:
        return run_chain(steps, keep_going=args.keep_going, force=args.force,
                         as_json=args.as_json, dry_run=args.dry_run,
                         max_output=args.max_output)
    except KeyboardInterrupt:
        print("\ninterrupted", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
