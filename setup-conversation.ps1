[CmdletBinding()]
param([switch]$InstallPrerequisites, [string]$DataDir = '')
. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess
if (-not $DataDir) { $DataDir = Join-Path $PSScriptRoot '.motion-lab' }
$Checks = Get-LabPrerequisites
if ($InstallPrerequisites) {
    Install-LabPrerequisites -Checks $Checks -ApplicationOnly
    Initialize-LabProcess
    $Checks = Get-LabPrerequisites
}
$Missing = @('Python312x64', 'Git', 'Node', 'Npm', 'FFmpeg' | Where-Object { -not $Checks[$_] })
if ($Missing.Count -gt 0) { throw ('Missing application tools: ' + ($Missing -join ', ') + '. Add -InstallPrerequisites.') }
Invoke-LabPython -PythonInfo (Find-LabPython) -Arguments @((Join-Path $PSScriptRoot 'scripts\setup_conversation.py'), '--data-dir', $DataDir)
