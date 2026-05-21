# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION.
# SPDX-License-Identifier: Apache-2.0

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT_PATH = REPO_ROOT / "fern" / "scripts" / "generate_api_reference.py"


def load_generator():
    spec = importlib.util.spec_from_file_location(
        "generate_api_reference", SCRIPT_PATH
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_restored_sphinx_sources_keep_api_semantics():
    cpp_source = (
        REPO_ROOT / "fern" / "sphinx" / "source" / "cpp" / "data_containers.md"
    ).read_text(encoding="utf-8")
    python_source = (
        REPO_ROOT / "fern" / "sphinx" / "source" / "python" / "mr.md"
    ).read_text(encoding="utf-8")
    conf = (REPO_ROOT / "fern" / "sphinx" / "source" / "conf.py").read_text(
        encoding="utf-8"
    )

    assert "{doxygengroup} data_containers" in cpp_source
    assert ".. automodule:: rmm.mr" in python_source
    assert "sphinx_markdown_builder" in conf
    assert "../../../cpp/doxygen/xml" in conf


def test_copy_generated_markdown_pages_preserves_rendered_content(tmp_path):
    generator = load_generator()
    markdown_dir = tmp_path / "sphinx" / "build" / "markdown"
    output_dir = tmp_path / "fern" / "pages" / "api_reference"
    (markdown_dir / "cpp").mkdir(parents=True)
    (markdown_dir / "python").mkdir(parents=True)
    (markdown_dir / "cpp" / "data_containers.md").write_text(
        "# Data Containers\n\n"
        '<a id="resource"></a>\n\n'
        "### using resource_ref = cuda::mr::resource_ref"
        "<cuda::mr::device_accessible>\n\n"
        " *#include <device_buffer.hpp>*\n\n"
        "RAII construct for device memory allocation.\n\n"
        "This class uses `cuda::mr::any_resource"
        "<cuda::mr::device_accessible>`.\n\n"
        "Use `[device_buffer](#classrmm_1_1device__buffer)` for storage.\n\n"
        "Reference type returned by operator[](size_type)\n\n"
        "This class allocates untyped and uninitialized device memory.\n",
        encoding="utf-8",
    )
    (markdown_dir / "python" / "mr.md").write_text(
        "# rmm.mr (Memory Resources)\n\n"
        "<!-- !! processed by numpydoc !! -->\n\n"
        "Python memory resource docstrings are rendered here.\n",
        encoding="utf-8",
    )

    copied = generator.copy_generated_markdown_pages(markdown_dir, output_dir)

    cpp_output = (output_dir / "cpp" / "data_containers.md").read_text(
        encoding="utf-8"
    )
    python_output = (output_dir / "python" / "mr.md").read_text(
        encoding="utf-8"
    )
    assert copied == 2
    assert "Generated from the Sphinx API extraction build." in cpp_output
    assert cpp_output.startswith(
        "{/* Generated from the Sphinx API extraction build. "
        "Do not edit directly. */}"
    )
    assert "<!--" not in cpp_output
    assert '<a id="resource"></a>' in cpp_output
    assert "resource_ref&lt;cuda::mr::device_accessible&gt;" in cpp_output
    assert "#include &lt;device_buffer.hpp&gt;" in cpp_output
    assert (
        "<code>cuda::mr::any_resource"
        "&lt;cuda::mr::device_accessible&gt;</code>" in cpp_output
    )
    assert (
        "`cuda::mr::any_resource<cuda::mr::device_accessible>`"
        not in cpp_output
    )
    assert (
        "`cuda::mr::any_resource&lt;cuda::mr::device_accessible&gt;`"
        not in cpp_output
    )
    assert "[`device_buffer`](#classrmm_1_1device__buffer)" in cpp_output
    assert "`[device_buffer](#classrmm_1_1device__buffer)`" not in cpp_output
    assert "operator\\[\\](size_type)" in cpp_output
    assert "[](size_type)" not in cpp_output
    assert (
        "This class allocates untyped and uninitialized device memory."
        in cpp_output
    )
    assert (
        "Python memory resource docstrings are rendered here." in python_output
    )
    assert "{/* !! processed by numpydoc !! */}" in python_output
    assert "<!--" not in python_output
    assert "docs.rapids.ai/api/rmm" not in cpp_output + python_output


def test_normalize_markdown_preserves_doctest_prompt_lines():
    generator = load_generator()
    output = generator.normalize_markdown(
        "# rmm\n\n"
        "### Examples\n\n"
        "```pycon\n"
        '>>> import rmm >>> db = rmm.DeviceBuffer.to_device(b"abc") '
        ">>> db.copy_to_host() array([97, 98, 99], dtype=uint8)\n"
        "```\n"
    )

    assert (
        "```pycon\n"
        ">>> import rmm\n"
        '>>> db = rmm.DeviceBuffer.to_device(b"abc")\n'
        ">>> db.copy_to_host()\n"
        "array([97, 98, 99], dtype=uint8)\n"
        "```"
    ) in output


def test_normalize_markdown_repairs_collapsed_cpp_examples():
    generator = load_generator()
    output = generator.normalize_markdown(
        "# Data Containers\n\n"
        "See [device_buffer](#classrmm_1_1device__buffer) for details.\n\n"
        "Examples:\n"
        "```cpp\n"
        "// Allocates using the default memory // resource and stream. "
        "[device_buffer](#classrmm_1_1device__buffer) buff(100);  "
        "// Allocates using a custom memory resource and // specified stream "
        "custom_memory_resource mr; cuda_stream_view "
        "[stream](#classrmm_1_1device__buffer_1stream) = "
        "cuda_stream_view{}; "
        "// Copies `buff` into a new buffer. cuda_stream_view "
        "[stream](#classrmm_1_1device__buffer_1stream) = cuda_stream_view{};\n"
        "// Moves memory. Deallocates previously allocated // to_buff memory "
        "on `to_buff.stream()`. "
        "[device_buffer](#classrmm_1_1device__buffer) "
        "to_buff(std::move(from_buff));\n"
        "```\n"
    )

    assert "See [device_buffer](#classrmm_1_1device__buffer)" in output
    assert (
        "```cpp\n"
        "// Allocates using the default memory\n"
        "// resource and stream.\n"
        "device_buffer buff(100);\n"
        "// Allocates using a custom memory resource and\n"
        "// specified stream\n"
        "custom_memory_resource mr;\n"
        "cuda_stream_view stream = cuda_stream_view{};\n"
        "// Copies `buff` into a new buffer.\n"
        "cuda_stream_view stream = cuda_stream_view{};\n"
        "// Moves memory. Deallocates previously allocated\n"
        "// to_buff memory on `to_buff.stream()`.\n"
        "device_buffer to_buff(std::move(from_buff));\n"
        "```"
    ) in output
    assert "[device_buffer](#classrmm_1_1device__buffer) buff" not in output
    assert "[stream](#classrmm_1_1device__buffer_1stream)" not in output


def test_normalize_markdown_promotes_field_list_sections():
    generator = load_generator()
    output = generator.normalize_markdown(
        "# rmm\n\n"
        "### *class* rmm.DeviceBuffer\n\n"
        "Bases: [`object`](https://docs.python.org/3/library/functions.html#object)\n\n"
        "* **Attributes:**\n"
        "  [`nbytes`](#rmm.DeviceBuffer.nbytes)\n"
        "  : Gets the size of the buffer in bytes.\n\n"
        "  `ptr`\n"
        "  : Gets a pointer to the underlying data.\n\n"
        "* **Parameters:** **log_file_name**\n"
        "  : Name of the log file.\n"
    )

    assert "### Attributes\n\n* [`nbytes`](#rmm.DeviceBuffer.nbytes)" in output
    assert "### Parameters\n\n* **log_file_name**" in output
    assert "* **Attributes:**" not in output
    assert "* **Parameters:**" not in output
    assert "`ptr`\n  : Gets a pointer to the underlying data." in output


def test_copy_generated_markdown_pages_is_idempotent(tmp_path):
    generator = load_generator()
    markdown_dir = tmp_path / "sphinx" / "build" / "markdown"
    output_dir = tmp_path / "fern" / "pages" / "api_reference"
    (markdown_dir / "python").mkdir(parents=True)
    (markdown_dir / "python" / "rmm.md").write_text(
        "# rmm\n\nGenerated from current docstrings.\n",
        encoding="utf-8",
    )
    stale_page = output_dir / "python" / "removed.md"
    stale_page.parent.mkdir(parents=True)
    stale_page.write_text(
        "# Removed API\n\nThis page came from an older run.\n",
        encoding="utf-8",
    )

    copied = generator.copy_generated_markdown_pages(markdown_dir, output_dir)

    assert copied == 1
    assert not stale_page.exists()
    assert (output_dir / "python" / "rmm.md").exists()


def test_find_command_prefers_current_python_environment(
    tmp_path, monkeypatch
):
    generator = load_generator()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    command = bin_dir / "doxygen"
    command.write_text("#!/bin/sh\n", encoding="utf-8")
    monkeypatch.setattr(generator.sys, "executable", str(bin_dir / "python"))

    assert generator.find_command("doxygen") == str(command)


def test_verify_current_rmm_package_accepts_matching_commit(monkeypatch):
    generator = load_generator()
    env = {"PATH": "/usr/bin"}
    monkeypatch.setattr(
        generator,
        "current_git_commit",
        lambda: "abcdef1234567890",
    )
    monkeypatch.setattr(
        generator,
        "imported_rmm_package",
        lambda env: ("abcdef1234567890", "/env/site-packages/rmm/__init__.py"),
    )

    generator.verify_current_rmm_package(env)


def test_verify_current_rmm_package_rejects_mismatched_commit(monkeypatch):
    generator = load_generator()
    env = {"PATH": "/usr/bin"}
    monkeypatch.setattr(
        generator,
        "current_git_commit",
        lambda: "abcdef1234567890",
    )
    monkeypatch.setattr(
        generator,
        "imported_rmm_package",
        lambda env: ("1234567890abcdef", "/env/site-packages/rmm/__init__.py"),
    )

    with pytest.raises(SystemExit, match="does not match this checkout"):
        generator.verify_current_rmm_package(env)


def test_verify_current_rmm_package_rejects_package_without_commit(
    monkeypatch,
):
    generator = load_generator()
    env = {"PATH": "/usr/bin"}
    monkeypatch.setattr(
        generator,
        "current_git_commit",
        lambda: "abcdef1234567890",
    )
    monkeypatch.setattr(
        generator,
        "imported_rmm_package",
        lambda env: ("", "/env/site-packages/rmm/__init__.py"),
    )

    with pytest.raises(SystemExit, match="does not record its git commit"):
        generator.verify_current_rmm_package(env)


def test_docs_yml_includes_native_api_navigation():
    docs_yml = (REPO_ROOT / "fern" / "docs.yml").read_text(encoding="utf-8")

    assert 'section: "API Reference"' in docs_yml
    assert "./pages/api_reference/cpp/data_containers.md" in docs_yml
    assert "./pages/api_reference/python/mr.md" in docs_yml


def test_fern_config_uses_same_concrete_cli_pin_as_build_script():
    import json

    config = json.loads(
        (REPO_ROOT / "fern" / "fern.config.json").read_text(encoding="utf-8")
    )
    build_script = (REPO_ROOT / "fern" / "build_docs.sh").read_text(
        encoding="utf-8"
    )

    assert config["version"] != "*"
    assert f"fern-api@{config['version']}" in build_script


def test_docs_yml_preview_url_is_absolute():
    docs_yml = (REPO_ROOT / "fern" / "docs.yml").read_text(encoding="utf-8")

    assert 'url: "https://nvidia-rmm.docs.buildwithfern.com/rmm"' in docs_yml
