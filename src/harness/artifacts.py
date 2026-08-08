"""Write machine-readable test reports under artifacts/test/."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def ensure_dir(path: Path | str) -> Path:
    target = Path(path)
    target.mkdir(parents=True, exist_ok=True)
    return target


def write_report(
    out_dir: Path | str,
    *,
    layer: str,
    result: str,
    checks: list[dict[str, Any]],
    extra: dict[str, Any] | None = None,
) -> tuple[Path, Path]:
    """Write report.json + report.md. result must be PASS|FAIL|BLOCKED."""
    directory = ensure_dir(out_dir)
    payload: dict[str, Any] = {
        "layer": layer,
        "result": result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }
    if extra:
        payload.update(extra)

    json_path = directory / "report.json"
    md_path = directory / "report.md"
    json_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_path.write_text(_to_markdown(payload), encoding="utf-8")
    return json_path, md_path


def _to_markdown(payload: dict[str, Any]) -> str:
    lines = [
        f"# {payload.get('layer', 'test')} report",
        "",
        f"**Result:** {payload.get('result')}",
        f"**Generated:** {payload.get('generated_at')}",
        "",
        "| ID | Result | Detail |",
        "| --- | --- | --- |",
    ]
    for check in payload.get("checks", []):
        cid = check.get("id", "?")
        cres = check.get("result", "?")
        detail = str(check.get("detail", "")).replace("|", "\\|")
        lines.append(f"| `{cid}` | {cres} | {detail} |")
    lines.append("")
    return "\n".join(lines)
