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
CPP_MEMBER_GROUP_HEADINGS = {
    "### Friends",
    "### Protected Attributes",
    "### Protected Functions",
    "### Protected Static Attributes",
    "### Public Attributes",
    "### Public Functions",
    "### Public Static Attributes",
    "### Public Types",
    "### Static Public Attributes",
}
HTML_COMMENT_RE = re.compile(r"<!--\s*(.*?)\s*-->", re.DOTALL)
HTML_ANCHOR_RE = re.compile(r'^\s*<a\s+(?:id|name)="[^"]+"></a>\s*$')
FENCE_RE = re.compile(r"^\s*(```|~~~)")
MARKDOWN_LINK_RE = re.compile(r"\[([^\]\n]+)\]\([^)]+\)")
CODE_SPAN_LINK_RE = re.compile(r"`\[([^\]\n]+)\]\(([^)\n]+)\)`")
SECTION_FIELD_RE = re.compile(
    r"^\s*\*\s+\*\*(?P<title>[A-Z][^:]+):\*\*(?:\s+(?P<body>.*))?$"
)
INDENTED_FIELD_TERM_RE = re.compile(
    r"^\s{2,}(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\([^)]+\))\s*$"
)
FIELD_LIST_RE = re.compile(r"^\s*\*\s+\*\*[A-Z][^:]+:\*\*")
DOCTEST_PROMPT_RE = re.compile(r"\s+(?=(?:>>>|\.\.\.)\s)")
DOCTEST_OUTPUT_RE = re.compile(
    r"^(?P<command>(?:>>>|\.\.\.)\s.*?\))\s+"
    r"(?P<output>(?:array\(|bytearray\(|\{|\[|<[^=>]|"
    r"True\b|False\b|None\b|[0-9]+|[A-Za-z_][\w.]*Error\b).*)$"
)
CPP_COMMENT_START_RE = re.compile(r"\s+(?=//\s)")
CPP_LINK_START_RE = re.compile(r"\[[^\]\n]+\]\([^)]+\)")
CPP_SYMBOL_START_RE = re.compile(
    r"(?P<symbol>[A-Za-z_]\w*(?:(?:::\w+)|(?:\.\w+)|(?:<[^>\n]+>))*)"
    r"(?:\s+[\[\w*&]|\s*[({=])"
)
CPP_KEYWORD_START_RE = re.compile(r"(?:auto|return|for|if|while|switch)\b")
CPP_STATEMENT_TERMINATOR_RE = re.compile(r"[;{]")
CODE_SPAN_RE = re.compile(r"(?P<fence>`+)(?P<code>[^`]*?)(?P=fence)")


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


def normalize_markdown(
    text: str, *, source_dir_name: str | None = None
) -> str:
    text = text.replace("\r\n", "\n")
    text = "\n".join(line.rstrip() for line in text.splitlines()).strip()
    text = sanitize_mdx(text)
    if source_dir_name == "python":
        text = indent_python_member_bodies(text)
    elif source_dir_name == "cpp":
        text = indent_cpp_member_bodies(text)
    return f"{GENERATED_NOTICE}{text}\n"


def sanitize_mdx(text: str) -> str:
    text = HTML_COMMENT_RE.sub(convert_html_comment_to_mdx, text)
    text = normalize_fenced_blocks(text)
    text = promote_markdown_links_inside_code_spans(text)
    text = promote_field_list_sections(text)
    text = escape_cpp_operator_empty_brackets(text)
    return escape_raw_angle_brackets(text)


def convert_html_comment_to_mdx(match: re.Match[str]) -> str:
    return f"{{/* {match.group(1).strip()} */}}"


def escape_cpp_operator_empty_brackets(text: str) -> str:
    return text.replace("operator[](", r"operator\[\](")


