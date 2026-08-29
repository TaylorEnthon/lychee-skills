param(
    [string]$ClaudeHome
)

$ErrorActionPreference = "Stop"
$SkillDir = if ($ClaudeHome) {
    Join-Path $ClaudeHome "skills\tts-lychee"
} else {
    Split-Path -Parent $MyInvocation.MyCommand.Path
}
$Launcher = Join-Path $SkillDir "scripts\run.ps1"

if (-not (Test-Path -LiteralPath $Launcher)) {
    Write-Host "tts-lychee is not installed at: $SkillDir"
    exit 1
}

& $Launcher --doctor
exit $LASTEXITCODE
