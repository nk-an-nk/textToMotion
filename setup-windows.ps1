[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$InstallPrerequisites,
    [switch]$AcceptModelLicense,
    [switch]$Start,
    [string]$DataDir = '',
    [string]$ConfigPath = ''
)

. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess
if (-not $DataDir) { $DataDir = Join-Path $PSScriptRoot '.motion-lab' }
if (-not $ConfigPath) { $ConfigPath = Join-Path $PSScriptRoot 'configs\lab-windows.json' }
$Checks = Get-LabPrerequisites
if ($CheckOnly) {
    $Checks | ConvertTo-Json
    if ($Checks.NvidiaDriver) {
        & nvidia-smi.exe --query-gpu=name,memory.total,driver_version --format=csv,noheader,nounits
    }
    Write-Host 'Check only: no installations, downloads, or environment creation.'
    return
}
if (-not $AcceptModelLicense) {
    throw 'Read reports/licenses.md and the NVIDIA model agreement, then add -AcceptModelLicense. Llama account approval is separate.'
}
if ($InstallPrerequisites) {
    Install-LabPrerequisites -Checks $Checks
    Initialize-LabProcess
    $Checks = Get-LabPrerequisites
}
$Missing = @($Checks.Keys | Where-Object { -not $Checks[$_] })
if ($Missing.Count -gt 0) {
    throw ('Missing prerequisites: ' + ($Missing -join ', ') +
           '. Use -InstallPrerequisites for supported tools. NVIDIA drivers must be installed by the PC administrator.')
}
$PythonInfo = Find-LabPython
$SetupArguments = @((Join-Path $PSScriptRoot 'scripts\setup_lab.py'), 'setup',
                    '--profile', $ConfigPath, '--data-dir', $DataDir, '--accept-model-license')
Invoke-LabPython -PythonInfo $PythonInfo -Arguments $SetupArguments
if ($Start) {
    Invoke-LabPython -PythonInfo $PythonInfo -Arguments @((Join-Path $PSScriptRoot 'scripts\setup_lab.py'),
        'start', '--profile', $ConfigPath, '--data-dir', $DataDir)
}
