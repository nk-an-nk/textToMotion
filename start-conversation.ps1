[CmdletBinding()]
param(
    [switch]$EnableRealtime,
    [double]$BudgetUsd = 0,
    [int]$SessionSeconds = 60,
    [switch]$TextFirst,
    [string]$DataDir = '',
    [int]$Port = 8765
)
. (Join-Path $PSScriptRoot 'scripts\windows_common.ps1')
Initialize-LabProcess
if (-not $DataDir) { $DataDir = Join-Path $PSScriptRoot '.motion-lab' }
$AppPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $AppPython)) { throw 'Application venv missing. Run setup-conversation.ps1 first.' }
$EnteredApiKey = $false
if ($Port -lt 1024 -or $Port -gt 65535) { throw 'Port must be 1024-65535.' }
if ($EnableRealtime) {
    if ($BudgetUsd -lt 1) { throw 'Specify -BudgetUsd >= 1 to authorize API usage allowances.' }
    if (-not $env:OPENAI_API_KEY) {
        $SecureApiKey = Read-Host 'OpenAI API key (hidden; process only)' -AsSecureString
        $KeyPointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($SecureApiKey)
        try { $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($KeyPointer) }
        finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($KeyPointer) }
        $EnteredApiKey = $true
    }
    $env:OPENAI_REALTIME_ENABLED = '1'
    $env:OPENAI_API_BUDGET_USD = $BudgetUsd.ToString([Globalization.CultureInfo]::InvariantCulture)
} else { $env:OPENAI_REALTIME_ENABLED = '0' }
$env:OPENAI_TEXT_FIRST_ENABLED = if ($TextFirst) { '1' } else { '0' }
$env:OPENAI_SESSION_SECONDS = [Math]::Min(180, [Math]::Max(10, $SessionSeconds)).ToString()
$env:MOTION_LAB_DATA = $DataDir
$env:MOTION_LAB_OUTPUTS = Join-Path $DataDir 'outputs'
$env:HF_HOME = Join-Path $DataDir 'hf-cache'
$env:HF_HUB_OFFLINE = '1'
$env:TRANSFORMERS_OFFLINE = '1'
$env:MPLCONFIGDIR = Join-Path $DataDir 'matplotlib-cache'
try {
    Write-Host "Conversation: http://127.0.0.1:$Port/conversation"
    & $AppPython -m uvicorn app.main:app --host 127.0.0.1 --port $Port --app-dir $PSScriptRoot
    if ($LASTEXITCODE -ne 0) { throw 'Conversation application failed to start.' }
} finally { if ($EnteredApiKey) { Remove-Item Env:OPENAI_API_KEY -ErrorAction SilentlyContinue } }
