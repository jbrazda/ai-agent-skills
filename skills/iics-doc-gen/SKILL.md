---
name: iics-doc-gen
description: Generate or refresh Markdown documentation for an IICS asset (PROCESS.xml / TASKFLOW.xml export) in a token-efficient way - a script extracts all structural facts (interface, step graph, dependencies, mapping table) and only hands the model the handful of XQuery expressions that actually need a prose summary. Use whenever asked to document, update, or regenerate docs for IICS processes, subprocesses, or taskflows (e.g. "document this IICS asset", "update the Corvel docs", "regenerate asset documentation from the XML", "write a doc for this PROCESS.xml").
license: Apache-2.0
compatibility: Requires Python 3.8+ (stdlib only) to run the scripts; Node.js 18+ with npx (for prettier and markdownlint-cli2) only if you use the lint step. No network access required except the one-time npx package fetch.
metadata:
  author: jbrazda
  version: "1.0.0"
  homepage: https://github.com/jbrazda/ai-agent-skills
---

# IICS asset documentation generator

Documenting an IICS asset from its exported XML is 95% mechanical
(interface tables, step graph, dependency lists, short field-copy mappings)
and 5% judgment (what does this asset do, and what is this specific
20-line XQuery block actually trying to achieve). Reading the full XML
into the model for every asset wastes tokens on that mechanical 95%. This
skill splits the work: a script does the extraction and rendering; the
model writes only the prose that requires understanding.

## When to use this

- "Document this IICS process/taskflow"
- "Regenerate/update asset docs from the XML" (source changed since the doc
  was last generated - compare `ModificationDate` in the XML to the doc's
  "Last modified" line to detect staleness)
- Restructuring existing docs' mapping tables into short-table +
  Detailed-Mapping-Logic form (this skill's renderer already does that split
  automatically at a 3-line threshold)

## Workflow

```text
Asset.PROCESS.xml --extract--> facts.json (full, for the renderer)
                            \-> brief.json (small, for you to read)

you read brief.json, write annotations.json (overview + per-mapping summaries)

facts.json + annotations.json --render--> Asset.md

lint_docs.sh Asset.md   (prettier + markdownlint-cli2, 0 issues required)
```

All commands below are given as `scripts/<name>`, relative to this skill's
own directory (the directory this `SKILL.md` lives in). Run them from
there, or prefix with the skill's absolute path if your working directory
differs - do not assume any specific install location, the same skill
folder is used whether it was installed as a personal skill, a project
skill, or via a plugin.

### 1. Extract facts from the XML

```bash
python3 scripts/extract_iics_asset.py \
  path/to/Asset.PROCESS.xml \
  -o /tmp/facts.json \
  --brief-out /tmp/brief.json
```

(On native Windows without WSL, use `python` instead of `python3`.)

- `facts.json` is the full structured extraction (metadata, input/output
  fields, the complete step graph with links, every assignment operation
  split into short vs. long XQuery, invoked services/subflows, core
  process objects). This feeds the renderer - you do not need to read it.
- `brief.json` is the **only file you should load into context**. It has
  the asset name/description, the ordered list of step titles, the invoked
  services/subflows, and - critically - just the XQuery expressions longer
  than 3 lines (the `longMappings` array), each with its step name, target
  field, and the raw expression text. This is a large (often 80-90%)
  reduction versus reading the raw XML.
- `--long-threshold N` changes the line-count cutoff for "long" (default
  3).
- For a `.TASKFLOW.xml` the same script works; the root element is
  `<taskflow>` instead of `<process>` but the step/link schema is
  otherwise identical.

### 2. Write the annotations (the only model-authored content)

Produce a small JSON file:

```json
{
  "overview": "2-4 sentences in business terms: what this asset does and when it runs.",
  "<mappingKey1>": "1-2 sentence summary of what that specific long expression computes.",
  "<mappingKey2>": "...",
  "errorHandling": "optional: free text appended after the auto-generated fault table",
  "logging": "optional: free text appended after the auto-generated logging table",
  "configNotes": "optional: free text appended after the auto-generated config table"
}
```

- One entry per key in `brief.json`'s `longMappings[].key` (same keys as
  `facts.json`'s `needsSummary`), plus `"overview"`. Nothing else is
  required.
- Summarize *intent*, not syntax - do not restate the XQuery in prose.
- Skip `errorHandling`/`logging`/`configNotes` unless you have something
  non-obvious to add; the renderer always emits a sensible baseline for
  those sections from the step graph alone (fault branches, `Log *`-titled
  steps, config-prefix temp fields).

### 3. Render the Markdown

```bash
python3 scripts/render_iics_doc.py \
  /tmp/facts.json /tmp/annotations.json \
  -o doc/Asset.md \
  --referenced-docs doc/README.md
```

This writes the full doc with the standard section set, in order:

1. `# Title` + `[[_TOC_]]`
2. `## 📘 Overview` (your text + Last modified / Tags from the XML)
3. `## 🔧 Configuration Parameters` (auto, from temp fields with an
   `initialvalue` or a `config`-looking name)
