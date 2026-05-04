"""
generate_report.py — Build an HTML accuracy dashboard from training data.

Reads:
  training/scores.json   — per-case scores
  training/patterns.json — top failing fields
  training/cases/<name>/diff.json  — per-field detail (latest run)
  training/runs/<ts>_<name>/diff.json — fallback if case-level diff missing

Writes:
  docs/report.html       — self-contained HTML dashboard (no external dependencies)
  docs/data.json         — raw JSON for programmatic access

Usage:
  python generate_report.py            # build report
  python generate_report.py --open     # build and open in browser
"""

import json
import os
import sys
import webbrowser
from datetime import datetime
from pathlib import Path

_HERE     = Path(__file__).parent.resolve()   # tools/
_ROOT     = _HERE.parent                       # AuditorReportReader/
_TRAINING = _ROOT / "training"
_CASES    = _TRAINING / "cases"
_RUNS     = _TRAINING / "runs"
_SCORES   = _TRAINING / "scores.json"
_PATTERNS = _TRAINING / "patterns.json"
_DOCS     = _ROOT / "docs"

_ERROR_COLORS = {
    "MATCH":        "#22c55e",
    "ROUNDING":     "#86efac",
    "MISSING":      "#ef4444",
    "WRONG_VALUE":  "#f97316",
    "SIGN_FLIP":    "#a855f7",
    "SCALE_x10":    "#eab308",
    "SCALE_x100":   "#eab308",
    "SCALE_x1000":  "#f59e0b",
    "TYPE_MISMATCH":"#6b7280",
}

# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _find_diff(case_name: str) -> dict:
    """Return the most recent diff for a case."""
    # Check case-level diff first
    case_diff = _CASES / case_name / "diff.json"
    if case_diff.exists():
        return _load_json(case_diff)
    # Fall back to latest run dir
    run_dirs = sorted(
        [d for d in _RUNS.iterdir() if d.is_dir() and d.name.endswith(f"_{case_name}")],
        reverse=True
    )
    for rd in run_dirs:
        diff_path = rd / "diff.json"
        if diff_path.exists():
            return _load_json(diff_path)
    return {}


def _pct_bar(pct: float, width: int = 200) -> str:
    """SVG progress bar."""
    filled = int(width * pct / 100)
    color  = "#22c55e" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#ef4444")
    return (
        f'<svg width="{width}" height="12" style="border-radius:6px;overflow:hidden">'
        f'<rect width="{width}" height="12" fill="#e5e7eb"/>'
        f'<rect width="{filled}" height="12" fill="{color}"/>'
        f'</svg>'
    )


# ── data assembly ─────────────────────────────────────────────────────────────

def build_data() -> dict:
    scores   = _load_json(_SCORES)
    patterns = _load_json(_PATTERNS)
    cases    = []

    for case_name in sorted(scores):
        sc   = scores[case_name]
        diff = _find_diff(case_name)
        meta_path = _CASES / case_name / "metadata.json"
        meta = _load_json(meta_path)

        fields = diff.get("fields", [])
        by_status: dict = {}
        for f in fields:
            by_status.setdefault(f["status"], []).append(f)

        cases.append({
            "name":          case_name,
            "industry":      meta.get("industry", "—"),
            "score_pct":     sc.get("score_pct", 0),
            "matched":       sc.get("matched", 0),
            "total":         sc.get("total", 0),
            "last_run":      sc.get("last_run", "—"),
            "by_category":   sc.get("by_category", {}),
            "fields":        fields,
            "by_status":     by_status,
            "years":         diff.get("years_compared", []),
            "pdf_filename":  (meta.get("pdf_filename")
                              or Path(meta.get("source_pdf", "")).name),
            "cawf_filename": (meta.get("cawf_filename")
                              or Path(meta.get("source_excel", "")).name),
        })

    total_m = sum(c["matched"] for c in cases)
    total_t = sum(c["total"]   for c in cases)
    overall = round(100 * total_m / total_t, 1) if total_t else 0.0

    return {
        "generated":     datetime.now().isoformat(),
        "overall_score": overall,
        "total_matched": total_m,
        "total_fields":  total_t,
        "cases":         cases,
        "patterns":      patterns,
    }


# ── HTML generator ────────────────────────────────────────────────────────────

def _field_rows(fields: list) -> str:
    rows = []
    for f in fields:
        status = f["status"]
        color  = _ERROR_COLORS.get(status, "#6b7280")
        fv = str(f.get("filled", "—")) if f.get("filled") is not None else "—"
        cv = str(f.get("correct", "—"))
        rows.append(
            f'<tr>'
            f'<td>{f["year"]}</td>'
            f'<td>{f["label"]}</td>'
            f'<td><span style="background:{color};color:#fff;padding:2px 6px;border-radius:4px;font-size:11px">{status}</span></td>'
            f'<td style="font-family:monospace">{fv}</td>'
            f'<td style="font-family:monospace">{cv}</td>'
            f'</tr>'
        )
    return "\n".join(rows)


