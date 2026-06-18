"""Tool implementations for data_analyst.

Tools:
- `sql`         — read-only SELECT/WITH against meta_ads (markdown table)
- `read_wiki`   — read analyst wiki page
- `chart`       — run a SELECT and render result as a Vega-Lite v5 spec
- `python_exec` — bwrap-sandboxed Python over parquet results of prior `sql` calls
"""
from __future__ import annotations

import csv as _csv
import datetime as _dt
import json
import logging
import os
import re
import subprocess
import sys as _sys
from decimal import Decimal
from pathlib import Path
from typing import Any

import psycopg2

from config import (
    knowledge_dir,
    prefixed,
    python_exec_enabled,
    sandbox_python,
)

_log = logging.getLogger(__name__)

_WIKI_DIR = knowledge_dir()
_WIKI_PAGES = (
    "readme",
    "onboarding",
    "reference",
    "schema",
    "weekly_playbook",
)

_SELECT_RE = re.compile(r"^\s*(SELECT|WITH)\b", re.IGNORECASE)
_STMT_TIMEOUT_MS = 30_000
_DEFAULT_LIMIT = 100
_SQL_PERSIST_LIMIT = 50_000
_MAX_CELL_CHARS = 200

# python_exec sandbox
_SANDBOX_VENV_PYTHON = sandbox_python()
_SANDBOX_RUNNER = Path(__file__).resolve().parent / "sandbox_runner.py"
_PYEXEC_DEFAULT_TIMEOUT = 60
_PYEXEC_MAX_CODE_CHARS = 16_000
_PYEXEC_STDOUT_LIMIT = 8_000
_PYEXEC_PLOT_MAX_BYTES = 5 * 1024 * 1024
_PYEXEC_PLOT_EXTS = {".png", ".svg", ".jpg", ".jpeg"}
_RESULT_ID_RE = re.compile(r"^q\d+$")

_CHART_DEFAULT_ROWS = 5000
_CHART_MAX_ROWS = 10000
_CHART_MARKS = ("line", "bar", "point", "area", "tick")
_CHART_FIELD_TYPES = ("quantitative", "temporal", "nominal", "ordinal")
_CHART_ORIENTS = ("vertical", "horizontal")

# Bright categorical palette — overrides ggplot2 theme's muted defaults via
# spec.config. First four colors are the most distinguishable; ordering matters.
# `_CHART_PALETTE[0]` doubles as the single-series default color.
_CHART_PALETTE = [
    "#4C9AFF",  # light blue
    "#FF6B6B",  # coral
    "#FFA94D",  # orange
    "#51CF66",  # green
    "#9775FA",  # purple
    "#22B8CF",  # cyan
    "#FFD43B",  # yellow
    "#FF8CC8",  # pink
]


def _strip_sql_comments(s: str) -> str:
    s = re.sub(r"--[^\n]*", "", s)
    s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
    return s


def _is_safe(sql: str) -> tuple[bool, str]:
    cleaned = _strip_sql_comments(sql).strip().rstrip(";").strip()
    if not cleaned:
        return False, "empty query"
    if ";" in cleaned:
        return False, "multiple statements not allowed"
    if not _SELECT_RE.match(cleaned):
        return False, "only SELECT or WITH statements allowed"
    return True, ""


def _format_cell(v) -> str:
    s = "" if v is None else str(v)
    if len(s) > _MAX_CELL_CHARS:
        s = s[: _MAX_CELL_CHARS - 1] + "…"
    return s.replace("|", "\\|").replace("\n", " ")


def _format_rows(rows, columns) -> str:
    if not rows:
        return "(0 rows)"
    header = "| " + " | ".join(columns) + " |"
    sep = "| " + " | ".join(["---"] * len(columns)) + " |"
    body = "\n".join("| " + " | ".join(_format_cell(c) for c in r) + " |" for r in rows)
    return f"{header}\n{sep}\n{body}"


def _coerce_for_parquet(v: Any) -> Any:
    """Convert psycopg2-returned values into types pandas/parquet can store.

    Decimals → float; date → datetime; arbitrary objects stringified.
    """
    if v is None:
        return None
    if isinstance(v, (bool, int, float, str, bytes)):
        return v
    if isinstance(v, Decimal):
        try:
            return float(v)
        except (ValueError, OverflowError):
            return str(v)
    if isinstance(v, _dt.datetime):
        return v
    if isinstance(v, _dt.date):
        return _dt.datetime(v.year, v.month, v.day)
    if isinstance(v, _dt.time):
        return v.isoformat()
    return str(v)


def _next_result_id(results_dir: Path) -> str:
    """Allocate the next q<N>.parquet name; race-tolerant within single-tenant use."""
    n = 0
    for p in results_dir.glob("q*.parquet"):
        m = re.match(r"^q(\d+)$", p.stem)
        if m:
            n = max(n, int(m.group(1)))
    return f"q{n + 1}"


