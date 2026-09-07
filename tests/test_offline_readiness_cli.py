import json
from pathlib import Path
import subprocess
import sys


def test_synthetic_cli_writes_expected_pass_report(tmp_path: Path):
  out = tmp_path / "pass"
  result = subprocess.run(
    [sys.executable, "tools/simulate_commissioning_pipeline.py", "pass", "--output-dir", str(out)],
    text=True,
    capture_output=True,
    check=False,
  )
  assert result.returncode == 0, result.stderr
  summary = json.loads(result.stdout)
  assert summary["matchesExpected"] is True
  report = json.loads((out / "commissioning_qualification.json").read_text(encoding="utf-8"))
  assert report["overallStatus"] == "PASS"
  assert report["synthetic"] is True


def test_synthetic_cli_expected_failure_case_is_successful_regression(tmp_path: Path):
  out = tmp_path / "fail"
  result = subprocess.run(
    [sys.executable, "tools/simulate_commissioning_pipeline.py", "fail_transport", "--output-dir", str(out)],
    text=True,
    capture_output=True,
    check=False,
  )
  # The simulator exits zero when the *expected* FAIL was correctly produced.
  assert result.returncode == 0, result.stderr
  summary = json.loads(result.stdout)
  assert summary["actualStatus"] == "FAIL"
  assert summary["matchesExpected"] is True
