[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess

$TokenPath = Join-Path $PSScriptRoot 'config\huggingface.md'
if (-not (Test-Path -LiteralPath $TokenPath)) {
    $TokenPath = Join-Path $PSScriptRoot 'configs\huggingface.md'
}
$TokenText = [IO.File]::ReadAllText($TokenPath).Replace('\_', '_')
$TokenMatch = [regex]::Match($TokenText, 'hf_[A-Za-z0-9]+')
if (-not $TokenMatch.Success) { throw 'Hugging Face token was not found in the configured file.' }

$PythonPath = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
if (-not (Test-Path -LiteralPath $PythonPath)) { throw 'Python 3.12 was not found.' }
$PreviousToken = [Environment]::GetEnvironmentVariable('HF_TOKEN', 'Process')
try {
    $env:HF_TOKEN = $TokenMatch.Value
    & $PythonPath (Join-Path $PSScriptRoot 'scripts\setup_lab.py') setup `
        --profile (Join-Path $PSScriptRoot 'configs\lab-windows.json') `
        --data-dir (Join-Path $PSScriptRoot '.motion-lab') --accept-model-license
    if ($LASTEXITCODE -ne 0) { throw 'Setup failed; see .motion-lab\logs\lab-setup.log.' }
} finally {
    [Environment]::SetEnvironmentVariable('HF_TOKEN', $PreviousToken, 'Process')
    $TokenText = $null
    $TokenMatch = $null
    $PreviousToken = $null
}