def _dedupe_columns(cols: list[str]) -> list[str]:
    """Make column names unique (`col`, `col__2`, …) — parquet rejects duplicates.

    SELECT-* joins legitimately repeat names (e.g. gd_file_id on both sides);
    persistence used to fail outright on them (observed 2026-06-02).
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for c in cols:
        if c in seen:
            seen[c] += 1
            out.append(f"{c}__{seen[c]}")
        else:
            seen[c] = 1
            out.append(c)
    return out


def _persist_sql_result(
    workspace: Path, cols: list[str], all_rows: list
) -> tuple[str | None, int | None, str | None, list[str]]:
    """Write SQL rows to <workspace>/results/<id>.parquet.

    Returns (id, persisted_rows, error_msg, columns_as_persisted).
    """
    cols = _dedupe_columns(cols)
    try:
        import pandas as pd  # local import — main venv has pyarrow + pandas
    except ImportError as e:
        return None, None, f"pandas import failed: {e}", cols
    results_dir = workspace / "results"
    try:
        results_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return None, None, f"mkdir results dir failed: {e}", cols

    coerced = [[_coerce_for_parquet(c) for c in row] for row in all_rows]
    try:
        df = pd.DataFrame(coerced, columns=cols)
    except Exception as e:  # noqa: BLE001
        return None, None, f"dataframe build failed: {type(e).__name__}: {e}", cols

    rid = _next_result_id(results_dir)
    out_path = results_dir / f"{rid}.parquet"
    try:
        df.to_parquet(out_path, engine="pyarrow", compression="snappy")
    except Exception as e:  # noqa: BLE001
        return None, None, f"parquet write failed: {type(e).__name__}: {e}", cols
    return rid, len(df), None, cols


def tool_sql(query: str, *, workspace: Path | None = None) -> str:
    ok, why = _is_safe(query)
    if not ok:
        return f"error: {why}"
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            options=f"-c statement_timeout={_STMT_TIMEOUT_MS}",
        )
    except psycopg2.Error as e:
        return f"connection error: {e}"
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(query)
            if cur.description is None:
                conn.rollback()
                return "(query executed but returned no result set)"
            cols = [d[0] for d in cur.description]
            # Fetch up to persist_limit + 1 so we can detect both model-facing
            # and persistence-level truncation in one round trip.
            rows = cur.fetchmany(_SQL_PERSIST_LIMIT + 1)
        conn.rollback()
    except psycopg2.Error as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return f"sql error: {e}"
    finally:
        conn.close()

    persist_truncated = len(rows) > _SQL_PERSIST_LIMIT
    rows = rows[:_SQL_PERSIST_LIMIT]
    model_truncated = len(rows) > _DEFAULT_LIMIT
    model_rows = rows[:_DEFAULT_LIMIT]

    out = f"_{len(model_rows)} row(s) returned_\n\n" + _format_rows(model_rows, cols)
    if model_truncated:
        out += (
            f"\n\n_(truncated to {_DEFAULT_LIMIT} for display; "
            f"add LIMIT or aggregate if you need exact counts)_"
        )

    # Persist all fetched rows (up to _SQL_PERSIST_LIMIT) for downstream
    # python_exec. Failure here must NOT fail the SQL call.
    if workspace is not None and rows:
        rid, persisted, err, persisted_cols = _persist_sql_result(workspace, cols, rows)
        if err:
            _log.warning("sql result persistence failed: %s", err)
            out += f"\n\n_(result not persisted: {err})_"
        elif rid is not None:
            note = (
                f"\n\n_Stored as result_id `{rid}` "
                f"({persisted} rows × {len(persisted_cols)} columns: {', '.join(persisted_cols)}). "
                f"Use `python_exec({{load: [\"{rid}\"], code: ...}})` to analyze further._"
            )
            if persisted_cols != cols:
                note += (
                    "\n\n_(duplicate column names were renamed with `__N` "
                    "suffixes in the stored result)_"
                )
            if persist_truncated:
                note += (
                    f"\n\n_(persisted result truncated to {_SQL_PERSIST_LIMIT} rows)_"
                )
            out += note
    return out


def tool_read_wiki(page: str) -> str:
    if page not in _WIKI_PAGES:
        return f"error: unknown page '{page}'. available: {list(_WIKI_PAGES)}"
    try:
        return (_WIKI_DIR / f"{page}.md").read_text()
    except OSError as e:
        return f"error reading {page}: {e}"


# --- chart tool ------------------------------------------------------------

def _coerce_for_json(v: Any) -> Any:
    """Make a single cell value JSON-serializable for Vega-Lite `data.values`."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float, str)):
        return v
    if isinstance(v, Decimal):
        try:
            return float(v)
        except (ValueError, OverflowError):
            return str(v)
    if isinstance(v, (_dt.datetime, _dt.date)):
        return v.isoformat()
    if isinstance(v, _dt.time):
        return v.isoformat()
    # Fallback — Vega-Lite can't parse arbitrary objects; stringify.
    return str(v)


def _chart_error(msg: str) -> dict:
    return {
        "kind": "chart_error",
        "error": msg,
        "summary": f"Chart error: {msg}",
    }


