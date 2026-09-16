"""
databricks/tests/conftest.py

Task 16A (Phase 1 / ADR-0001). PySpark is not currently installed in
this project's environments (see databricks/README.md's "What is NOT
done yet"). Every test in this directory that needs a real
SparkSession uses the `spark` fixture below, which calls
`pytest.importorskip("pyspark")` -- so this suite reports SKIPPED
(not failed, not silently absent) when pyspark isn't installed, and
will actually run once it is.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture(scope="session")
def spark():
    pytest.importorskip("pyspark", reason="pyspark not installed -- see databricks/README.md")
    from databricks.src.common.spark_session import get_local_spark_session, stop_spark_session

    session = get_local_spark_session(app_name="pori-lakehouse-tests")
    yield session
    stop_spark_session(session)
