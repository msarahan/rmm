# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FERN_ROOT = REPO_ROOT / "fern"


def test_build_docs_pins_npx_fern_api_fallback():
    script = REPO_ROOT / "fern" / "build_docs.sh"
    text = script.read_text(encoding="utf-8")

    assert '"fern-api@5.30.4"' in text
    assert 'FERN_CMD=("npx" "--yes" "fern-api")' not in text


def test_build_docs_runs_sphinx_api_generator():
    script = REPO_ROOT / "fern" / "build_docs.sh"
    text = script.read_text(encoding="utf-8")

    assert "generate_api_reference.py" in text
    assert "run_fern check --warnings" in text


def test_ci_docs_env_uses_current_build_artifacts():
    script = REPO_ROOT / "ci" / "build_docs.sh"
    text = script.read_text(encoding="utf-8")

    assert "rapids-download-conda-from-github cpp" in text
    assert 'rapids-package-name "conda_python" rmm' in text
    assert '--prepend-channel "${CPP_CHANNEL}"' in text
    assert '--prepend-channel "${PYTHON_CHANNEL}"' in text


def test_fern_docs_do_not_link_to_legacy_api_reference():
    docs_yml = FERN_ROOT / "docs.yml"
    page_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((FERN_ROOT / "pages").rglob("*.md"))
    )

    assert "docs.rapids.ai/api/rmm" not in page_text
    assert "api_reference" in docs_yml.read_text(encoding="utf-8")


def test_home_page_links_native_api_entry_points():
    home = (FERN_ROOT / "pages" / "index.md").read_text(encoding="utf-8")

    assert "[C++ API](./api_reference/cpp/index.md)" in home
    assert "[Python API](./api_reference/python/index.md)" in home