def _chart_quant_format(raw_rows, col_idx: int) -> str:
    """Vega-Lite numeric format: integer comma group if all values look integral."""
    seen = False
    for row in raw_rows[:50]:
        v = row[col_idx]
        if v is None or isinstance(v, bool):
            continue
        try:
            f = float(v)
        except (TypeError, ValueError):
            return ",.2f"
        seen = True
        if not f.is_integer():
            return ",.2f"
    return "," if seen else ",.2f"


def _chart_temporal_format(raw_rows, col_idx: int) -> str:
    """Vega-Lite date format: include time only if any sampled value has one."""
    for row in raw_rows[:5]:
        v = row[col_idx]
        if v is None:
            continue
        if isinstance(v, _dt.datetime):
            return "%Y-%m-%d %H:%M"
        if isinstance(v, str) and ("T" in v or " " in v.strip()):
            return "%Y-%m-%d %H:%M"
    return "%Y-%m-%d"


def _validate_field(spec: Any, name: str) -> tuple[bool, str, dict]:
    if not isinstance(spec, dict):
        return False, f"`{name}` must be an object with `field` and `type`", {}
    field = spec.get("field")
    typ = spec.get("type")
    if not isinstance(field, str) or not field:
        return False, f"`{name}.field` is required and must be a non-empty string", {}
    if typ not in _CHART_FIELD_TYPES:
        return False, (
            f"`{name}.type` must be one of {list(_CHART_FIELD_TYPES)} (got {typ!r})"
        ), {}
    title = spec.get("title")
    if title is not None and not isinstance(title, str):
        return False, f"`{name}.title` must be a string if provided", {}
    enc = {"field": field, "type": typ, "title": title or field}
    return True, "", enc


