"""Run spawn-based tests outside Streamlit's process-global script state."""

from functools import wraps
import os
from pathlib import Path
import subprocess
import sys


_CHILD_TEST = "REVIEW_INTEL_ISOLATED_TEST"


def isolated_process_test(method):
    """Keep ordinary unittest discovery safe, even after AppTest reruns.

    Each child runs just this test through unittest's import-safe entry point.
    Unlike changing multiprocessing's start method or replacing __main__, this
    leaves the parent AppTest state and the real spawn/locking coverage intact.
    """
    @wraps(method)
    def run(self):
        module = type(self).__module__
        if module == "__main__":
            module = Path(method.__code__.co_filename).stem
        test_id = f"{module}.{type(self).__qualname__}.{method.__name__}"
        if os.environ.get(_CHILD_TEST) == test_id:
            return method(self)
        environment = dict(os.environ, **{_CHILD_TEST: test_id})
        try:
            result = subprocess.run(
                [sys.executable, "-m", "unittest", "-v", test_id],
                cwd=Path(__file__).resolve().parent,
                env=environment,
                capture_output=True,
                text=True,
                timeout=180,
            )
        except subprocess.TimeoutExpired as exc:
            self.fail(f"Isolated test timed out: {test_id}\n{exc.stdout}\n{exc.stderr}")
        self.assertEqual(
            result.returncode, 0,
            f"Isolated test failed: {test_id}\n{result.stdout}\n{result.stderr}",
        )
    return run
