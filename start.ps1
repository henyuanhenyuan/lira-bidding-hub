$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
python -m pip install --quiet -r requirements.txt
$port = if ($env:LIRA_PORT) { $env:LIRA_PORT } else { "8011" }
python -m uvicorn app.main:app --host 127.0.0.1 --port $port