def tool_chart(args: dict) -> dict:
    sql = args.get("sql")
    mark = args.get("mark")
    if not isinstance(sql, str) or not sql.strip():
        return _chart_error("`sql` is required")
    if mark not in _CHART_MARKS:
        return _chart_error(
            f"`mark` must be one of {list(_CHART_MARKS)} (got {mark!r})"
        )

    ok, why = _is_safe(sql)
    if not ok:
        return _chart_error(why)

    # row_limit
    row_limit = args.get("row_limit", _CHART_DEFAULT_ROWS)
    if not isinstance(row_limit, int) or isinstance(row_limit, bool):
        return _chart_error("`row_limit` must be an integer")
    if row_limit <= 0:
        return _chart_error("`row_limit` must be > 0")
    if row_limit > _CHART_MAX_ROWS:
        row_limit = _CHART_MAX_ROWS

    # x / y / optional color / size — validate shape
    ok_x, why_x, x_enc = _validate_field(args.get("x"), "x")
    if not ok_x:
        return _chart_error(why_x)
    ok_y, why_y, y_enc = _validate_field(args.get("y"), "y")
    if not ok_y:
        return _chart_error(why_y)

    color_enc: dict | None = None
    if args.get("color") is not None:
        ok_c, why_c, color_enc = _validate_field(args.get("color"), "color")
        if not ok_c:
            return _chart_error(why_c)

    size_enc: dict | None = None
    if args.get("size") is not None:
        ok_s, why_s, size_enc = _validate_field(args.get("size"), "size")
        if not ok_s:
            return _chart_error(why_s)

    orient = args.get("orient", "vertical")
    if orient not in _CHART_ORIENTS:
        return _chart_error(
            f"`orient` must be one of {list(_CHART_ORIENTS)} (got {orient!r})"
        )

    stack = bool(args.get("stack", False))
    title = args.get("title")
    if title is not None and not isinstance(title, str):
        return _chart_error("`title` must be a string if provided")

    # Execute SQL (read-only).
    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            options=f"-c statement_timeout={_STMT_TIMEOUT_MS}",
        )
    except psycopg2.Error as e:
        return _chart_error(f"connection error: {e}")
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                conn.rollback()
                return _chart_error("query returned no result set")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(row_limit + 1)
        conn.rollback()
    except psycopg2.Error as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return _chart_error(f"sql error: {e}")
    finally:
        conn.close()

    if not rows:
        return _chart_error("query returned 0 rows — nothing to chart")

    truncated = len(rows) > row_limit
    rows = rows[:row_limit]

    # Sanity-check that referenced fields exist in the result columns.
    col_set = set(cols)
    for label, enc in (
        ("x", x_enc),
        ("y", y_enc),
        ("color", color_enc),
        ("size", size_enc),
    ):
        if enc is None:
            continue
        if enc["field"] not in col_set:
            return _chart_error(
                f"`{label}.field` {enc['field']!r} not in result columns. "
                f"available: {cols}"
            )

    # Convert rows to list of dicts with JSON-safe values.
    values = [
        {c: _coerce_for_json(v) for c, v in zip(cols, row)}
        for row in rows
    ]

    # Build the Vega-Lite v5 spec.
    if orient == "horizontal" and mark == "bar":
        # Swap x/y encodings server-side for horizontal bars.
        enc_x, enc_y = y_enc, x_enc
    else:
        enc_x, enc_y = x_enc, y_enc

    encoding: dict[str, Any] = {
        "x": dict(enc_x),
        "y": dict(enc_y),
    }
    # Stacking applies to the y encoding for bar/area only when grouped by color.
    if mark in ("bar", "area") and color_enc is not None:
        encoding["y"]["stack"] = "zero" if stack else None
    if color_enc is not None:
        encoding["color"] = dict(color_enc)
    if size_enc is not None:
        encoding["size"] = dict(size_enc)

    # Tooltip — aligned to the fields that are actually plotted, with sensible
    # per-type formats. Encoding.tooltip beats mark.tooltip and shows only the
    # encoded fields rather than every column the SQL happened to return.
    tooltip: list[dict[str, Any]] = []
    for enc in (x_enc, y_enc, color_enc, size_enc):
        if enc is None:
            continue
        item: dict[str, Any] = {
            "field": enc["field"],
            "type": enc["type"],
            "title": enc.get("title") or enc["field"],
        }
        col_idx = cols.index(enc["field"])
        if enc["type"] == "quantitative":
            item["format"] = _chart_quant_format(rows, col_idx)
        elif enc["type"] == "temporal":
            item["format"] = _chart_temporal_format(rows, col_idx)
        tooltip.append(item)
    encoding["tooltip"] = tooltip

    # Line/area need point markers — without them, hover has no hit target
    # between vertices. Bar/tick/point are already hittable as-is.
    if mark in ("line", "area"):
        mark_spec: Any = {"type": mark, "point": True}
    else:
        mark_spec = mark

    # Y-axis padding for non-stacked line/area: lift the top mark off the
    # chart edge so tooltips on the highest point aren't clipped. Stacked
    # area must still start at zero, so skip the override there.
    if mark in ("line", "area"):
        is_stacked = (mark == "area" and color_enc is not None and stack)
        if not is_stacked:
            encoding["y"]["scale"] = {"zero": False, "nice": True, "padding": 8}

    spec: dict[str, Any] = {
        "$schema": "https://vega.github.io/schema/vega-lite/v5.json",
        "title": title or None,
        "width": "container",
        "height": 320,
        "mark": mark_spec,
        "data": {"values": values},
        "encoding": encoding,
    }

    # Pan + zoom on continuous scales only. Interval selections on nominal /
    # ordinal axes don't behave sensibly and Vega-Lite logs warnings.
    _continuous = {"quantitative", "temporal"}
    if x_enc["type"] in _continuous and y_enc["type"] in _continuous:
        spec["params"] = [
            {"name": "grid", "select": "interval", "bind": "scales"}
        ]

    # Bright palette via spec.config — overrides the ggplot2 theme's muted
    # category range while keeping its axes / grid / typography. Both keys
    # always emitted: config.mark.color is used when no color encoding exists,
    # config.range.category when one does.
    cfg = spec.setdefault("config", {})
    cfg.setdefault("mark", {})["color"] = _CHART_PALETTE[0]
    cfg.setdefault("range", {})["category"] = list(_CHART_PALETTE)

    auto_summary = title or f"Chart of {y_enc['field']} vs {x_enc['field']}"
    summary = (
        f"Chart: {auto_summary} · {len(values)} rows · "
        f"{mark} of {y_enc['field']} vs {x_enc['field']}"
    )
    if truncated:
        summary += f" (truncated to {row_limit})"

    return {
        "kind": "chart",
        "summary": summary,
        "vega_lite_spec": spec,
        "truncated": truncated,
        "row_count": len(values),
    }


# --- export_csv tool -------------------------------------------------------

_CSV_DEFAULT_LIMIT = 50_000
_CSV_MAX_LIMIT = 50_000
_CSV_SAFE_CHAR_RE = re.compile(r"[^A-Za-z0-9._-]")


def _safe_csv_filename(name: str | None, outputs_dir: Path) -> str:
    if not name:
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"export_{ts}.csv"
    # Strip directory components.
    name = Path(name).name.lstrip(".")
    # Replace unsafe characters.
    name = _CSV_SAFE_CHAR_RE.sub("_", name)
    if not name:
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%d_%H%M%S")
        name = f"export_{ts}"
    # Force .csv extension.
    if not name.lower().endswith(".csv"):
        name = name + ".csv"
    # Avoid overwriting.
    if (outputs_dir / name).exists():
        stem = name[:-4]
        i = 1
        while (outputs_dir / f"{stem}_{i}.csv").exists():
            i += 1
        name = f"{stem}_{i}.csv"
    return name


def _coerce_for_csv(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, Decimal):
        return str(v)
    if isinstance(v, _dt.datetime):
        return v.isoformat()
    if isinstance(v, _dt.date):
        return v.isoformat()
    if isinstance(v, _dt.time):
        return v.isoformat()
    return str(v)


def _csv_error(msg: str) -> dict:
    return {"kind": "csv_error", "error": msg, "summary": f"export_csv error: {msg}"}


