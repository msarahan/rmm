# RMM Fern Generator Alternatives

This branch evaluates whether `sphinx-autodoc2-fern` or MyST can replace the
current Sphinx/Doxygen extraction step for RMM's Fern API docs.

## Short Answer

`sphinx-autodoc2-fern` is not a drop-in replacement for RMM. It is useful for
pure-Python modules because it statically parses `.py` files and does not need
to import the built package. It does not parse RMM's Cython `.pyx` files, and
the `.pyi` stubs have signatures but not the docstrings that currently hold the
user-facing API prose, doctest examples, parameter notes, and memory-resource
details.

MyST is still useful for authored docs and RST migration. It lets Sphinx parse
Markdown and supports Sphinx roles/directives, including `eval-rst`. It does not
replace Python or C++ API extraction by itself.

For C++, the realistic source-first path remains Doxygen XML plus a renderer.
Breathe bridges Doxygen XML into Sphinx. Exhale can auto-generate RST wrapper
pages from Doxygen XML, but it is still a Sphinx/Breathe layer and does not emit
Fern-native API pages directly.

## Reproduction

Install the experiment package in a temporary environment:

```bash
python -m venv /tmp/rmm-autodoc2-fern-venv
/tmp/rmm-autodoc2-fern-venv/bin/pip install 'sphinx-autodoc2-fern[cli]'
```

Run the RMM comparison:

```bash
PATH=/tmp/rmm-autodoc2-fern-venv/bin:$PATH \
  python fern/scripts/evaluate_sphinx_autodoc2_fern.py
```

The script writes generated Markdown to the platform temp directory under
`rmm-sphinx-autodoc2-fern-output` by default and prints a JSON summary.

## Observed Results

Package behavior:

- Installing plain `sphinx-autodoc2-fern` exposes `autodoc2`, but the CLI fails
  until the `cli` extra is installed because `rich` is missing.
- Directory analysis of `python/rmm/rmm` finds `.py` and `.pyi` modules, but it
  also includes package internals unless exclusions are added.
- Direct analysis of `python/rmm/rmm/pylibrmm/device_buffer.pyx` fails at
  `cimport`, so `.pyx` docstrings are unavailable to this tool.
- Direct analysis of `python/rmm/rmm/pylibrmm/device_buffer.pyi` succeeds and
  gets signatures for `DeviceBuffer`, `prefetch`, `copy_to_host`, and related
  methods.

Generated output:

- This trial generated 22 Markdown files and 1,789 lines of Markdown.
- Pure Python docstrings such as `rmm.rmm.reinitialize` are present.
- Sphinx roles inside those docstrings remain raw, for example
  `:py:func:\`~rmm.reinitialize()\``.
- `DeviceBuffer` and memory-resource pages mostly contain signatures with
  `None` descriptions, because the matching `.pyi` files do not contain the
  rich docstrings from `.pyx`.
- The generated `DeviceBuffer` page had no doctest prompts and no `ParamField`
  components.
- The generator did not emit Fern `ParamField` components for RMM's NumPy-style
  docstrings in this trial.
- Output files are flat slug files like `rmm-pylibrmm-device-buffer.md`, not the
  curated `fern/pages/api_reference/python/*.md` shape RMM currently uses.

Compared with the current Fern dev rendering, the existing Sphinx-backed path
still preserves key Cython docstring content. The live Python pages contain
`Prefetch buffer data`, `RMM_LOG_FILE`, `DeviceBuffer`, `Enable logging of
runtime events`, and the `rmm-api-member-body` styling wrapper.

## Feature Implications

### Python API

`sphinx-autodoc2-fern` could reduce the need to import built RMM for pure
Python modules, but it would require one of these changes before it can cover
RMM's actual API:

- move Cython docstrings into `.pyi` stubs,
- teach the tool to parse Cython syntax and docstrings,
- or keep the current import/Sphinx path for Cython-backed objects.

The first option would move API prose into source-controlled stubs, but it is a
substantial docs-source migration. The third option is closest to the current
pipeline.

### MyST And RST

MyST is a good migration format for handwritten RST pages because it keeps a
Sphinx-compatible authoring model while allowing Markdown. It is especially
useful for pages that still need Sphinx roles/directives during conversion.

It does not solve the final Fern problem by itself. If we keep Sphinx/MyST as an
intermediate build, we still need either a Markdown builder plus postprocessing
or a custom source-to-Fern renderer.

### Intersphinx

Sphinx intersphinx works through `objects.inv` inventories. Fern will not
automatically preserve those semantic links unless the conversion step resolves
them to concrete URLs or Fern gains an inventory-aware link resolver. MyST
Document Engine can consume Sphinx inventories, but that is separate from Fern's
current MDX rendering.

### C++ API

No tested Python alternative replaces Doxygen for RMM C++ docs. Doxygen already
extracts C++ declarations and comments and can generate XML. Breathe consumes
that XML in Sphinx; Exhale can auto-generate RST wrapper pages from it. A Fern
pipeline still needs a Doxygen XML to Fern/MDX renderer or a Sphinx/Breathe
intermediate conversion.

## Recommendation

Keep the current source-driven Sphinx/Doxygen extraction as the baseline for
this branch. Consider `sphinx-autodoc2-fern` only as a focused follow-up for
pure-Python modules or as a possible upstream target if we are willing to add
Cython/docstring support. MyST is worth using for authored-page conversion and
for preserving Sphinx directive semantics during migration, but not as the API
extraction engine.

## Primary Sources Checked

- `sphinx-autodoc2-fern` PyPI:
  <https://pypi.org/project/sphinx-autodoc2-fern/>
- `sphinx-autodoc2` quickstart and configuration:
  <https://sphinx-autodoc2.readthedocs.io/en/latest/quickstart.html>
- MyST parser intro and roles/directives:
  <https://myst-parser.readthedocs.io/en/latest/intro.html>
  <https://myst-parser.readthedocs.io/en/latest/syntax/roles-and-directives.html>
- MyST source-code/API guidance:
  <https://myst-parser.readthedocs.io/en/stable/syntax/code_and_apis.html>
- Sphinx autodoc, doctest, and intersphinx docs:
  <https://www.sphinx-doc.org/en/master/usage/extensions/autodoc.html>
  <https://www.sphinx-doc.org/en/master/usage/extensions/doctest.html>
  <https://www.sphinx-doc.org/en/master/usage/extensions/intersphinx.html>
- numpydoc style guide:
  <https://numpydoc.readthedocs.io/en/latest/format.html>
- Doxygen, Breathe, and Exhale docs:
  <https://www.doxygen.nl/manual/output.html>
  <https://www.breathe-doc.org/>
  <https://exhale.readthedocs.io/en/latest/overview.html>
