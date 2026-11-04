# One-shot quality gate: lint (autofix), format check, re-lint, test.
# The format step only CHECKS. A disagreement means the caller's own edit is
# off-style — rewriting unrelated files behind their back is what a gate must
# not do.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)

ruff check --fix pot tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff format --check pot tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
ruff check pot tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
python -m pytest -q
exit $LASTEXITCODE
