# Installation, dependencies, and platform portability

This covers what each skill in this repo actually needs at runtime, and
how that differs between Linux/macOS, WSL, and native Windows. As of this
writing the only skill is `iics-doc-gen`; add a section here for each new
skill that has non-trivial runtime requirements.

## `iics-doc-gen`

### Dependencies

| Tool | Required for | Minimum version | Notes |
| --- | --- | --- | --- |
| Python 3 | `extract_iics_asset.py`, `render_iics_doc.py` | 3.8+ | Standard library only (`argparse`, `json`, `re`, `xml.etree.ElementTree`, `pathlib`). No `pip install` needed. |
| Node.js + npx | `lint_docs.sh` / `lint_docs.ps1` (lint step only) | 18+ | Fetches `prettier` and `markdownlint-cli2` on demand via `npx --yes`; no global npm install required, but needs network access the first time (npx caches afterward). |
| Bash | `lint_docs.sh` | any POSIX shell | Linux, macOS, WSL, or Git Bash. Not available on plain `cmd.exe`/PowerShell without WSL or Git Bash. |
| PowerShell | `lint_docs.ps1` | 5.1+ (Windows PowerShell) or PowerShell 7+ (`pwsh`) | Native Windows alternative to `lint_docs.sh` - does the same thing. |

The two Python scripts have **zero OS-specific code**: no shelling out,
no path separators hardcoded, no POSIX-only stdlib calls. They run
identically under CPython on Linux, macOS, WSL, or native Windows.

### Is this skill portable?

**Yes.** Specifically:

- **Linux / macOS**: works out of the box with any Python 3.8+ and
  Node.js 18+ on `PATH`. Use `scripts/lint_docs.sh`.
- **WSL (Windows Subsystem for Linux)**: identical to Linux - install
  Python3 and Node.js inside the WSL distro as you would on any Linux
  box, then use `scripts/lint_docs.sh`. This is the path of least
  friction if your agent harness (e.g. Copilot CLI, Claude Code) is
  itself running inside WSL, which is the common setup on Windows.
- **Native Windows (no WSL)**: the extraction/render scripts run fine
  under a native Windows Python install (`python scripts\extract_iics_asset.py ...`).
  For the lint step, use `scripts\lint_docs.ps1` instead of the `.sh`
  script (plain `cmd.exe`/PowerShell cannot run Bash scripts without Git
  Bash or WSL installed). Both lint scripts are functionally identical.

### Setup by platform

#### Linux / macOS

```bash
python3 --version   # need 3.8+
node --version       # need 18+; npx ships with Node
```

If missing: use your distro's package manager (`apt`, `dnf`, `brew`,
etc.) or [nodejs.org](https://nodejs.org) / [python.org](https://python.org)
installers.

#### WSL

Same as Linux, inside your WSL distro:

```bash
sudo apt update && sudo apt install -y python3 nodejs npm
```

(Ubuntu's `apt` Node.js package can be old; if you need Node 18+
specifically and `apt` gives you something older, use
[NodeSource](https://github.com/nodesource/distributions) or
[nvm](https://github.com/nvm-sh/nvm).)

#### Native Windows

1. Install Python 3.8+ from the [Microsoft Store](https://apps.microsoft.com/detail/9ncvdn91xzqp)
   or [python.org](https://python.org) (check "Add python.exe to PATH"
   during setup).
2. Install Node.js 18+ LTS from [nodejs.org](https://nodejs.org) (`npx`
   is included).
3. Run the extraction/render steps with `python` (not `python3` - the
   Windows installer does not create a `python3` alias by default):

   ```powershell
   python scripts\extract_iics_asset.py path\to\Asset.PROCESS.xml -o facts.json --brief-out brief.json
   python scripts\render_iics_doc.py facts.json annotations.json -o Asset.md
   ```

4. Lint with the PowerShell script:

   ```powershell
   powershell -File scripts\lint_docs.ps1 Asset.md
   ```

   If script execution is blocked by your execution policy, run once per
   session:

   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   ```

   (This only affects the current PowerShell process; it does not change
   your system-wide policy.)

### Known platform gotchas

- **`python3` vs `python`**: Linux/macOS/WSL conventionally expose
  `python3`; native Windows installers conventionally expose `python`
  (and sometimes `py`). The SKILL.md examples use `python3`; swap to
  `python` on native Windows.
- **Line endings**: the scripts write Unix (`\n`) line endings
  regardless of platform; `prettier`/`markdownlint-cli2` and Git's
  `core.autocrlf` handle this transparently in practice, but if you see
  spurious whole-file diffs after lint, check your repo's
  `.gitattributes`/`core.autocrlf` settings rather than the scripts.
- **Hard tabs**: both lint scripts normalize literal tab characters
  (which can appear in XQuery copied verbatim from the source XML) to
  4 spaces before linting, so `MD010` never needs to be disabled in your
  project's markdownlint config.
- **No `MD013` config**: if the target docs directory has no
  `.markdownlint.jsonc`, the default 80-character line-length rule will
  flag nearly every generated table/diagram line. Copy
  [`skills/iics-doc-gen/assets/markdownlint.jsonc.sample`](../skills/iics-doc-gen/assets/markdownlint.jsonc.sample)
  in as `.markdownlint.jsonc` (or merge `"MD013": false` into an existing
  config) before linting generated docs.
- **Network access**: only the first `npx` invocation for `prettier`/
  `markdownlint-cli2` needs the internet (to download and cache the
  packages). The Python extraction/render steps never need network
  access. If you're in an offline/air-gapped environment, pre-install
  `prettier` and `markdownlint-cli2` globally (`npm install -g prettier
  markdownlint-cli2`) and the scripts will use the cached `npx` resolution
  without re-fetching.
