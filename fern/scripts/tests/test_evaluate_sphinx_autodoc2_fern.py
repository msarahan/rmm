# SPDX-FileCopyrightText: Copyright (c) 2026, NVIDIA CORPORATION.
# SPDX-License-Identifier: Apache-2.0

from pathlib import Path

from fern.scripts.evaluate_sphinx_autodoc2_fern import (
    analyze_generated_output,
)


def test_analyze_generated_output_tracks_rmm_specific_gaps(tmp_path: Path):
    (tmp_path / "rmm-pylibrmm-device-buffer.md").write_text(
        "\n".join(
            [
                "# rmm.pylibrmm.device_buffer",
                "```python",
                "class rmm.pylibrmm.device_buffer.DeviceBuffer",
                "```",
                "| Name | Description |",
                "| [`DeviceBuffer`](#devicebuffer) | None |",
            ]
        ),
        encoding="utf-8",
    )
    (tmp_path / "rmm-rmm.md").write_text(
        "\n".join(
            [
                "Finalizes and then initializes RMM",
                ":py:func:`~rmm.reinitialize()`",
                "**Value**: `['DeviceBuffer', 'enable_logging']`",
            ]
        ),
        encoding="utf-8",
    )

    summary = analyze_generated_output(tmp_path)

    assert summary["markdown_file_count"] == 2
    sentinels = summary["sentinels"]
    assert sentinels["pure_python_reinitialize_docstring"]
    assert sentinels["raw_sphinx_role"]
    assert sentinels["top_level_exports_only"]
    assert not sentinels["cython_devicebuffer_docstring"]
    assert not sentinels["fern_paramfield_component"]

    device_buffer = summary["device_buffer_summary"]
    assert device_buffer["none_description_count"] == 1
    assert not device_buffer["has_doctest_prompt"]
