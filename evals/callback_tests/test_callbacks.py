"""Pytest discovery entry point for callback and tool evaluation unit tests."""

import importlib.util
from pathlib import Path
import sys

from cxas_scrapi.evals.callback_evals import CallbackEvals
from cxas_scrapi.evals.tool_evals import ToolEvals

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_TEST_DIR = (
    Path(__file__).resolve().parent
    / "tests"
    / "totto_root_agent"
    / "before_agent_callbacks"
    / "before_agent"
)
if str(_TEST_DIR) not in sys.path:
  sys.path.insert(0, str(_TEST_DIR))

from test import TestBeforeAgentCallback  # noqa: F401, E402


def test_callback_evals_runner() -> None:
  """Verifies CallbackEvals.test_all_callbacks_in_app_dir passes 100%."""
  cb = CallbackEvals()
  df = cb.test_all_callbacks_in_app_dir(str(_PROJECT_ROOT / "evals" / "callback_tests"))
  assert len(df) == 4
  assert (df["status"] == "PASSED").all()


def test_tool_evals_suite() -> None:
  """Verifies all 16 tool test cases in evals/tool_tests/tool_tests.yaml pass ToolEvals."""
  te = ToolEvals.__new__(ToolEvals)
  test_cases = te.load_tool_tests_from_dir(str(_PROJECT_ROOT / "evals" / "tool_tests"))
  assert len(test_cases) >= 16
  for tc in test_cases:
    code_path = (
        _PROJECT_ROOT
        / "cxas_app"
        / "totto_mercedes_f1_agent"
        / "tools"
        / tc.tool
        / "python_function"
        / "python_code.py"
    )
    spec = importlib.util.spec_from_file_location(tc.tool, code_path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, tc.tool)
    response = fn(**(tc.args or {}))
    assert not te.validate_tool_test(tc, response)
    assert not te.validate_tool_test(tc, {"response": response})