4. `## ⚙️ Process Interface` - `### Input Fields` / `### Output Fields`
   tables (auto, from the XML `<input>`/`<output>`)
5. `## 🏗️ Process Diagram` - an ADO `:::mermaid flowchart TD` built from
   the actual step/link graph, plus a numbered `Execution path summary`
   (auto-generated per-step sentence; service calls, subprocess calls, and
   end-step HTTP status are named automatically)
6. `## 🧬 Data Models & Mapping` - `### Core process objects`,
   `### Mapping highlights` (short-form table, ≤3-line expressions only),
   and - only if any exist - `### Detailed Mapping Logic` with one
   `#### <Step Title> - <target field>` H4 per long expression, your summary,
   and a ` ```xml ` fenced verbatim block (not `xquery` - Azure DevOps wiki
   markdown does not apply XQuery syntax highlighting; adjust this if your
   target wiki does support it)
7. `## ⚠️ Error Handling & Troubleshooting` (auto: non-2xx end steps and
   branches whose container title matches fault/error/catch/exception)
8. `## 📜 Logging` (auto: steps titled `Log ...`)
9. `## 📎 Dependencies` - `### Invoked services` / `### Invoked
   subprocesses/taskflows` / `### Referenced process objects`
10. `## 🔖 Referenced Documents`

If a key is missing from your annotations file, the renderer still
produces a complete doc with a `_TODO: ..._` placeholder in that spot and
prints a warning - it never blocks on missing prose.

### 4. Lint

```bash
scripts/lint_docs.sh doc/Asset.md          # macOS / Linux / WSL
powershell -File scripts/lint_docs.ps1 doc/Asset.md   # native Windows
```

Normalizes any literal tabs copied into fenced blocks to spaces, then runs
`prettier --prose-wrap preserve --write` (fixes GFM table alignment) and
`markdownlint-cli2`. Must report 0 issues before you consider the doc
done. A project's own `.markdownlint.jsonc`/`.markdownlint-cli2.jsonc`
applies automatically - do not edit it to silence a warning this skill
produced; fix the renderer input (annotations) instead, or if it's a
pre-existing project convention, report it rather than overriding it.

If the target docs directory has **no** markdownlint config yet, the
default 80-character MD013 rule will flag nearly every table/diagram line
these docs generate. Copy [`assets/markdownlint.jsonc.sample`](assets/markdownlint.jsonc.sample)
in as `.markdownlint.jsonc` next to the generated docs (or merge its
`MD013: false` into an existing config) before linting.

## Known approximations to review

The renderer is mechanical and gets the structure right, but review these
before publishing:

- **Branch labels** in the mermaid diagram and execution summary come from
  the nearest enclosing `<container title="...">` (the switch/condition
  name), not a true-branch/false-branch label. Two sibling outcomes under
  the same exclusive container (e.g. a fault path and a success path) will
  show the same branch name. Rename them by hand if it's ambiguous (e.g.
  append "(fault)"/"(success)").
- **Error Handling / Logging sections** are heuristic (non-2xx end steps,
  container titles containing fault/error/catch, step titles starting with
  "Log"). If the asset's real error-handling logic doesn't match those
  patterns, add it via `annotations.errorHandling`/`logging` rather than
  editing the rendered Markdown directly, so a future re-run doesn't lose it.
- **Configuration Parameters** detection is a name/initial-value heuristic
  over temp fields; sanity-check the one or two rows it finds.
- **Mermaid/wiki conventions** here target Azure DevOps wikis (`:::mermaid`
  fence, `[[_TOC_]]`). If your target platform is plain GitHub/GitLab
  Markdown, change those two spots to a standard ` ```mermaid ` fence and
  drop the `[[_TOC_]]` line (most renderers auto-generate a TOC, or use a
  `<!-- TOC -->` tool instead).

## Re-running after the XML changes (staleness refresh)

Compare the doc's "Last modified" line to the XML's
`<ModifiedBy>`/`<ModificationDate>` (or `<types1:...>`/`<ns1:...>`
variants - the prefix differs per export). If the XML is newer, redo
steps 1-4 above; `facts.json` will reflect the current structure and any
previously-written annotation keys can be reused verbatim for mappings
that didn't change (diff `brief.json`'s `longMappings` against the
previous run to see which keys are new/changed/removed).

## Files

- `scripts/extract_iics_asset.py` - XML to `facts.json` + `brief.json`.
  No model calls; pure parsing. Namespace-agnostic (works regardless of
  the `types1:`/`ns1:` prefix used in a given export). Pure Python 3
  standard library - no pip install required.
- `scripts/render_iics_doc.py` - `facts.json` + `annotations.json` to the
  final Markdown doc. No model calls; pure templating. Pure Python 3
  standard library.
- `scripts/lint_docs.sh` / `scripts/lint_docs.ps1` - tab normalization +
  prettier + markdownlint-cli2 validation wrapper, for Unix-like shells
  and native Windows PowerShell respectively. See
  [`../../docs/INSTALL.md`](../../docs/INSTALL.md) for setup on WSL vs.
  native Windows.
