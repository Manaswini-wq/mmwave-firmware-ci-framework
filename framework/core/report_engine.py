"""
Report Engine - HTML, JSON, and dashboard report generation.

Generates rich test reports with Jinja2 templating, trend analysis,
and safety-evidence artefacts (traceability matrices, coverage summaries).
"""
from __future__ import annotations

import argparse
import json
import logging
import statistics
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import jinja2

    _HAS_JINJA2 = True
except ImportError:
    _HAS_JINJA2 = False

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default embedded HTML template (used when no external template provided)
# ---------------------------------------------------------------------------

_DEFAULT_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{{ title }}</title>
  <style>
    body { font-family: Arial, sans-serif; margin: 2rem; background: #f9fafb; }
    h1 { color: #1e293b; }
    .summary { display: flex; gap: 1rem; margin-bottom: 2rem; }
    .card { padding: 1rem 1.5rem; border-radius: 8px; color: #fff; min-width: 100px; }
    .card.pass { background: #16a34a; }
    .card.fail { background: #dc2626; }
    .card.skip { background: #ca8a04; }
    .card.error { background: #9333ea; }
    table { border-collapse: collapse; width: 100%; }
    th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid #e2e8f0; }
    th { background: #1e293b; color: #fff; }
    tr.pass td:first-child { border-left: 4px solid #16a34a; }
    tr.fail td:first-child { border-left: 4px solid #dc2626; }
    tr.error td:first-child { border-left: 4px solid #9333ea; }
    tr.skip td:first-child { border-left: 4px solid #ca8a04; }
    .trend { margin-top: 2rem; }
    .bar { display: inline-block; height: 18px; }
    .bar.pass { background: #16a34a; }
    .bar.fail { background: #dc2626; }
  </style>
</head>
<body>
  <h1>{{ title }}</h1>
  <p>Generated: {{ timestamp }}</p>

  <div class="summary">
    <div class="card pass"><strong>{{ summary.passed }}</strong><br>Passed</div>
    <div class="card fail"><strong>{{ summary.failed }}</strong><br>Failed</div>
    <div class="card skip"><strong>{{ summary.skipped }}</strong><br>Skipped</div>
    <div class="card error"><strong>{{ summary.errors }}</strong><br>Errors</div>
  </div>

  <table>
    <thead><tr><th>Test</th><th>Status</th><th>Duration (s)</th><th>Message</th></tr></thead>
    <tbody>
    {% for r in results %}
      <tr class="{{ r.status }}">
        <td>{{ r.name }}</td>
        <td>{{ r.status | upper }}</td>
        <td>{{ "%.3f" | format(r.duration) }}</td>
        <td>{{ r.message }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>

  {% if trends %}
  <div class="trend">
    <h2>Pass-Rate Trend (last {{ trends | length }} runs)</h2>
    {% for t in trends %}
      <div>
        <span style="display:inline-block;width:90px;">{{ t.label }}</span>
        <span class="bar pass" style="width:{{ t.pass_pct * 3 }}px;"></span>
        <span class="bar fail" style="width:{{ (100 - t.pass_pct) * 3 }}px;"></span>
        {{ "%.1f" | format(t.pass_pct) }}%
      </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if traceability %}
  <h2>Requirements Traceability</h2>
  <table>
    <thead><tr><th>Requirement</th><th>Tests</th><th>Status</th></tr></thead>
    <tbody>
    {% for req_id, info in traceability.items() %}
      <tr>
        <td>{{ req_id }}</td>
        <td>{{ info.tests | join(", ") }}</td>
        <td>{{ info.status }}</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% endif %}
</body>
</html>
"""


# ---------------------------------------------------------------------------
# ReportEngine
# ---------------------------------------------------------------------------

class ReportEngine:
    """Generate HTML, JSON, and dashboard reports from test results."""

    def __init__(self, template_dir: str | Path | None = None) -> None:
        self._template_dir = Path(template_dir) if template_dir else None

    # ------------------------------------------------------------------
    # HTML report
    # ------------------------------------------------------------------

    def generate_html(
        self,
        results: list[dict[str, Any]],
        summary: dict[str, Any],
        output: str | Path,
        template: str | None = None,
        title: str = "mmWave Firmware Test Report",
        traceability: dict[str, Any] | None = None,
        trends: list[dict[str, Any]] | None = None,
    ) -> Path:
        """Render an HTML report using Jinja2 (or a built-in fallback)."""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)

        context: dict[str, Any] = {
            "title": title,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
            "summary": summary,
            "results": results,
            "traceability": traceability,
            "trends": trends,
        }

        html = self._render_template(template, context)
        output.write_text(html, encoding="utf-8")
        logger.info("HTML report written to %s", output)
        return output

    # ------------------------------------------------------------------
    # JSON report
    # ------------------------------------------------------------------

    def generate_json(
        self,
        results: list[dict[str, Any]],
        summary: dict[str, Any],
        output: str | Path,
    ) -> Path:
        """Write a machine-readable JSON report."""
        output = Path(output)
        output.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "results": results,
        }
        output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        logger.info("JSON report written to %s", output)
        return output

    # ------------------------------------------------------------------
    # Dashboard / trends
    # ------------------------------------------------------------------

    def generate_summary_dashboard(
        self,
        results_history: list[dict[str, Any]],
        output: str | Path,
    ) -> Path:
        """Generate an HTML dashboard showing trends across multiple runs.

        *results_history* is a list of previous run summaries (dicts with
        ``passed``, ``total``, ``timestamp`` keys).
        """
        trends = self._calculate_trends(results_history)
        latest = results_history[-1] if results_history else {}
        return self.generate_html(
            results=latest.get("results", []),
            summary=latest.get("summary", {}),
            output=output,
            title="CI Dashboard — Trend Overview",
            trends=trends,
        )

    # ------------------------------------------------------------------
    # Safety evidence helpers
    # ------------------------------------------------------------------

    @staticmethod
    def build_traceability_matrix(
        results: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        """Build a requirements-to-tests traceability matrix.

        Each result dict should contain a ``requirements_ids`` list.
        Returns ``{req_id: {tests: [...], status: "covered"|"gap"}}``.
        """
        matrix: dict[str, dict[str, Any]] = {}
        for r in results:
            for req_id in r.get("requirements_ids", []):
                entry = matrix.setdefault(req_id, {"tests": [], "status": "gap"})
                entry["tests"].append(r.get("name", "?"))
                if r.get("status") == "pass":
                    entry["status"] = "covered"
        return matrix

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _render_template(self, template_name: str | None, context: dict[str, Any]) -> str:
        """Render a Jinja2 template (file or embedded default)."""
        if _HAS_JINJA2:
            if template_name and self._template_dir:
                env = jinja2.Environment(
                    loader=jinja2.FileSystemLoader(str(self._template_dir)),
                    autoescape=jinja2.select_autoescape(["html"]),
                )
                tmpl = env.get_template(template_name)
            else:
                env = jinja2.Environment(autoescape=jinja2.select_autoescape(["html"]))
                tmpl = env.from_string(_DEFAULT_HTML_TEMPLATE)
            return tmpl.render(**context)

        # Minimal fallback when Jinja2 is not installed
        logger.warning("Jinja2 not installed — generating minimal HTML report")
        rows = "\n".join(
            f"<tr><td>{r.get('name')}</td><td>{r.get('status')}</td>"
            f"<td>{r.get('duration', 0):.3f}</td></tr>"
            for r in context.get("results", [])
        )
        return f"<html><body><h1>{context['title']}</h1><table>{rows}</table></body></html>"

    @staticmethod
    def _calculate_trends(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Compute pass-rate and duration trends from historical summaries."""
        trends: list[dict[str, Any]] = []
        for entry in history[-20:]:  # last 20 runs
            summary = entry.get("summary", entry)
            total = summary.get("total", 1) or 1
            passed = summary.get("passed", 0)
            pass_pct = (passed / total) * 100.0
            trends.append({
                "label": summary.get("timestamp", "?")[:10],
                "pass_pct": round(pass_pct, 1),
                "duration": summary.get("total_duration", 0.0),
            })
        return trends


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> None:
    """CLI entry-point for standalone report generation."""
    parser = argparse.ArgumentParser(description="Generate test reports from JSON results")
    parser.add_argument("--input", required=True, help="Path to results JSON file")
    parser.add_argument("--format", choices=["html", "json"], default="html")
    parser.add_argument("--output", required=True, help="Output file path")
    parser.add_argument("--template-dir", default=None, help="Directory with Jinja2 templates")
    parser.add_argument("--template", default=None, help="Template file name")
    parser.add_argument("--title", default="mmWave Firmware Test Report")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    engine = ReportEngine(template_dir=args.template_dir)

    if args.format == "html":
        engine.generate_html(
            results=data.get("results", []),
            summary=data.get("summary", {}),
            output=args.output,
            template=args.template,
            title=args.title,
        )
    else:
        engine.generate_json(
            results=data.get("results", []),
            summary=data.get("summary", {}),
            output=args.output,
        )


if __name__ == "__main__":
    main()
