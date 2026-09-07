from pathlib import Path
import ast


PROBE = Path(__file__).resolve().parents[1] / "tools/carrot_wip_s4b_shadow_probe.py"


def _tree():
  return ast.parse(PROBE.read_text(encoding="utf-8"))


def _imported_modules(tree: ast.AST) -> set[str]:
  modules: set[str] = set()
  for node in ast.walk(tree):
    if isinstance(node, ast.Import):
      modules.update(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
      modules.add(node.module)
  return modules


def test_s4b_probe_has_no_publish_or_manager_registration_code():
  tree = _tree()
  modules = _imported_modules(tree)
  assert not any(module.endswith("process_config") or ".process_config" in module for module in modules)

  for node in ast.walk(tree):
    if isinstance(node, ast.Name):
      assert node.id != "PubMaster"
    if isinstance(node, ast.Attribute):
      assert node.attr != "PubMaster"
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
      # Ignore documentation strings; reject executable/message constants that
      # would expose forbidden control publications or manager subscriptions.
      parent_is_doc_expr = False
      for candidate in ast.walk(tree):
        if isinstance(candidate, ast.Expr) and candidate.value is node:
          parent_is_doc_expr = True
          break
      if not parent_is_doc_expr:
        assert node.value != "modelV2"
        assert node.value != "managerState"

  # These are emitted as immutable safety metadata on every probe event.
  source = PROBE.read_text(encoding="utf-8")
  assert 'event.setdefault("controlEligible", False)' in source
  assert 'event.setdefault("qualityComparisonEligible", False)' in source


def test_s4b_probe_imports_openpilot_only_after_argument_guards():
  tree = _tree()
  main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "main")

  guard_index = None
  numpy_import_index = None
  profile_set_index = None
  for index, stmt in enumerate(main.body):
    if isinstance(stmt, ast.If):
      for node in ast.walk(stmt):
        if isinstance(node, ast.Constant) and node.value == "S4B --max-hz must be >0 and <=5":
          guard_index = index
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "setdefault":
          if len(node.args) >= 2 and all(isinstance(arg, ast.Constant) for arg in node.args[:2]):
            if node.args[0].value == "PROFILE" and node.args[1].value == "1":
              profile_set_index = index
    if isinstance(stmt, ast.Import) and any(alias.name == "numpy" for alias in stmt.names):
      numpy_import_index = index

  assert guard_index is not None
  assert profile_set_index is not None
  assert numpy_import_index is not None
  assert guard_index < profile_set_index < numpy_import_index