def tool_export_csv(args: dict, *, workspace: Path) -> dict:
    sql = args.get("sql")
    if not isinstance(sql, str) or not sql.strip():
        return _csv_error("`sql` is required")

    ok, why = _is_safe(sql)
    if not ok:
        return _csv_error(why)

    row_limit = args.get("row_limit", _CSV_DEFAULT_LIMIT)
    if not isinstance(row_limit, int) or isinstance(row_limit, bool) or row_limit <= 0:
        row_limit = _CSV_DEFAULT_LIMIT
    if row_limit > _CSV_MAX_LIMIT:
        row_limit = _CSV_MAX_LIMIT

    outputs_dir = workspace / "outputs"
    try:
        outputs_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        return _csv_error(f"cannot create outputs directory: {e}")

    safe_name = _safe_csv_filename(args.get("filename"), outputs_dir)
    out_path = outputs_dir / safe_name

    try:
        conn = psycopg2.connect(
            host=os.environ["DB_HOST"],
            port=os.environ.get("DB_PORT", "5432"),
            dbname=os.environ["DB_NAME"],
            user=os.environ["DB_USER"],
            password=os.environ["DB_PASSWORD"],
            options=f"-c statement_timeout={_STMT_TIMEOUT_MS}",
        )
    except psycopg2.Error as e:
        return _csv_error(f"connection error: {e}")
    try:
        conn.set_session(readonly=True, autocommit=False)
        with conn.cursor() as cur:
            cur.execute(sql)
            if cur.description is None:
                conn.rollback()
                return _csv_error("query returned no result set")
            cols = [d[0] for d in cur.description]
            rows = cur.fetchmany(row_limit + 1)
        conn.rollback()
    except psycopg2.Error as e:
        try:
            conn.rollback()
        except Exception:
            pass
        return _csv_error(f"sql error: {e}")
    finally:
        conn.close()

    truncated = len(rows) > row_limit
    rows = rows[:row_limit]

    try:
        with out_path.open("w", newline="", encoding="utf-8") as f:
            writer = _csv.writer(f)
            writer.writerow(cols)
            for row in rows:
                writer.writerow([_coerce_for_csv(v) for v in row])
    except OSError as e:
        return _csv_error(f"file write error: {e}")

    nb_id = _notebook_id_from_workspace(workspace)
    url = prefixed(f"/outputs/{nb_id}/{safe_name}")
    summary = f"CSV export: {safe_name} · {len(rows)} rows · {len(cols)} columns"
    if truncated:
        summary += f" (truncated to {row_limit})"

    return {
        "kind": "csv",
        "summary": summary,
        "filename": safe_name,
        "url": url,
        "row_count": len(rows),
        "truncated": truncated,
        "columns": cols,
    }


TOOL_SPECS = [
    {
        "type": "function",
        "function": {
            "name": "sql",
            "description": (
                "Run a read-only SQL SELECT or WITH (CTE) query against the meta_ads PostgreSQL database. "
                "Returns up to 100 rows as a markdown table. Multiple statements rejected. "
                "DDL/DML rejected at tool and DB role level. Statement timeout 30s."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "A single SELECT or WITH statement.",
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_wiki",
            "description": (
                "Read a page from the analyst wiki. Two analysis surfaces are documented: "
                "(1) CREATIVE PIPELINE — call BEFORE writing SQL against creative_pipeline.* views, "
                "or when the user asks about creative content, personas, pipelines, scripts, or "
                "creative-level performance. Pages: readme (overview), onboarding (mental model + "
                "conventions), reference (view catalog, example queries, foot-guns), lineage "
                "(column provenance), ops (debug/recover). "
                "(2) MAIN PAGE / DASHBOARD — call BEFORE writing SQL for account-level KPIs, "
                "time-series trends, demographic / placement break-downs, campaign or ad health, "
                "rules-engine activity, BAU pipeline, or upload-and-launch funnel questions. Page: "
                "main_overview (tables, metric definitions, query patterns, pitfalls)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "page": {
                        "type": "string",
                        "enum": list(_WIKI_PAGES),
                        "description": "Wiki page name (without .md extension).",
                    },
                },
                "required": ["page"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "chart",
            "description": (
                "Run a read-only SELECT/WITH query and render the result as an interactive "
                "Vega-Lite v5 chart in the notebook UI. Use when the user asks to plot, chart, "
                "graph, or visualize, or when a chart conveys the answer better than a table "
                "(time series ≥ 5 points, top-N rankings, group comparisons, distributions). "
                "Aggregate in SQL first — the row cap is 5000 (max 10000). Use field-type "
                "`temporal` for date/timestamp, `quantitative` for numeric measures, `nominal` "
                "for unordered categories, `ordinal` when order matters. Use `color` to group "
                "(multi-line, stacked bar). Same safety rules as `sql`: read-only, single "
                "statement, 30s timeout."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {
                        "type": "string",
                        "description": "A single SELECT or WITH statement returning the chart's data.",
                    },
                    "mark": {
                        "type": "string",
                        "enum": list(_CHART_MARKS),
                        "description": (
                            "Chart type. `line` for time series, `bar` for categorical / top-N, "
                            "`point` for scatter, `area` for stacked time series, `tick` for "
                            "1-D distributions."
                        ),
                    },
                    "x": {
                        "type": "object",
                        "description": "X-axis encoding: {field, type, title?}.",
                        "properties": {
                            "field": {"type": "string"},
                            "type": {"type": "string", "enum": list(_CHART_FIELD_TYPES)},
                            "title": {"type": "string"},
                        },
                        "required": ["field", "type"],
                    },
                    "y": {
                        "type": "object",
                        "description": "Y-axis encoding: {field, type, title?}.",
                        "properties": {
                            "field": {"type": "string"},
                            "type": {"type": "string", "enum": list(_CHART_FIELD_TYPES)},
                            "title": {"type": "string"},
                        },
                        "required": ["field", "type"],
                    },
                    "color": {
                        "type": "object",
                        "description": (
                            "Optional grouping encoding for multi-series charts: "
                            "{field, type, title?}."
                        ),
                        "properties": {
                            "field": {"type": "string"},
                            "type": {"type": "string", "enum": list(_CHART_FIELD_TYPES)},
                            "title": {"type": "string"},
                        },
                        "required": ["field", "type"],
                    },
                    "size": {
                        "type": "object",
                        "description": (
                            "Optional size encoding (mainly for `point`): {field, type, title?}."
                        ),
                        "properties": {
                            "field": {"type": "string"},
                            "type": {"type": "string", "enum": list(_CHART_FIELD_TYPES)},
                            "title": {"type": "string"},
                        },
                        "required": ["field", "type"],
                    },
                    "stack": {
                        "type": "boolean",
                        "description": (
                            "Only meaningful when `mark` is `bar` or `area` AND `color` is set. "
                            "Default false."
                        ),
                    },
                    "orient": {
                        "type": "string",
                        "enum": list(_CHART_ORIENTS),
                        "description": (
                            "`vertical` (default) or `horizontal`. For horizontal bars, x and y "
                            "encodings are swapped when building the spec."
                        ),
                    },
                    "title": {
                        "type": "string",
                        "description": "Chart title shown above the plot.",
                    },
                    "row_limit": {
                        "type": "integer",
                        "description": (
                            f"Max rows to include in the spec. Default "
                            f"{_CHART_DEFAULT_ROWS}, capped at {_CHART_MAX_ROWS}."
                        ),
                    },
                },
                "required": ["sql", "mark", "x", "y"],
            },
        },
    },
]

