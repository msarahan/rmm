#!/usr/bin/env python3
# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION.
# SPDX-License-Identifier: Apache-2.0

"""Generate Fern API reference pages from Sphinx-rendered Markdown."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FERN_ROOT = REPO_ROOT / "fern"
SPHINX_ROOT = FERN_ROOT / "sphinx"
SPHINX_SOURCE_DIR = SPHINX_ROOT / "source"
SPHINX_BUILD_DIR = SPHINX_ROOT / "build"
MARKDOWN_BUILD_DIR = SPHINX_BUILD_DIR / "markdown"
API_OUTPUT_DIR = FERN_ROOT / "pages" / "api_reference"
DOXYGEN_DIR = REPO_ROOT / "cpp" / "doxygen"
DOXYGEN_XML_INDEX = DOXYGEN_DIR / "xml" / "index.xml"

GENERATED_NOTICE = (
    "{/* Generated from the Sphinx API extraction build. "
    "Do not edit directly. */}\n\n"
)
API_SOURCE_DIRS = ("cpp", "python")
HTML_COMMENT_RE = re.compile(r"<!--\s*(.*?)\s*-->", re.DOTALL)
HTML_ANCHOR_RE = re.compile(r'^\s*<a\s+(?:id|name)="[^"]+"></a>\s*$')
FENCE_RE = re.compile(r"^\s*(```|~~~)")


def relative_to_repo(path: Path) -> str:
    """Return a repo-relative path for concise command output."""
    return str(path.relative_to(REPO_ROOT))


def require_command(command: str) -> None:
    if find_command(command) is None:
        raise SystemExit(
            f"{command!r} is required to generate Fern API reference pages. "
            "Install the docs environment from dependencies.yaml."
        )


def find_command(command: str) -> str | None:
    sibling = Path(sys.executable).with_name(command)
    if sibling.exists():
        return str(sibling)
    return shutil.which(command)


def docs_environment() -> dict[str, str]:
    env = os.environ.copy()
    version = (REPO_ROOT / "VERSION").read_text(encoding="utf-8").strip()
    major_minor = ".".join(version.split(".")[:2])
    env.setdefault("RAPIDS_VERSION", version)
    env.setdefault("RAPIDS_VERSION_MAJOR_MINOR", major_minor)
    return env


def run_command(args: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    display = " ".join(args)
    print(f"+ ({relative_to_repo(cwd)}) {display}", file=sys.stderr)
    subprocess.run(args, cwd=cwd, env=env, check=True)


def current_git_commit() -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=REPO_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def imported_rmm_package(env: dict[str, str]) -> tuple[str, str]:
    probe = (
        "import inspect, json, rmm; "
        "print(json.dumps({"
        "'commit': rmm.__git_commit__, "
        "'path': inspect.getfile(rmm)"
        "}))"
    )
    result = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise SystemExit(
            "Unable to import the RMM Python package for API docs. "
            "Build and install the current RMM package before running "
            "fern/build_docs.sh.\n"
            f"{result.stderr.strip()}"
        )

    data = json.loads(result.stdout)
    return data["commit"], data["path"]


def verify_current_rmm_package(env: dict[str, str]) -> None:
    git_commit = current_git_commit()
    package_commit, package_path = imported_rmm_package(env)

    if not package_commit:
        raise SystemExit(
            f"The imported rmm package at {package_path} does not record its "
            "git commit. Build and install the current RMM package before "
            "generating Fern API docs."
        )

    if package_commit == git_commit:
        return
    if git_commit.startswith(package_commit) or package_commit.startswith(
        git_commit
    ):
        return

    raise SystemExit(
        f"The imported rmm package at {package_path} was built from "
        f"{package_commit}, which does not match this checkout ({git_commit}). "
        "Install the package artifacts built from this commit before "
        "generating Fern API docs."
    )


def build_doxygen_xml(env: dict[str, str]) -> None:
    require_command("doxygen")
    doxygen = find_command("doxygen")
    if doxygen is None:
        raise SystemExit("'doxygen' is required to generate C++ API XML.")
    run_command([doxygen, "Doxyfile"], cwd=DOXYGEN_DIR, env=env)
    if not DOXYGEN_XML_INDEX.exists():
        raise SystemExit(
            "Doxygen completed without producing cpp/doxygen/xml/index.xml"
        )


def build_sphinx_markdown(env: dict[str, str]) -> None:
    shutil.rmtree(MARKDOWN_BUILD_DIR, ignore_errors=True)
    run_command(
        [
            sys.executable,
            "-m",
            "sphinx.cmd.build",
            "-M",
            "markdown",
            ".",
            "../build",
        ],
        cwd=SPHINX_SOURCE_DIR,
        env=env,
    )
    if not MARKDOWN_BUILD_DIR.exists():
        raise SystemExit(
            "Sphinx completed without producing fern/sphinx/build/markdown"
        )


def normalize_markdown(text: str) -> str:
    text = text.replace("\r\n", "\n")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    text = sanitize_mdx(text)
    return f"{GENERATED_NOTICE}{text}\n"


def sanitize_mdx(text: str) -> str:
    text = HTML_COMMENT_RE.sub(convert_html_comment_to_mdx, text)
    text = escape_cpp_operator_empty_brackets(text)
    return escape_raw_angle_brackets(text)


def convert_html_comment_to_mdx(match: re.Match[str]) -> str:
    return f"{{/* {match.group(1).strip()} */}}"


def escape_cpp_operator_empty_brackets(text: str) -> str:
    return text.replace("operator[](", r"operator\[\](")


def escape_raw_angle_brackets(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue

        if in_fence or HTML_ANCHOR_RE.match(line):
            lines.append(line)
            continue

        lines.append(line.replace("<", "&lt;").replace(">", "&gt;"))
    return "\n".join(lines)


def copy_generated_markdown_pages(markdown_dir: Path, output_dir: Path) -> int:
    shutil.rmtree(output_dir, ignore_errors=True)
    copied = 0
    for source_dir_name in API_SOURCE_DIRS:
        source_dir = markdown_dir / source_dir_name
        if not source_dir.exists():
            continue
        for source_path in sorted(source_dir.rglob("*.md")):
            target_path = output_dir / source_path.relative_to(markdown_dir)
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(
                normalize_markdown(source_path.read_text(encoding="utf-8")),
                encoding="utf-8",
            )
            copied += 1
    return copied


def main() -> int:
    env = docs_environment()
    verify_current_rmm_package(env)
    build_doxygen_xml(env)
    build_sphinx_markdown(env)
    copied = copy_generated_markdown_pages(MARKDOWN_BUILD_DIR, API_OUTPUT_DIR)
    if copied == 0:
        raise SystemExit("No API reference Markdown pages were generated")
    print(f"Generated {copied} Fern API reference pages.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
