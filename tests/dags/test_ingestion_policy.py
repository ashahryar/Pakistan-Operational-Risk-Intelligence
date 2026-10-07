"""Task 40 -- ingestion policy: a source failure is a task failure (never a silent green run), "no new reports" is not a failure, S3 archiving is explicit."""

import importlib
import sys
from pathlib import Path

import pytest

from pipeline.helpers import s3_optional as S3

ROOT = Path(__file__).resolve().parents[2]
EXTRACTION = str(ROOT / "scripts" / "extraction")


# --- S3 gate -------------------------------------------------------------------------------------------------------------------
FULL = {"AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s", "AWS_REGION": "eu-west-1", "S3_BUCKET": "b"}


def test_s3_state_disabled_unconfigured_enabled():
    assert S3.s3_state({**FULL, "PORI_S3_UPLOAD": "off"})[0] == "disabled"
    assert S3.s3_state({**FULL, "PORI_S3_UPLOAD": "False"})[0] == "disabled"
    state, why = S3.s3_state({"AWS_REGION": "x"})
    assert state == "unconfigured" and "AWS_ACCESS_KEY_ID" in why and "S3_BUCKET" in why
    assert S3.s3_state(FULL)[0] == "enabled" and S3.s3_state({**FULL, "PORI_S3_UPLOAD": "auto"})[0] == "enabled"


def test_blank_values_count_as_missing():
    assert S3.s3_state({**FULL, "S3_BUCKET": "  "})[0] == "unconfigured"


def test_a_disabled_upload_is_skipped_not_succeeded_and_never_touches_aws(monkeypatch):
    airflow_exc = pytest.importorskip("airflow.exceptions")
    monkeypatch.setattr(S3, "_settings", lambda env=None: {**FULL, "PORI_S3_UPLOAD": "off"})
    monkeypatch.setattr(S3, "check_credentials", lambda env=None: pytest.fail("AWS must not be contacted when archiving is off"))
    with pytest.raises(airflow_exc.AirflowSkipException, match="Nothing was uploaded"):
        S3.upload_folder_or_skip("data/raw/x", "raw/x")


def test_rejected_credentials_fail_fast_with_a_clear_message(monkeypatch):
    boto3 = pytest.importorskip("boto3")
    from botocore.exceptions import ClientError

    class FakeSts:
        def get_caller_identity(self):
            raise ClientError({"Error": {"Code": "InvalidClientTokenId"}}, "GetCallerIdentity")

    monkeypatch.setattr(boto3, "client", lambda *a, **k: FakeSts())
    with pytest.raises(RuntimeError, match=r"rejected the credentials \(InvalidClientTokenId\).*PORI_S3_UPLOAD=off"):
        S3.check_credentials(FULL)


# --- extractor failure policy ----------------------------------------------------------------------------------------------------
class Resp:
    status_code, url, text = 200, "https://example.test/", "<html><body>no reports here</body></html>"


class Client:
    def __init__(self, resp):
        self.resp = resp

    def get(self, *a, **k):
        return self.resp


@pytest.fixture
def extractors():
    """The extractors import `common.*` from scripts/extraction/common, which collides with the repository's top-level `common` package: isolate the imports."""
    saved = {k: sys.modules.pop(k) for k in list(sys.modules) if k == "common" or k.startswith("common.")}
    for n in ("extract_ndma", "extract_pdma", "extract_pmd"):
        sys.modules.pop(n, None)
    sys.path.insert(0, EXTRACTION)
    try:
        yield {n: importlib.import_module(n) for n in ("extract_ndma", "extract_pdma", "extract_pmd")}
    finally:
        sys.path.remove(EXTRACTION)
        for k in [k for k in sys.modules if k == "common" or k.startswith("common.") or k in ("extract_ndma", "extract_pdma", "extract_pmd")]:
            sys.modules.pop(k, None)
        sys.modules.update(saved)


def run_main(mod, monkeypatch, argv):
    monkeypatch.setattr(sys, "argv", ["x", *argv])
    mod.main()


@pytest.mark.parametrize("name,argv", [("extract_ndma", ["sitreps"]), ("extract_pdma", ["earthquake"])])
def test_unreachable_listing_page_fails_the_task(extractors, monkeypatch, name, argv):
    mod = extractors[name]
    monkeypatch.setattr(mod, "client", Client(None))
    mod.FAILURES.clear()
    with pytest.raises(SystemExit) as e:
        run_main(mod, monkeypatch, argv)
    assert e.value.code == 1 and any("unreachable" in f for f in mod.FAILURES)
    mod.FAILURES.clear()


@pytest.mark.parametrize("name,argv", [("extract_ndma", ["sitreps"]), ("extract_pdma", ["earthquake"])])
def test_a_reachable_source_with_nothing_new_is_not_a_failure(extractors, monkeypatch, name, argv):
    mod = extractors[name]
    monkeypatch.setattr(mod, "client", Client(Resp()))
    mod.FAILURES.clear()
    run_main(mod, monkeypatch, argv)            # no SystemExit
    assert mod.FAILURES == []


def test_pmd_with_no_fetched_report_fails_and_writes_nothing(extractors, monkeypatch, tmp_path):
    mod = extractors["extract_pmd"]
    monkeypatch.setattr(mod, "client", Client(None))
    monkeypatch.setattr(mod, "write_verified_bytes", lambda *a, **k: pytest.fail("a failed fetch must not overwrite latest.json"))
    with pytest.raises(SystemExit) as e:
        run_main(mod, monkeypatch, ["all"])
    assert e.value.code == 1


def test_every_production_dag_archives_through_the_explicit_s3_gate():
    for n in ("ndma_dag.py", "pdma_dag.py", "pmd_dag.py", "manual_dag.py", "weekly_dag.py"):
        src = (ROOT / "pipeline" / "dags" / n).read_text(encoding="utf-8")
        assert "s3_optional" in src and "aws_helper" not in src, n
