Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Update-LabPath {
    $env:Path = [Environment]::GetEnvironmentVariable('Path', 'Machine') + ';' +
                [Environment]::GetEnvironmentVariable('Path', 'User') + ';' + $env:Path
}

function Find-LabPython {
    $Launcher = Get-Command py.exe -ErrorAction SilentlyContinue
    if ($Launcher) {
        try {
            & $Launcher.Source -3.12 -c 'import sys; assert sys.maxsize > 2**32' 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Program = $Launcher.Source; Prefix = @('-3.12') } }
        } catch { }
    }
    $PythonCommand = Get-Command python.exe -ErrorAction SilentlyContinue
    if ($PythonCommand) {
        try {
            & $PythonCommand.Source -c 'import sys; assert sys.version_info[:2] == (3,12) and sys.maxsize > 2**32' 2>$null
            if ($LASTEXITCODE -eq 0) { return @{ Program = $PythonCommand.Source; Prefix = @() } }
        } catch { }
    }
    return $null
}

function Find-LabVisualStudio {
    $VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
    if (Test-Path $VsWhere) {
        $Location = & $VsWhere -latest -products '*' -version '[17.0,18.0)' `
            -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
        if ($LASTEXITCODE -eq 0 -and $Location) { return $Location.Trim() }
    }
    return $null
}

function Test-LabNode {
    $NodeCommand = Get-Command node.exe -ErrorAction SilentlyContinue
    if (-not $NodeCommand) { return $false }
    try {
        $NodeVersion = & $NodeCommand.Source --version
        return ($LASTEXITCODE -eq 0 -and [version]$NodeVersion.Trim().TrimStart('v') -ge [version]'20.6.0')
    } catch { return $false }
}

function Get-LabPrerequisites {
    return [ordered]@{
        Python312x64 = [bool](Find-LabPython)
        Git = [bool](Get-Command git.exe -ErrorAction SilentlyContinue)
        Node = [bool](Test-LabNode)
        Npm = [bool](Get-Command npm.cmd -ErrorAction SilentlyContinue)
        FFmpeg = [bool](Get-Command ffmpeg.exe -ErrorAction SilentlyContinue)
        VisualStudio2022Cpp = [bool](Find-LabVisualStudio)
        NvidiaDriver = [bool](Get-Command nvidia-smi.exe -ErrorAction SilentlyContinue)
    }
}

function Install-LabPrerequisites {
    param($Checks, [switch]$ApplicationOnly)
    if (-not (Get-Command winget.exe -ErrorAction SilentlyContinue)) {
        throw 'winget is unavailable. See docs/windows_lab.md for manual prerequisite installation.'
    }
    $Packages = @()
    if (-not $Checks.Python312x64) { $Packages += 'Python.Python.3.12' }
    if (-not $Checks.Git) { $Packages += 'Git.Git' }
    if (-not $Checks.Node -or -not $Checks.Npm) { $Packages += 'OpenJS.NodeJS.LTS' }
    if (-not $Checks.FFmpeg) { $Packages += 'Gyan.FFmpeg' }
    foreach ($Package in $Packages) {
        Write-Host "Installing prerequisite: $Package"
        & winget.exe install --id $Package --exact --source winget
        if ($LASTEXITCODE -ne 0) { throw "winget failed for $Package. Restart PowerShell after resolving the installer." }
    }
    if (-not $ApplicationOnly -and -not $Checks.VisualStudio2022Cpp) {
        Write-Host 'Installing Visual Studio 2022 C++ Build Tools. Windows may request administrator approval.'
        & winget.exe install --id Microsoft.VisualStudio.2022.BuildTools --exact --source winget `
            --override '--wait --passive --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended'
        if ($LASTEXITCODE -ne 0) { throw 'C++ Build Tools installation failed; inspect the installer and restart PowerShell.' }
    }
    Update-LabPath
}

function Initialize-LabProcess {
    [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
    $global:OutputEncoding = [Console]::OutputEncoding
    $env:PYTHONUTF8 = '1'
    $env:PYTHONIOENCODING = 'utf-8'
    $env:PYTHON_MANAGER_AUTOMATIC_INSTALL = '0'
    # Select the checked MSVC toolchain instead of an unrelated MinGW on PATH.
    if (Find-LabVisualStudio) { $env:CMAKE_GENERATOR = 'Visual Studio 17 2022' }
}

function Invoke-LabPython {
    param($PythonInfo, [string[]]$Arguments)
    $CommandArguments = @($PythonInfo.Prefix) + $Arguments
    & $PythonInfo.Program @CommandArguments
    if ($LASTEXITCODE -ne 0) { throw "Motion Lab exited with code $LASTEXITCODE. See .motion-lab\logs\lab-setup.log if setup was started." }
}
