[CmdletBinding()]
param(
    [ValidateSet('all','short','medium')][string]$Group = 'all',
    [string]$Models = 'ardy',
    [string]$DataDir = '',
    [string]$ConfigPath = ''
)

. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess
if (-not $DataDir) { $DataDir = Join-Path $PSScriptRoot '.motion-lab' }
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'configs\lab-windows.json' }
$Settings = Get-Content -Raw -LiteralPath $ConfigPath | ConvertFrom-Json
$AppPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $AppPython)) { throw 'Run setup-windows.ps1 first, then keep start-windows.ps1 running.' }
Invoke-LabPython -PythonInfo @{ Program = $AppPython; Prefix = @() } -Arguments @(
    (Join-Path $PSScriptRoot 'scripts\run_ardy_examples.py'),
    '--url', ('http://127.0.0.1:' + $Settings.port), '--group', $Group, '--models', $Models,
    '--output-dir', (Join-Path $DataDir 'batches'))
