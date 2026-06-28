$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
npx -y skills@latest add "$Root\biznews-jayant" -g -y
