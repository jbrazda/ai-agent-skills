# ai-agent-skills

Reusable [Agent Skills](https://agentskills.io) for internal engineering
workflows, shareable across repositories and across AI coding agents
(GitHub Copilot CLI, Claude Code, Cursor, and any other harness that
implements the Agent Skills open standard).

A skill is a `SKILL.md` file (plus optional scripts/references/assets)
that an agent loads on demand. This repo is both:

- A **plugin** you can install directly (`copilot plugin install`,
  Claude Code `/plugin install`, Cursor Plugins).
- A plain **skills directory** you can clone and point any
  spec-compliant agent at, with no plugin manager involved.

## Skills in this repo

| Skill | Description |
| --- | --- |
| [`iics-doc-gen`](skills/iics-doc-gen/SKILL.md) | Generate/refresh Markdown documentation for Informatica IICS `PROCESS.xml`/`TASKFLOW.xml` assets. A script extracts structure (interface, step graph, dependencies, short mappings) mechanically; the model only writes the overview and summaries for XQuery expressions over 3 lines. See [docs/INSTALL.md](docs/INSTALL.md) for required tooling and platform notes (WSL vs. native Windows). |

## Install

### GitHub Copilot CLI

```bash
# One-time: install this repo as a plugin
copilot plugin install jbrazda/ai-agent-skills

# or, without the plugin system: register the skills directory directly
copilot skill add ~/path/to/ai-agent-skills/skills
```

Project-local install (checked into a specific repo instead of personal
config): clone this repo, then

```bash
copilot skill add --project ./ai-agent-skills/skills/iics-doc-gen/SKILL.md
```

or simply copy `skills/iics-doc-gen/` into that repo's `.github/skills/`
directory, which Copilot CLI auto-discovers.

### Claude Code

```text
/plugin marketplace add jbrazda/ai-agent-skills
/plugin install ai-agent-skills@ai-agent-skills
```

or, for a single project, copy `skills/iics-doc-gen/` into that project's
`.claude/skills/` directory.

### Cursor

Settings → Plugins → search `ai-agent-skills` once published to the
Cursor Marketplace, or add this repo as a Git plugin source directly from
Cursor settings (see `.cursor-plugin/plugin.json`).

### Any other spec-compliant agent

Clone this repo and point the agent at the `skills/` directory, or copy a
single skill folder (e.g. `skills/iics-doc-gen/`) wherever that agent
looks for project/user skills. Nothing here depends on a specific
harness - see [agentskills.io/specification](https://agentskills.io/specification).

## Updating

```bash
copilot plugin update ai-agent-skills   # Copilot CLI
/plugin update ai-agent-skills          # Claude Code
```

Or `git pull` if you installed by cloning/symlinking directly.

## Repository layout

```text
ai-agent-skills/
├── plugin.json                  # root plugin manifest (owner/repo install)
├── .claude-plugin/
│   ├── plugin.json              # Claude Code plugin manifest
│   └── marketplace.json         # lets this repo register itself as a marketplace
├── .plugin/plugin.json          # GitHub Copilot CLI / VS Code plugin manifest
├── .cursor-plugin/plugin.json   # Cursor plugin manifest
├── skills/
│   └── iics-doc-gen/            # one skill = one directory, spec-compliant
│       ├── SKILL.md
│       ├── scripts/
│       └── assets/
├── docs/
│   └── INSTALL.md               # dependencies, WSL/Windows portability
├── LICENSE                      # Apache-2.0
└── NOTICE
```

Each plugin manifest is a duplicate of the same content under the path
each harness looks for by convention (this mirrors how multi-harness
plugins such as `microsoft/azure-skills` are structured) - edit
`plugin.json` at the root and copy it to the other three locations when
metadata changes.

## Adding a new skill

1. `mkdir -p skills/<skill-name>/scripts`
2. Write `skills/<skill-name>/SKILL.md` with valid frontmatter (`name`
   must match the directory name, lowercase+hyphens; `description` states
   what it does and when to use it). See the
   [Agent Skills specification](https://agentskills.io/specification).
3. Reference any bundled scripts with **relative paths** from the skill
   directory (`scripts/foo.py`), never absolute paths - the same skill
   folder is installed at different absolute paths depending on harness
   and install scope (personal vs. project vs. plugin).
4. Document platform/runtime dependencies in the `compatibility`
   frontmatter field and in `docs/INSTALL.md`.
5. Update the table above and bump `version` in the four `plugin.json`
   copies.

## License

Apache-2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE).
