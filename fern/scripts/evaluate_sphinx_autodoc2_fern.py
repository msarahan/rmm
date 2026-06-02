#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION.
# SPDX-License-Identifier: Apache-2.0

"""Evaluate sphinx-autodoc2-fern against the RMM Python source tree."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RMM_PYTHON_PACKAGE = REPO_ROOT / "python" / "rmm" / "rmm"
DEVICE_BUFFER_PYI = RMM_PYTHON_PACKAGE / "pylibrmm" / "device_buffer.pyi"
DEVICE_BUFFER_PYX = RMM_PYTHON_PACKAGE / "pylibrmm" / "device_buffer.pyx"

DEFAULT_OUTPUT_DIR = (
    Path(tempfile.gettempdir()) / "rmm-sphinx-autodoc2-fern-output"
)

SENTINELS = {
    "pure_python_reinitialize_docstring": "Finalizes and then initializes RMM",
    "pure_python_numpydoc_examples": ">>> @profiler()",
    "cython_devicebuffer_docstring": "Prefetch buffer data",
    "cython_devicebuffer_doctest": ">>> db = rmm.DeviceBuffer.to_device",
    "cython_memory_resource_docstring": "Enable logging of runtime events",
    "fern_paramfield_component": "<ParamField",
    "raw_sphinx_role": ":py:func:",
    "top_level_exports_only": "**Value**: `['DeviceBuffer'",
}


def run_command(
    args: list[str], *, cwd: Path = REPO_ROOT
) -> subprocess.CompletedProcess[str]:
    """Run a command and capture stdout/stderr."""
    return subprocess.run(
        args,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def require_autodoc2(command: str) -> None:
    """Exit with a clear message if the requested CLI is unavailable."""
    if shutil.which(command):
        return
    raise SystemExit(
        f"Could not find {command!r} on PATH. Install the experiment package "
        "with: python -m pip install 'sphinx-autodoc2-fern[cli]'"
    )


def read_generated_markdown(output_dir: Path) -> dict[str, str]:
    """Return generated Markdown file contents keyed by filename."""
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(output_dir.glob("*.md"))
    }


def analyze_generated_output(output_dir: Path) -> dict[str, object]:
    """Summarize the generated output against RMM-specific requirements."""
    files = read_generated_markdown(output_dir)
    all_text = "\n".join(files.values())

    return {
        "output_dir": str(output_dir),
        "markdown_file_count": len(files),
        "markdown_line_count": sum(
            text.count("\n") + 1 for text in files.values()
        ),
        "generated_files": sorted(files),
        "sentinels": {
            name: needle in all_text for name, needle in SENTINELS.items()
        },
        "device_buffer_summary": summarize_file(
            files.get("rmm-pylibrmm-device-buffer.md", "")
        ),
        "memory_resource_summary": summarize_file(
            files.get("rmm-pylibrmm-memory-resource--memory-resource.md", "")
        ),
    }


def summarize_file(text: str) -> dict[str, object]:
    """Collect compact stats for a generated Markdown page."""
    return {
        "line_count": text.count("\n") + 1 if text else 0,
        "code_fence_count": text.count("```"),
        "table_count": text.count("| Name | Description |"),
        "none_description_count": text.count(" | None |"),
        "has_doctest_prompt": ">>>" in text,
        "has_paramfield": "<ParamField" in text,
        "has_raw_sphinx_role": ":py:" in text or ":class:" in text,
    }


def output_excerpt(text: str, *, limit: int = 1200) -> str:
    """Return a bounded command-output excerpt for JSON reporting."""
    stripped = text.strip()
    if len(stripped) <= limit:
        return stripped
    return f"{stripped[:limit]}... [truncated]"


def evaluate(autodoc2: str, output_dir: Path) -> dict[str, object]:
    """Run the package experiment and return a JSON-serializable summary."""
    require_autodoc2(autodoc2)

    output_dir = output_dir.resolve()
    write_result = run_command(
        [
            autodoc2,
            "write",
            str(RMM_PYTHON_PACKAGE),
            "-m",
            "rmm",
            "--output",
            str(output_dir),
            "--clean",
            "--renderer",
            "fern",
        ]
    )

    pyi_result = run_command(
        [
            autodoc2,
            "list",
            str(DEVICE_BUFFER_PYI),
            "-m",
            "rmm.pylibrmm.device_buffer",
            "--one-line",
        ]
    )
    pyx_result = run_command(
        [
            autodoc2,
            "list",
            str(DEVICE_BUFFER_PYX),
            "-m",
            "rmm.pylibrmm.device_buffer",
            "--one-line",
        ]
    )

    result: dict[str, object] = {
        "autodoc2": autodoc2,
        "write": {
            "returncode": write_result.returncode,
            "stdout": output_excerpt(write_result.stdout),
            "stderr": output_excerpt(write_result.stderr),
        },
        "device_buffer_pyi_list": {
            "returncode": pyi_result.returncode,
            "stdout_line_count": len(pyi_result.stdout.splitlines()),
            "stdout": output_excerpt(pyi_result.stdout),
            "stderr": output_excerpt(pyi_result.stderr),
        },
        "device_buffer_pyx_list": {
            "returncode": pyx_result.returncode,
            "stdout": output_excerpt(pyx_result.stdout),
            "stderr": output_excerpt(pyx_result.stderr),
        },
    }

    if write_result.returncode == 0:
        result["generated_output"] = analyze_generated_output(output_dir)

    return result


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=(
            "Run sphinx-autodoc2-fern against RMM and summarize whether it "
            "preserves the API-doc details RMM needs."
        )
    )
    parser.add_argument(
        "--autodoc2",
        default="autodoc2",
        help="autodoc2 command to run, default: autodoc2",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"directory for generated Markdown, default: {DEFAULT_OUTPUT_DIR}",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit compact JSON instead of pretty-printed JSON",
    )
    args = parser.parse_args(argv)

    result = evaluate(args.autodoc2, args.output)
    if args.json:
        print(json.dumps(result, sort_keys=True))
    else:
        print(json.dumps(result, indent=2, sort_keys=True))

    write = result["write"]
    return int(write["returncode"]) if isinstance(write, dict) else 1


if __name__ == "__main__":
    sys.exit(main())
