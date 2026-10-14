[CmdletBinding()]
param(
    [string]$DataDir = '',
    [string]$ConfigPath = ''
)

. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess
if (-not $DataDir) { $DataDir = Join-Path $PSScriptRoot '.motion-lab' }
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'configs\lab-windows.json' }
$PythonInfo = Find-LabPython
if (-not $PythonInfo) { throw 'Python 3.12 x64 is required. Run setup-windows.ps1 first.' }
Invoke-LabPython -PythonInfo $PythonInfo -Arguments @((Join-Path $PSScriptRoot 'scripts\setup_lab.py'),
    'start', '--profile', $ConfigPath, '--data-dir', $DataDir)