def _category_pills(by_category: dict) -> str:
    pills = []
    for cat, cnt in sorted(by_category.items(), key=lambda x: -x[1]):
        if cat == "MATCH":
            continue
        color = _ERROR_COLORS.get(cat, "#6b7280")
        pills.append(
            f'<span style="background:{color};color:#fff;padding:2px 8px;'
            f'border-radius:12px;font-size:12px;margin:2px">{cat} {cnt}</span>'
        )
    return " ".join(pills) if pills else '<span style="color:#22c55e">✓ All matched</span>'


def _file_pills(pdf: str, cawf: str) -> str:
    """Render labelled file-name pills if filenames are known."""
    parts = []
    if pdf:
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'background:#eff6ff;color:#1d4ed8;border:1px solid #bfdbfe;'
            f'border-radius:6px;padding:3px 10px;font-size:11px">'
            f'&#128196;&nbsp;<strong>Auditor PDF:</strong>&nbsp;'
            f'<span style="font-family:monospace">{pdf}</span></span>'
        )
    if cawf:
        parts.append(
            f'<span style="display:inline-flex;align-items:center;gap:5px;'
            f'background:#f0fdf4;color:#15803d;border:1px solid #bbf7d0;'
            f'border-radius:6px;padding:3px 10px;font-size:11px">'
            f'&#9989;&nbsp;<strong>Correct data:</strong>&nbsp;'
            f'<span style="font-family:monospace">{cawf}</span></span>'
        )
    return " ".join(parts)


def _case_card(case: dict) -> str:
    pct  = case["score_pct"]
    bar  = _pct_bar(pct)
    ring_color = "#22c55e" if pct >= 80 else ("#f59e0b" if pct >= 50 else "#ef4444")
    pills = _category_pills(case["by_category"])
    field_table = _field_rows(case["fields"]) if case["fields"] else (
        "<tr><td colspan='5' style='color:#6b7280;text-align:center'>No diff data available</td></tr>"
    )
    years = ", ".join(case["years"]) or "—"
    file_pills = _file_pills(case.get("pdf_filename", ""), case.get("cawf_filename", ""))

    return f"""
    <div class="card" id="case-{case['name']}">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
        <div>
          <h2 style="margin:0;font-size:20px">{case['name']}</h2>
          <span style="color:#6b7280;font-size:13px">{case['industry']} &nbsp;·&nbsp; Years: {years} &nbsp;·&nbsp; Run: {case['last_run'][:15] if case['last_run'] != '—' else '—'}</span>
        </div>
        <div style="text-align:center">
          <div style="font-size:32px;font-weight:700;color:{ring_color}">{pct}%</div>
          <div style="font-size:12px;color:#6b7280">{case['matched']}/{case['total']} fields</div>
        </div>
      </div>
      {"<div style='margin-bottom:10px;display:flex;flex-wrap:wrap;gap:6px'>" + file_pills + "</div>" if file_pills else ""}
      <div style="margin-bottom:8px">{bar}</div>
      <div style="margin-bottom:12px">{pills}</div>
      <details>
        <summary style="cursor:pointer;color:#3b82f6;font-size:13px">Show field-by-field detail ▾</summary>
        <div style="overflow-x:auto;margin-top:8px">
          <table class="field-table">
            <thead><tr><th>Year</th><th>Field</th><th>Status</th><th>Extracted</th><th>Correct</th></tr></thead>
            <tbody>{field_table}</tbody>
          </table>
        </div>
      </details>
    </div>
    """