# --- python_exec tool (bwrap-sandboxed) -----------------------------------

def _pyexec_error(error: str) -> dict:
    return {
        "kind": "python_exec_error",
        "error": error,
        "summary": f"python_exec error: {error}",
    }


def _notebook_id_from_workspace(workspace: Path) -> int:
    """Workspace dirs are <root>/web/<user_id>/<notebook_id>. Last segment is the nb id."""
    try:
        return int(workspace.name)
    except ValueError:
        return 0


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + "\n[...truncated]"


def _run_in_sandbox(
    *,
    code: str,
    workspace: Path,
    load: list[str],
    timeout: int = _PYEXEC_DEFAULT_TIMEOUT,
) -> tuple[int, str, str]:
    """Invoke bwrap → sandbox_venv python → sandbox_runner.py with user code on stdin.

    Returns (exit_code, stdout, stderr). Raises subprocess.TimeoutExpired on
    wall-clock overrun. The sandbox has NO network, NO DB creds, NO filesystem
    access outside the notebook's workspace + the sandbox venv + the runner.
    """
    results_dir = workspace / "results"
    plots_dir = workspace / "plots"
    outputs_dir = workspace / "outputs"
    # Belt-and-suspenders mkdir: bwrap requires the host paths to exist.
    results_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    argv: list[str] = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/lib", "/lib",
    ]
    if Path("/lib64").exists():
        argv += ["--ro-bind", "/lib64", "/lib64"]
    # /bin and /sbin are symlinks → usr/bin / usr/sbin on this host; recreate
    # them inside the sandbox so shebangs that hard-code /bin/sh resolve.
    argv += [
        "--symlink", "usr/bin", "/bin",
        "--symlink", "usr/sbin", "/sbin",
        "--ro-bind", "/etc/alternatives", "/etc/alternatives",
        "--ro-bind", str(_SANDBOX_VENV_PYTHON.parent.parent),
                     str(_SANDBOX_VENV_PYTHON.parent.parent),
        "--ro-bind", str(_SANDBOX_RUNNER), str(_SANDBOX_RUNNER),
        "--ro-bind", str(results_dir), str(results_dir),
        "--bind",    str(plots_dir),   str(plots_dir),
        "--bind",    str(outputs_dir), str(outputs_dir),
        "--proc", "/proc",
        "--dev", "/dev",
        "--tmpfs", "/tmp",
        "--tmpfs", "/run",
        "--unshare-net",
        "--unshare-pid",
        "--unshare-uts",
        "--unshare-ipc",
        "--die-with-parent",
        "--new-session",
        "--chdir", str(workspace),
        "--clearenv",
        "--setenv", "PYTHONDONTWRITEBYTECODE", "1",
        "--setenv", "MPLBACKEND", "Agg",
        "--setenv", "HOME", "/tmp",
        "--setenv", "PATH", "/usr/bin:/bin",
        "--setenv", "LANG", "C.UTF-8",
        # Cap BLAS/OMP thread count: OpenBLAS reserves ~64 MiB of VAS per
        # thread, which can blow through RLIMIT_AS at import time even
        # before any user code runs. Single-threaded BLAS is fine for the
        # row scales (<= 50k) the persisted parquets are capped at.
        "--setenv", "OPENBLAS_NUM_THREADS", "1",
        "--setenv", "OMP_NUM_THREADS", "1",
        "--setenv", "MKL_NUM_THREADS", "1",
        "--",
        str(_SANDBOX_VENV_PYTHON),
        "-I",
        str(_SANDBOX_RUNNER),
        "--workspace", str(workspace),
        "--load", json.dumps(load),
    ]

    proc = subprocess.run(
        argv,
        input=code.encode("utf-8"),
        capture_output=True,
        timeout=timeout,
        check=False,
    )
    stdout = proc.stdout.decode("utf-8", errors="replace") if proc.stdout else ""
    stderr = proc.stderr.decode("utf-8", errors="replace") if proc.stderr else ""
    return proc.returncode, stdout, stderr


