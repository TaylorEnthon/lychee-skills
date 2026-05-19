param(
    [string]$ClaudeHome = "$env:USERPROFILE\.claude"
)

$ErrorActionPreference = "Stop"
$SkillDir = Join-Path $ClaudeHome "skills\tts-lychee"
$Client = Join-Path $SkillDir "scripts\tts_client.py"

if (-not (Test-Path -LiteralPath $Client)) {
    Write-Host "tts-lychee is not installed at: $SkillDir"
    exit 1
}

$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) {
    $python = Get-Command python3 -ErrorAction SilentlyContinue
}
if (-not $python) {
    Write-Host "Python not found. Install Python 3.8+ and rerun this doctor."
    exit 1
}

& $python.Source $Client --doctor
exit $LASTEXITCODE