def build_html(data: dict) -> str:
    overall = data["overall_score"]
    overall_color = "#22c55e" if overall >= 80 else ("#f59e0b" if overall >= 50 else "#ef4444")
    generated = data["generated"][:19].replace("T", " ")

    # Top failing fields table
    fields_ranked = data["patterns"].get("fields_ranked", {})
    top_fields_rows = ""
    for label, info in list(fields_ranked.items())[:15]:
        dom   = info.get("dominant_error", "?")
        tot   = info.get("total_errors", 0)
        color = _ERROR_COLORS.get(dom, "#6b7280")
        bar_w = min(tot * 12, 120)
        top_fields_rows += (
            f'<tr><td>{label}</td>'
            f'<td><span style="background:{color};color:#fff;padding:2px 6px;border-radius:4px;font-size:11px">{dom}</span></td>'
            f'<td style="font-family:monospace">{tot}</td>'
            f'<td><div style="background:{color};height:8px;width:{bar_w}px;border-radius:4px"></div></td>'
            f'</tr>'
        )

    case_cards = "\n".join(_case_card(c) for c in data["cases"])
    total_cases = len(data["cases"])

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AuditorReportReader — Extraction Accuracy Dashboard</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0 }}
  body {{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif; background:#f8fafc; color:#1e293b; }}
  .header {{ background:linear-gradient(135deg,#1e40af,#3b82f6); color:#fff; padding:32px 24px; }}
  .header h1 {{ font-size:24px; font-weight:700 }}
  .header p  {{ opacity:.8; font-size:14px; margin-top:4px }}
  .container {{ max-width:1100px; margin:0 auto; padding:24px }}
  .summary-grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; margin-bottom:24px }}
  .stat-box {{ background:#fff; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,.1); text-align:center }}
  .stat-box .num {{ font-size:36px; font-weight:700 }}
  .stat-box .lbl {{ font-size:13px; color:#6b7280; margin-top:4px }}
  .card {{ background:#fff; border-radius:12px; padding:20px; box-shadow:0 1px 3px rgba(0,0,0,.1); margin-bottom:16px }}
  .section-title {{ font-size:18px; font-weight:600; margin:24px 0 12px }}
  .field-table {{ width:100%; border-collapse:collapse; font-size:13px }}
  .field-table th {{ background:#f1f5f9; padding:8px 10px; text-align:left; font-weight:600 }}
  .field-table td {{ padding:7px 10px; border-bottom:1px solid #f1f5f9 }}
  .field-table tr:hover td {{ background:#f8fafc }}
  details summary {{ outline:none }}
  .legend {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:16px }}
  .legend span {{ padding:3px 10px; border-radius:12px; font-size:12px; color:#fff }}
</style>
</head>
<body>

<div class="header">
  <h1>AuditorReportReader — Extraction Accuracy</h1>
  <p>Training data dashboard &nbsp;·&nbsp; Generated {generated}</p>
</div>

<div class="container">

  <!-- Summary stats -->
  <div class="summary-grid" style="margin-top:24px">
    <div class="stat-box">
      <div class="num" style="color:{overall_color}">{overall}%</div>
      <div class="lbl">Overall Accuracy</div>
    </div>
    <div class="stat-box">
      <div class="num" style="color:#3b82f6">{data['total_matched']}/{data['total_fields']}</div>
      <div class="lbl">Fields Matched</div>
    </div>
    <div class="stat-box">
      <div class="num">{total_cases}</div>
      <div class="lbl">Training Cases</div>
    </div>
    <div class="stat-box">
      <div class="num" style="color:#ef4444">{data['total_fields'] - data['total_matched']}</div>
      <div class="lbl">Fields to Fix</div>
    </div>
  </div>

  <!-- Legend -->
  <div class="legend">
    <span style="background:#22c55e">MATCH</span>
    <span style="background:#ef4444">MISSING</span>
    <span style="background:#f97316">WRONG_VALUE</span>
    <span style="background:#f59e0b">SCALE_x1000</span>
    <span style="background:#a855f7">SIGN_FLIP</span>
    <span style="background:#eab308">SCALE_x10/100</span>
    <span style="background:#6b7280">TYPE_MISMATCH</span>
  </div>

  <!-- Top failing fields -->
  {"" if not top_fields_rows else f'''
  <div class="section-title">Top Fields Needing Improvement</div>
  <div class="card">
    <table class="field-table">
      <thead><tr><th>Field</th><th>Dominant Error</th><th>Error Count</th><th>Volume</th></tr></thead>
      <tbody>{top_fields_rows}</tbody>
    </table>
  </div>
  '''}

  <!-- Per-case cards -->
  <div class="section-title">Case-by-Case Results</div>
  {case_cards}

</div>
</body>
</html>
"""


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    _DOCS.mkdir(exist_ok=True)

    data = build_data()

    # Write data.json
    data_path = _DOCS / "data.json"
    data_path.write_text(json.dumps(data, indent=2, default=str))

    # Write report.html
    html_path = _DOCS / "report.html"
    html_path.write_text(build_html(data))

    print(f"Report written → {html_path}")
    print(f"Data  written → {data_path}")
    print(f"Overall accuracy: {data['overall_score']}%  ({data['total_matched']}/{data['total_fields']} fields)")

    if "--open" in sys.argv:
        webbrowser.open(f"file://{html_path.resolve()}")


if __name__ == "__main__":
    main()
