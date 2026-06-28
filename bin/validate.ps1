$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (Get-Command python -ErrorAction SilentlyContinue) {
    python "$Root\bin\validate.py"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    py -3 "$Root\bin\validate.py"
} else {
    throw "No Python executable found. Install Python 3.11+."
}