def _parse_sandbox_stdout(raw: str) -> tuple[str, list[dict], list[dict]]:
    """Split runner stdout into (clean_text, vega_specs, tables) by markers."""
    clean_lines: list[str] = []
    vega_specs: list[dict] = []
    tables: list[dict] = []
    for line in raw.splitlines():
        if line.startswith("__FB_CHART__\t"):
            try:
                vega_specs.append(json.loads(line[len("__FB_CHART__\t"):]))
            except json.JSONDecodeError:
                clean_lines.append(line)
        elif line.startswith("__FB_TABLE__\t"):
            try:
                tables.append(json.loads(line[len("__FB_TABLE__\t"):]))
            except json.JSONDecodeError:
                clean_lines.append(line)
        else:
            clean_lines.append(line)
    clean = "\n".join(clean_lines).rstrip()
    return clean, vega_specs, tables


def tool_python_exec(
    code: Any,
    load: Any = None,
    *,
    workspace: Path,
) -> dict:
    if not python_exec_enabled():
        return _pyexec_error(
            "python_exec is disabled in this environment. "
            "Set PYTHON_EXEC_ENABLED=true after installing the sandbox venv and bubblewrap."
        )
    if not isinstance(code, str) or not code.strip():
        return _pyexec_error("`code` is required and must be a non-empty string")
    if len(code) > _PYEXEC_MAX_CODE_CHARS:
        return _pyexec_error(
            f"`code` exceeds {_PYEXEC_MAX_CODE_CHARS} chars (got {len(code)})"
        )

    if load is None:
        load_list: list[str] = []
    elif isinstance(load, list):
        load_list = []
        for item in load:
            if not isinstance(item, str):
                return _pyexec_error(f"`load` entries must be strings (got {item!r})")
            if not _RESULT_ID_RE.match(item):
                return _pyexec_error(
                    f"result_id {item!r} not found (must match ^q\\d+$)"
                )
            load_list.append(item)
    else:
        return _pyexec_error("`load` must be a list of strings if provided")

    results_dir = workspace / "results"
    plots_dir = workspace / "plots"
    outputs_dir = workspace / "outputs"
    results_dir.mkdir(parents=True, exist_ok=True)
    plots_dir.mkdir(parents=True, exist_ok=True)
    outputs_dir.mkdir(parents=True, exist_ok=True)

    for rid in load_list:
        if not (results_dir / f"{rid}.parquet").is_file():
            return _pyexec_error(f"result_id '{rid}' not found")

    pre_plot_files = {p.name for p in plots_dir.iterdir() if p.is_file()}

    try:
        exit_code, stdout_raw, stderr_raw = _run_in_sandbox(
            code=code,
            workspace=workspace,
            load=load_list,
            timeout=_PYEXEC_DEFAULT_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return {
            "kind": "python_exec",
            "exit_status": "timeout",
            "stdout": "",
            "stderr": f"Sandbox killed after {_PYEXEC_DEFAULT_TIMEOUT}s wall-clock limit.",
            "plots": [],
            "vega_specs": [],
            "tables": [],
            "summary": f"python_exec timed out after {_PYEXEC_DEFAULT_TIMEOUT}s.",
        }
    except FileNotFoundError as e:
        return _pyexec_error(f"sandbox runtime not found: {e}")
    except Exception as e:  # noqa: BLE001
        return _pyexec_error(f"sandbox launch failed: {type(e).__name__}: {e}")

    stdout_clean, vega_specs, tables = _parse_sandbox_stdout(stdout_raw)
    stdout_clean = _truncate(stdout_clean, _PYEXEC_STDOUT_LIMIT)
    stderr_clean = _truncate(stderr_raw, _PYEXEC_STDOUT_LIMIT)

    new_plots: list[dict] = []
    nb_id = _notebook_id_from_workspace(workspace)
    for p in sorted(plots_dir.iterdir()):
        if not p.is_file():
            continue
        if p.name in pre_plot_files:
            continue
        if p.suffix.lower() not in _PYEXEC_PLOT_EXTS:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        if size > _PYEXEC_PLOT_MAX_BYTES:
            continue
        new_plots.append({
            "url": prefixed(f"/plots/{nb_id}/{p.name}"),
            "filename": p.name,
            "size": size,
        })

    if exit_code == 0:
        exit_status = "ok"
    else:
        exit_status = "error"

    head = stdout_clean[:80]
    summary = (
        f"python_exec: {exit_status}. "
        f"{len(new_plots)} plot(s), {len(vega_specs)} chart(s), "
        f"{len(tables)} table(s). "
        f"Stdout: {head}{'…' if len(stdout_clean) > 80 else ''}"
    )

    return {
        "kind": "python_exec",
        "exit_status": exit_status,
        "stdout": stdout_clean,
        "stderr": stderr_clean,
        "plots": new_plots,
        "vega_specs": vega_specs,
        "tables": tables,
        "summary": summary,
    }


TOOL_SPECS.append({
    "type": "function",
    "function": {
        "name": "python_exec",
        "description": (
            "Run arbitrary Python over the results of prior `sql` calls in a "
            "sandboxed subprocess (bwrap: no network, no DB credentials, scoped "
            "filesystem, 60s wall-clock, 512MB RAM). Use for correlations, "
            "regressions, hypothesis tests, custom transforms, and analytical "
            "plots that the `chart` tool cannot express. Each `sql` call returns "
            "a `result_id` like `q1`, `q2` — pass them in `load` and they appear "
            "as same-named pandas DataFrames inside the code. Pre-imported: "
            "`pd`, `np`, `plt` (matplotlib.pyplot, Agg backend), `stats` "
            "(scipy.stats), `sm` (statsmodels.api). Helper `fb.emit_chart(spec)` "
            "renders a Vega-Lite spec inline; `fb.emit_table(df, title=...)` "
            "renders a DataFrame as an HTML table. `plt.savefig('plots/x.png')` "
            "surfaces a PNG/SVG/JPG inline. Write intermediate files to "
            "`outputs/<name>.parquet` and read them back in the next call. "
            "Each call is a fresh subprocess — no shared state."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python source to execute. Up to 16000 chars. The "
                        "current working directory is the notebook's workspace; "
                        "`plots/` and `outputs/` are writable, `results/` is "
                        "read-only."
                    ),
                },
                "load": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "List of result_ids from prior `sql` calls "
                        "(e.g. [\"q1\", \"q3\"]). Each becomes a pandas "
                        "DataFrame variable of the same name."
                    ),
                },
            },
            "required": ["code"],
        },
    },
})


