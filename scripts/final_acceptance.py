from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def run_step(name: str, command: list[str], *, env: dict[str, str] | None = None) -> dict[str, object]:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    started_at = datetime.now().isoformat(timespec="seconds")
    process = subprocess.run(
        command,
        cwd=PROJECT_ROOT,
        env=merged_env,
        capture_output=True,
        text=True,
    )
    return {
        "name": name,
        "command": command,
        "started_at": started_at,
        "returncode": process.returncode,
        "stdout": process.stdout[-8000:],
        "stderr": process.stderr[-8000:],
        "status": "PASS" if process.returncode == 0 else "FAIL",
    }


def build_report(results: list[dict[str, object]]) -> str:
    lines = [
        "# Knowledge Base Core v1 Final Acceptance Report",
        "",
        f"Generated at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "| Step | Status | Command |",
        "|---|---|---|",
    ]
    for result in results:
        command = " ".join(result["command"])
        lines.append(f"| {result['name']} | {result['status']} | `{command}` |")
    lines.append("")
    for result in results:
        lines.append(f"## {result['name']}")
        lines.append("")
        lines.append(f"- status: `{result['status']}`")
        lines.append(f"- started_at: `{result['started_at']}`")
        lines.append("")
        lines.append("```text")
        output = result["stdout"] if result["status"] == "PASS" else (result["stderr"] or result["stdout"])
        lines.append(output.strip() or "(no output)")
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def main() -> int:
    default_output_base = PROJECT_ROOT / "qa-outputs"
    configured_output_base = os.environ.get("OA_RAG_ACCEPTANCE_OUTPUT_DIR", "").strip()
    output_base = Path(configured_output_base) if configured_output_base else default_output_base
    output_root = output_base / "oa-rag" / datetime.now().strftime("%Y%m%d-%H%M%S")
    reports_dir = output_root / "reports"
    artifacts_dir = output_root / "artifacts"
    reports_dir.mkdir(parents=True, exist_ok=True)
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict[str, object]] = []
    python_bin = str(PROJECT_ROOT / ".venv" / "bin" / "python")
    pytest_bin = str(PROJECT_ROOT / ".venv" / "bin" / "pytest")

    results.append(
        run_step(
            "pytest",
            [pytest_bin, "-q"],
        )
    )
    results.append(
        run_step(
            "dify_mvp_smoke",
            [python_bin, "scripts/dify_mvp_smoke.py"],
            env={"DIFY_APP_KEY": os.environ.get("DIFY_APP_KEY", "test-dify-key")},
        )
    )

    if os.environ.get("OA_RAG_RUN_REAL_PROVIDER_SMOKE", "").lower() in {"1", "true", "yes"}:
        results.append(
            run_step(
                "real_provider_smoke",
                [python_bin, "scripts/real_provider_smoke.py"],
            )
        )

    report_path = reports_dir / "final-acceptance-report.md"
    artifact_path = artifacts_dir / "final-acceptance-result.json"
    report_path.write_text(build_report(results), encoding="utf-8")
    artifact_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = {
        "report_path": str(report_path),
        "artifact_path": str(artifact_path),
        "failed_steps": [item["name"] for item in results if item["status"] == "FAIL"],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if not summary["failed_steps"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