def normalize_fenced_blocks(text: str) -> str:
    lines: list[str] = []
    fence_language: str | None = None
    for line in text.splitlines():
        if FENCE_RE.match(line):
            if fence_language is None:
                fence_language = fence_info(line)
            else:
                fence_language = None
            lines.append(line)
            continue

        if fence_language in {"pycon", "python", "py"}:
            lines.extend(expand_doctest_line(line))
            continue
        if fence_language in {"cpp", "c++", "cxx", "cc", "hpp", "h"}:
            lines.extend(expand_cpp_line(line))
            continue

        lines.append(line)
    return "\n".join(lines)


def fence_info(line: str) -> str:
    stripped = line.strip()
    info = stripped[3:].strip()
    if not info:
        return ""
    return info.split(maxsplit=1)[0].lower()


def expand_doctest_line(line: str) -> list[str]:
    indent = line[: len(line) - len(line.lstrip())]
    parts = DOCTEST_PROMPT_RE.sub("\n", line.lstrip()).splitlines()
    expanded: list[str] = []
    for part in parts:
        match = DOCTEST_OUTPUT_RE.match(part)
        if match:
            expanded.append(f"{indent}{match.group('command')}")
            expanded.append(f"{indent}{match.group('output')}")
        else:
            expanded.append(f"{indent}{part}")
    return expanded


def expand_cpp_line(line: str) -> list[str]:
    if not line.strip():
        return [line]

    indent = line[: len(line) - len(line.lstrip())]
    parts = CPP_COMMENT_START_RE.sub("\n", line.lstrip()).splitlines()
    expanded: list[str] = []
    for part in parts:
        for section in split_cpp_comment_from_code(part):
            expanded.extend(split_cpp_statements(section))

    return [
        f"{indent}{strip_markdown_links_from_code(part).rstrip()}"
        for part in expanded
    ]


def split_cpp_comment_from_code(line: str) -> list[str]:
    if not line.startswith("//"):
        return [line]

    for match in re.finditer(r"\s+", line):
        code = line[match.end() :]
        if looks_like_cpp_code_start(code, in_comment=True):
            return [line[: match.start()].rstrip(), code]
    return [line]


def looks_like_cpp_code_start(text: str, *, in_comment: bool) -> bool:
    link_match = CPP_LINK_START_RE.match(text)
    if link_match:
        return not in_comment or statement_starts_before_sentence(
            text, link_match.end()
        )
    keyword_match = CPP_KEYWORD_START_RE.match(text)
    if keyword_match:
        return not in_comment or statement_starts_before_sentence(
            text, keyword_match.end()
        )

    match = CPP_SYMBOL_START_RE.match(text)
    if not match:
        return False
    if not in_comment:
        return True

    symbol = match.group("symbol")
    if not any(marker in symbol for marker in ("_", "::", ".", "<")):
        return False
    return statement_starts_before_sentence(text, match.end())


def statement_starts_before_sentence(text: str, start: int) -> bool:
    remainder = text[start:]
    terminators = [
        position
        for position in (
            remainder.find(";"),
            remainder.find("{"),
        )
        if position >= 0
    ]
    if not terminators:
        return False

    sentence_end = remainder.find(". ")
    if sentence_end < 0:
        return True
    return min(terminators) < sentence_end


