from pathlib import Path
import ast


PROBE = Path(__file__).resolve().parents[1] / "tools/carrot_wip_s4b_shadow_probe.py"


def test_s4b_probe_has_no_publish_or_manager_registration_code():
  source = PROBE.read_text(encoding="utf-8")
  assert "PubMaster" not in source
  assert ".send('modelV2'" not in source
  assert '.send("modelV2"' not in source
  assert "process_config" not in source
  assert "managerState" not in source
  assert "controlEligible\", False" in source
  assert "qualityComparisonEligible\", False" in source


def test_s4b_probe_imports_openpilot_only_after_argument_guards():
  tree = ast.parse(PROBE.read_text(encoding="utf-8"))
  main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")
  text = ast.unparse(main)
  assert text.index("S4B --max-hz must be >0 and <=5") < text.index("import numpy as np")
  assert 'os.environ.setdefault("PROFILE", "1")' in text
