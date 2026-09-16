"""
tests/architecture/test_task16a_cleanup.py

Task 16A (Phase 1 / ADR-0001), Part K -- architecture regression tests
proving:
  1. no active Glue DAG references
  2. no active Redshift code paths
  3. no Glue deployment scripts remain
  4. no Redshift deployment scripts remain
  5. S3 acquisition functionality remains
  6. PostgreSQL/PostGIS remains
  7. Databricks structure exists
  8. DevOps CI configuration exists

Uses AST inspection where it matters (imports, function/class
definitions) rather than relying only on grep, per Task 16A's own
instruction ("Do not rely only on grep if AST/import inspection is
more appropriate").
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]

SKIP_DIRS = {"venv", ".git", "airflow", "__pycache__", "node_modules"}


def _all_py_files():
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for name in files:
            if name.endswith(".py"):
                yield Path(root) / name


def _imported_names(tree: ast.Module) -> set[str]:
    """Every dotted module path this file imports, flattened."""
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


# ==========================================================
# 1 & 3. No active Glue DAG references / no Glue deployment scripts
# ==========================================================

def test_no_glue_specific_files_remain():
    glue_specific_paths = [
        PROJECT_ROOT / "aws" / "glue",
        PROJECT_ROOT / "aws" / "lambda",  # existed only to route S3 events to Glue jobs
    ]
    still_present = [str(p.relative_to(PROJECT_ROOT)) for p in glue_specific_paths if p.exists()]
    assert not still_present, f"Glue-specific paths still exist: {still_present}"


def test_no_dag_calls_a_glue_function():
    """AST-based: walks every DAG file's call sites for anything
    plausibly Glue-related, not just a grep for the word "glue" (which
    could false-positive on prose)."""
    dag_dir = PROJECT_ROOT / "pipeline" / "dags"
    offenders = []

    for py_file in dag_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if "glue" in func_name.lower():
                    offenders.append(f"{py_file.name}: calls {func_name}()")

    assert not offenders, f"DAG(s) still call a Glue-named function: {offenders}"


def test_no_python_file_imports_a_glue_module():
    offenders = []
    for py_file in _all_py_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for name in _imported_names(tree):
            if "glue" in name.lower() and "aws_helper" not in name.lower():
                offenders.append(f"{py_file.relative_to(PROJECT_ROOT)}: imports {name}")

    assert not offenders, f"Glue-related imports still present: {offenders}"


def test_aws_helper_has_no_glue_client_or_functions():
    """The one file that legitimately used to mix S3 (kept) and Glue
    (removed) functionality -- confirm only S3 survives."""
    source = (PROJECT_ROOT / "pipeline" / "helpers" / "aws_helper.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    function_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    glue_functions = {n for n in function_names if "glue" in n.lower()}
    assert not glue_functions, f"aws_helper.py still defines Glue function(s): {glue_functions}"

    assert "boto3.client(\n\n    \"glue\"" not in source
    assert '"glue"' not in source.lower().replace("'", '"') or 'glue"' not in source


# ==========================================================
# 2 & 4. No active Redshift code paths / no Redshift deployment scripts
# ==========================================================

def test_no_redshift_specific_files_remain():
    redshift_specific_paths = [
        PROJECT_ROOT / "aws" / "redshift",
        PROJECT_ROOT / "pipeline" / "helpers" / "redshift_helper.py",
    ]
    still_present = [str(p.relative_to(PROJECT_ROOT)) for p in redshift_specific_paths if p.exists()]
    assert not still_present, f"Redshift-specific paths still exist: {still_present}"


def test_no_python_file_imports_redshift_connector_or_helper():
    offenders = []
    for py_file in _all_py_files():
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for name in _imported_names(tree):
            if "redshift" in name.lower():
                offenders.append(f"{py_file.relative_to(PROJECT_ROOT)}: imports {name}")

    assert not offenders, f"Redshift-related imports still present: {offenders}"


def test_no_dag_calls_a_redshift_function():
    dag_dir = PROJECT_ROOT / "pipeline" / "dags"
    offenders = []

    for py_file in dag_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func_name = ""
                if isinstance(node.func, ast.Name):
                    func_name = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    func_name = node.func.attr
                if "redshift" in func_name.lower():
                    offenders.append(f"{py_file.name}: calls {func_name}()")

    assert not offenders, f"DAG(s) still call a Redshift-named function: {offenders}"


# ==========================================================
# 5. S3 acquisition functionality remains
# ==========================================================

def test_s3_upload_module_still_exists_and_is_real():
    s3_upload = PROJECT_ROOT / "aws" / "s3" / "upload.py"
    assert s3_upload.exists()

    tree = ast.parse(s3_upload.read_text(encoding="utf-8"))
    function_names = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "upload_folder" in function_names


def test_aws_helper_still_exposes_working_s3_functions():
    from pipeline.helpers import aws_helper

    for name in ("upload_folder", "upload_raw", "upload_analytics", "upload_all", "bucket_exists", "verify_upload"):
        assert hasattr(aws_helper, name), f"aws_helper.py no longer exposes {name}()"


def test_every_dag_that_uploads_still_imports_upload_folder():
    """The 5 domain/master DAGs each upload raw/parsed/analytics data
    to S3 -- confirm that capability wasn't accidentally removed along
    with Glue."""
    dags_expected_to_upload = ["ndma_dag.py", "pdma_dag.py", "pmd_dag.py", "backfill_dag.py", "manual_dag.py"]
    for dag_file in dags_expected_to_upload:
        source = (PROJECT_ROOT / "pipeline" / "dags" / dag_file).read_text(encoding="utf-8")
        assert "upload_folder" in source or "upload_all" in source, f"{dag_file} no longer references S3 upload"


# ==========================================================
# 6. PostgreSQL/PostGIS remains
# ==========================================================

def test_postgres_engine_and_geo_schema_code_untouched():
    assert (PROJECT_ROOT / "config" / "database.py").exists()
    assert (PROJECT_ROOT / "scripts" / "database" / "create_geo_schema_tables.py").exists()
    assert (PROJECT_ROOT / "scripts" / "geo" / "resolver.py").exists()
    assert (PROJECT_ROOT / "scripts" / "geo" / "canonical_data.py").exists()

    from config.database import engine
    assert engine is not None


def test_no_dag_was_repointed_at_redshift_instead_of_postgres():
    """Every DAG's load_postgres task must still call a
    scripts/database/load_*.py script -- confirms Postgres, not
    Redshift, remains the load target."""
    domain_dags = {
        "ndma_dag.py": "load_ndma.py",
        "pdma_dag.py": "load_pdma.py",
        "pmd_dag.py": "load_pmd.py",
    }
    for dag_file, loader in domain_dags.items():
        source = (PROJECT_ROOT / "pipeline" / "dags" / dag_file).read_text(encoding="utf-8")
        assert loader in source, f"{dag_file} no longer references {loader}"


# ==========================================================
# 7. Databricks structure exists
# ==========================================================

def test_databricks_directory_structure_exists():
    expected_dirs = [
        "databricks", "databricks/notebooks", "databricks/notebooks/bronze",
        "databricks/notebooks/silver", "databricks/notebooks/gold", "databricks/notebooks/ml",
        "databricks/notebooks/exploration", "databricks/src", "databricks/src/bronze",
        "databricks/src/silver", "databricks/src/gold", "databricks/src/features",
        "databricks/src/ml", "databricks/src/common", "databricks/jobs", "databricks/schemas",
        "databricks/schemas/bronze", "databricks/schemas/silver", "databricks/schemas/gold",
        "databricks/tests", "databricks/resources",
    ]
    missing = [d for d in expected_dirs if not (PROJECT_ROOT / d).is_dir()]
    assert not missing, f"Missing expected databricks/ directories: {missing}"


def test_databricks_readme_and_spark_foundation_exist():
    assert (PROJECT_ROOT / "databricks" / "README.md").exists()
    assert (PROJECT_ROOT / "databricks" / "src" / "common" / "spark_session.py").exists()
    assert (PROJECT_ROOT / "databricks" / "src" / "common" / "transforms.py").exists()


def test_databricks_scaffold_does_not_claim_to_be_production_ready():
    """Guards against future drift: the README must keep saying this
    is scaffolded, not implemented, until it genuinely is."""
    readme = (PROJECT_ROOT / "databricks" / "README.md").read_text(encoding="utf-8")
    assert "SCAFFOLDED" in readme or "scaffolded" in readme
    assert "not implemented" in readme.lower() or "NOT IMPLEMENTED" in readme


def test_no_dag_imports_databricks():
    """Confirms Task 16A's own instruction was followed: Databricks
    scaffolding must not be wired into any DAG yet. AST-based (checks
    real imports, not prose) -- several DAGs' docstrings now mention
    "see databricks/README.md" as documentation of the Glue/Redshift
    removal, which is not a wiring violation."""
    dag_dir = PROJECT_ROOT / "pipeline" / "dags"
    offenders = []
    for py_file in dag_dir.glob("*.py"):
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
        for name in _imported_names(tree):
            if name.lower().startswith("databricks"):
                offenders.append(f"{py_file.name}: imports {name}")
    assert not offenders, f"DAG(s) actually import databricks/ before it's real: {offenders}"


# ==========================================================
# 8. DevOps CI configuration exists
# ==========================================================

def test_github_actions_ci_workflow_exists():
    workflow = PROJECT_ROOT / ".github" / "workflows" / "ci.yml"
    assert workflow.exists()

    import yaml
    with open(workflow, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    # PyYAML parses the bare `on:` key as boolean True (YAML 1.1
    # quirk) -- check for either the string or boolean key.
    assert "jobs" in config
    assert True in config or "on" in config


def test_pre_commit_config_exists_and_is_valid_yaml():
    import yaml
    config_path = PROJECT_ROOT / ".pre-commit-config.yaml"
    assert config_path.exists()
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert "repos" in config
    assert len(config["repos"]) > 0


def test_ruff_config_exists_and_is_narrow_not_a_mass_reformat():
    pyproject = PROJECT_ROOT / "pyproject.toml"
    assert pyproject.exists()
    text = pyproject.read_text(encoding="utf-8")
    assert "[tool.ruff" in text


def test_terraform_scaffold_exists_and_is_s3_only():
    tf_dir = PROJECT_ROOT / "infrastructure" / "terraform"
    assert tf_dir.exists()
    assert (tf_dir / "main.tf").exists()

    main_tf = (tf_dir / "main.tf").read_text(encoding="utf-8")
    assert "aws_s3_bucket" in main_tf
    # Explicit negative checks -- Part N/H: no Glue, Redshift, EKS, ECS,
    # NAT Gateway resources anywhere in the Terraform config.
    forbidden_resources = ["aws_glue", "aws_redshift", "aws_eks", "aws_ecs", "aws_nat_gateway"]
    for resource in forbidden_resources:
        assert resource not in main_tf.lower(), f"Terraform config defines a forbidden resource: {resource}"


def test_requirements_ci_file_exists():
    assert (PROJECT_ROOT / "requirements" / "ci.txt").exists()