def split_cpp_statements(line: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for index, char in enumerate(line):
        if char in "([{":
            depth += 1
        elif char in ")]}":
            depth = max(0, depth - 1)
        elif char == ";" and depth == 0:
            tail = line[index + 1 :]
            code = tail.lstrip()
            if code and looks_like_cpp_code_start(code, in_comment=False):
                parts.append(line[start : index + 1].rstrip())
                start = index + 1 + len(tail) - len(code)

    parts.append(line[start:].strip())
    return [part for part in parts if part]


def strip_markdown_links_from_code(line: str) -> str:
    return MARKDOWN_LINK_RE.sub(r"\1", line)


def promote_markdown_links_inside_code_spans(text: str) -> str:
    lines: list[str] = []
    in_fence = False
    for line in text.splitlines():
        if FENCE_RE.match(line):
            in_fence = not in_fence
            lines.append(line)
            continue

        if in_fence:
            lines.append(line)
        else:
            lines.append(CODE_SPAN_LINK_RE.sub(r"[`\1`](\2)", line))
    return "\n".join(lines)


def promote_field_list_sections(text: str) -> str:
    lines: list[str] = []
    in_field_section = False
    for line in text.splitlines():
        match = SECTION_FIELD_RE.match(line)
        if match:
            lines.append(f"### {match.group('title')}")
            lines.append("")
            if match.group("body"):
                lines.append(f"* {match.group('body')}")
            in_field_section = True
            continue

        if in_field_section:
            if line.startswith("#") or FIELD_LIST_RE.match(line):
                in_field_section = False
            elif INDENTED_FIELD_TERM_RE.match(line):
                lines.append(f"* {line.strip()}")
                continue

        lines.append(line)
    return "\n".join(lines)


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

        lines.append(escape_raw_angle_brackets_in_line(line))
    return "\n".join(lines)


def escape_raw_angle_brackets_in_line(line: str) -> str:
    escaped: list[str] = []
    start = 0
    for match in CODE_SPAN_RE.finditer(line):
        escaped.append(
            line[start : match.start()]
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )
        escaped.append(format_code_span_for_mdx(match))
        start = match.end()
    escaped.append(line[start:].replace("<", "&lt;").replace(">", "&gt;"))
    return "".join(escaped)


def format_code_span_for_mdx(match: re.Match[str]) -> str:
    code = match.group("code")
    if "<" not in code and ">" not in code:
        return match.group(0)
    return f"<code>{escape_html_text(code)}</code>"


def escape_html_text(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def indent_python_member_bodies(text: str) -> str:
    lines: list[str] = []
    member_body: list[str] | None = None

    for line in text.splitlines():
        if line.startswith("#### "):
            flush_api_member_body(lines, member_body)
            member_body = []
            lines.append(line)
            continue

        if member_body is not None and is_python_member_boundary(line):
            flush_api_member_body(lines, member_body)
            member_body = None
            lines.append(line)
            continue

        if member_body is not None:
            member_body.append(line)
        else:
            lines.append(line)

    flush_api_member_body(lines, member_body)
    return "\n".join(lines)


def is_python_member_boundary(line: str) -> bool:
    return line.startswith("{/*") or HTML_ANCHOR_RE.match(line) is not None


def indent_cpp_member_bodies(text: str) -> str:
    lines: list[str] = []
    member_body: list[str] | None = None

    for line in text.splitlines():
        if is_cpp_member_group_heading(line):
            flush_api_member_body(lines, member_body)
            member_body = None
            lines.append(line)
            continue

        if line.startswith("### ") and previous_nonblank_is_anchor(lines):
            flush_api_member_body(lines, member_body)
            member_body = []
            lines.append(line)
            continue

        if member_body is not None and is_cpp_member_boundary(line):
            flush_api_member_body(lines, member_body)
            member_body = None
            lines.append(line)
            continue

        if member_body is not None:
            member_body.append(line)
        else:
            lines.append(line)

    flush_api_member_body(lines, member_body)
    return "\n".join(lines)


def is_cpp_member_group_heading(line: str) -> bool:
    return line in CPP_MEMBER_GROUP_HEADINGS


def is_cpp_member_boundary(line: str) -> bool:
    return line.startswith("{/*") or HTML_ANCHOR_RE.match(line) is not None


def previous_nonblank_is_anchor(lines: list[str]) -> bool:
    for line in reversed(lines):
        if not line.strip():
            continue
        return HTML_ANCHOR_RE.match(line) is not None
    return False


def flush_api_member_body(
    lines: list[str], member_body: list[str] | None
) -> None:
    if member_body is None:
        return

    body = list(member_body)
    while body and not body[0].strip():
        body.pop(0)
    while body and not body[-1].strip():
        body.pop()

    if not body:
        lines.append("")
        return

    lines.append("")
    lines.append('<div className="rmm-api-member-body">')
    lines.append("")
    lines.extend(body)
    lines.append("")
    lines.append("</div>")
    lines.append("")


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
                normalize_markdown(
                    source_path.read_text(encoding="utf-8"),
                    source_dir_name=source_dir_name,
                ),
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
