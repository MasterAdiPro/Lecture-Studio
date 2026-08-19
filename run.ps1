$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
if (-not (Test-Path '.venv\Scripts\python.exe')) { throw 'Project environment is missing. Create it with: python -m venv .venv' }
& '.venv\Scripts\python.exe' app.py

