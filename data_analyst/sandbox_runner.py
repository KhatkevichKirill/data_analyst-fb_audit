"""Host script for python_exec calls — runs INSIDE bwrap, never on the main host.

Invoked by `tools._run_in_sandbox`. Reads user code from stdin, executes it in
an `exec()` scope pre-loaded with the requested parquet results (q1, q2, …) and
a curated set of analytics modules. Emits marker lines for inline charts/tables.

Defense in depth (do not rely on any single layer):
  - bwrap mounts / namespace isolation (parent harness)
  - resource.setrlimit caps applied here for AS/CPU/FSIZE/NOFILE
  - python -I (parent runs the interpreter in isolated mode)
"""
from __future__ import annotations

import argparse
import io
import json
import os
import re
import resource
import signal
import sys
import traceback
from pathlib import Path


_RESULT_ID_RE = re.compile(r"^q\d+$")
# RLIMIT_AS caps *virtual address space*, not RSS — pandas + scipy +
# statsmodels + single-threaded OpenBLAS need ~700 MiB of VAS at import. A
# 1024 MiB cap is the lowest value that lets the analytics stack boot while
# still killing a runaway `[0] * 10**9` allocation (>4 GiB) immediately.
_RLIMIT_AS = 1024 * 1024 * 1024
_RLIMIT_CPU_SOFT = 60                       # 60s CPU time, soft (SIGXCPU)
_RLIMIT_CPU_HARD = 65                       # 65s CPU time, hard (SIGKILL)
_RLIMIT_FSIZE = 50 * 1024 * 1024            # 50 MiB max single-file write
_RLIMIT_NOFILE = 64


def _apply_rlimits() -> None:
    resource.setrlimit(resource.RLIMIT_AS, (_RLIMIT_AS, _RLIMIT_AS))
    resource.setrlimit(resource.RLIMIT_CPU, (_RLIMIT_CPU_SOFT, _RLIMIT_CPU_HARD))
    resource.setrlimit(resource.RLIMIT_FSIZE, (_RLIMIT_FSIZE, _RLIMIT_FSIZE))
    resource.setrlimit(resource.RLIMIT_NOFILE, (_RLIMIT_NOFILE, _RLIMIT_NOFILE))


def _install_signal_handler() -> None:
    def _xcpu(signum, frame):  # noqa: ARG001
        sys.stderr.write("\n[sandbox] CPU time limit exceeded (RLIMIT_CPU).\n")
        sys.stderr.flush()
        os._exit(2)
    try:
        signal.signal(signal.SIGXCPU, _xcpu)
    except (ValueError, OSError):
        pass


class _Fb:
    """Helpers exposed to user code as the global name `fb`."""

    @staticmethod
    def emit_chart(spec: dict) -> None:
        """Emit a Vega-Lite spec to be rendered inline by the notebook UI."""
        sys.stdout.write("__FB_CHART__\t" + json.dumps(spec, default=str) + "\n")
        sys.stdout.flush()

    @staticmethod
    def emit_table(df, title=None) -> None:
        """Render a DataFrame as a real HTML table (first 200 rows max)."""
        import pandas as _pd
        if not isinstance(df, _pd.DataFrame):
            df = _pd.DataFrame(df)
        rows = df.head(200).to_dict(orient="records")
        cols = [str(c) for c in df.columns]
        payload = {"title": title, "columns": cols, "rows": rows}
        sys.stdout.write("__FB_TABLE__\t" + json.dumps(payload, default=str) + "\n")
        sys.stdout.flush()


def _load_results(workspace: Path, load: list[str]) -> dict:
    """Read each requested q<N>.parquet into a DataFrame named the same."""
    import pandas as pd
    out: dict = {}
    for name in load:
        if not _RESULT_ID_RE.match(name):
            raise ValueError(f"invalid result_id: {name!r}")
        path = workspace / "results" / f"{name}.parquet"
        if not path.is_file():
            raise FileNotFoundError(f"result_id not found: {name}")
        out[name] = pd.read_parquet(path)
    return out


def _build_globals(loaded: dict) -> dict:
    import pandas as pd
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from scipy import stats
    import statsmodels.api as sm

    g: dict = {
        "__name__": "__sandbox__",
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "plt": plt,
        "stats": stats,
        "sm": sm,
        "fb": _Fb,
    }
    try:
        import seaborn as sns  # optional
        g["sns"] = sns
    except ImportError:
        pass
    g.update(loaded)
    return g


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--load", default="[]")
    args = parser.parse_args(argv)

    _apply_rlimits()
    _install_signal_handler()

    workspace = Path(args.workspace)
    try:
        load_list = json.loads(args.load)
        if not isinstance(load_list, list):
            raise ValueError("--load must be a JSON list")
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write(f"[sandbox] bad --load: {e}\n")
        return 2

    try:
        os.chdir(workspace)
    except OSError as e:
        sys.stderr.write(f"[sandbox] cannot chdir to workspace: {e}\n")
        return 2

    try:
        loaded = _load_results(workspace, load_list)
    except (ValueError, FileNotFoundError) as e:
        sys.stderr.write(f"[sandbox] {e}\n")
        return 2

    code = sys.stdin.read()
    if not code.strip():
        sys.stderr.write("[sandbox] empty code\n")
        return 2

    try:
        compiled = compile(code, "<python_exec>", "exec")
    except SyntaxError:
        traceback.print_exc(file=sys.stderr)
        return 1

    g = _build_globals(loaded)

    try:
        exec(compiled, g)
    except SystemExit:
        raise
    except MemoryError:
        sys.stderr.write("\n[sandbox] MemoryError (RLIMIT_AS exceeded).\n")
        return 1
    except BaseException:
        # Trim internal sandbox-runner frames from the traceback to keep the
        # error focused on the user's code.
        tb = sys.exc_info()[2]
        # Skip frames whose filename is this runner.
        while tb and tb.tb_frame.f_code.co_filename == __file__:
            tb = tb.tb_next
        exc_type, exc_val, _ = sys.exc_info()
        formatted = traceback.format_exception(exc_type, exc_val, tb)
        sys.stderr.write("".join(formatted))
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
