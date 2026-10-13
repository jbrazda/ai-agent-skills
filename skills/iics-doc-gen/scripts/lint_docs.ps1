<#
.SYNOPSIS
  Validate generated IICS asset docs on native Windows (no WSL/Bash required).

.DESCRIPTION
  Mirrors scripts/lint_docs.sh: normalizes literal tabs in fenced code
  blocks to spaces, runs `prettier --prose-wrap preserve --write`, then
  `markdownlint-cli2`. Requires Node.js 18+ (npx) on PATH.

.PARAMETER Files
  One or more Markdown file paths to lint.

.EXAMPLE
  powershell -File scripts/lint_docs.ps1 doc/Asset.md

.EXAMPLE
  pwsh ./scripts/lint_docs.ps1 doc/Asset1.md doc/Asset2.md
#>
param(
    [Parameter(Mandatory = $true, ValueFromRemainingArguments = $true)]
    [string[]]$Files
)

$ErrorActionPreference = 'Stop'

if (-not $Files -or $Files.Count -eq 0) {
    Write-Error "usage: lint_docs.ps1 <file.md> [more.md ...]"
    exit 2
}

foreach ($f in $Files) {
    if (-not (Test-Path $f)) {
        Write-Error "file not found: $f"
        exit 1
    }
    $text = Get-Content -Raw -Path $f
    if ($text -match "`t") {
        $text = $text -replace "`t", '    '
        Set-Content -Path $f -Value $text -NoNewline
    }
}

npx --yes prettier --prose-wrap preserve --write @Files
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

npx --yes markdownlint-cli2 @Files
exit $LASTEXITCODE