TOOL_SPECS.append({
    "type": "function",
    "function": {
        "name": "export_csv",
        "description": (
            "Run a read-only SELECT/WITH query and write the result to a downloadable "
            "CSV file in the notebook's output folder. Returns a download URL rendered "
            "as a button in the UI. Use when the user asks to download, export, or save "
            "data as a CSV. Aggregate in SQL first — row cap is 50 000 (default). "
            "Same safety rules as `sql`: read-only, single statement, 30s timeout. "
            "Do NOT use `python_exec` just to write CSV from SQL — `export_csv` does "
            "it directly."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "sql": {
                    "type": "string",
                    "description": "A single SELECT or WITH statement.",
                },
                "filename": {
                    "type": "string",
                    "description": (
                        "Optional filename (e.g. `top_creatives_last_7d.csv`). "
                        "Directory components are stripped; unsafe characters are "
                        "replaced with underscores. Defaults to a timestamped name."
                    ),
                },
                "row_limit": {
                    "type": "integer",
                    "description": (
                        f"Max rows to export. Default {_CSV_DEFAULT_LIMIT}, "
                        f"capped at {_CSV_MAX_LIMIT}. Truncation is reported."
                    ),
                },
            },
            "required": ["sql"],
        },
    },
})

_DISPATCH = {
    "sql": lambda args, *, workspace=None, **_: tool_sql(
        args["query"], workspace=workspace
    ),
    "read_wiki": lambda args, **_: tool_read_wiki(args["page"]),
    "chart": lambda args, **_: tool_chart(args),
    "python_exec": lambda args, *, workspace, **_: tool_python_exec(
        args.get("code"), args.get("load"), workspace=workspace
    ),
    "export_csv": lambda args, *, workspace, **_: tool_export_csv(args, workspace=workspace),
}


def dispatch(name: str, args: dict, **ctx):
    """Dispatch a tool call. Returns `str` for sql/read_wiki, `dict` for chart/python_exec."""
    fn = _DISPATCH.get(name)
    if fn is None:
        return f"error: unknown tool '{name}'"
    try:
        return fn(args, **ctx)
    except Exception as e:
        return f"tool {name} crashed: {type(e).__name__}: {e}"
