param(
    [string]$ClaudeHome = "$env:USERPROFILE\.claude"
)

$ErrorActionPreference = "Stop"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSource = Join-Path $SourceDir "skills\tts-lychee"
$SkillTarget = Join-Path $ClaudeHome "skills\tts-lychee"
$CommandSourceDir = Join-Path $SourceDir "commands"
$CommandTargetDir = Join-Path $ClaudeHome "commands"
$LegacyCommand = Join-Path $CommandTargetDir "tts-lychee.md"

$RequiredSourcePaths = @(
    (Join-Path $SkillSource "SKILL.md"),
    (Join-Path $SkillSource "doctor.ps1"),
    (Join-Path $SkillSource "doctor.sh"),
    (Join-Path $SkillSource "scripts"),
    (Join-Path $SkillSource "data"),
    (Join-Path $CommandSourceDir "tts-lychee-preview-match.md"),
    (Join-Path $CommandSourceDir "tts-lychee-list-voices.md")
)

foreach ($RequiredSourcePath in $RequiredSourcePaths) {
    if (-not (Test-Path -LiteralPath $RequiredSourcePath)) {
        throw "Required source path is missing: $RequiredSourcePath"
    }
}

New-Item -ItemType Directory -Path $SkillTarget -Force | Out-Null
New-Item -ItemType Directory -Path $CommandTargetDir -Force | Out-Null

Copy-Item -LiteralPath (Join-Path $SkillSource "SKILL.md") -Destination (Join-Path $SkillTarget "SKILL.md") -Force
Copy-Item -LiteralPath (Join-Path $SkillSource "doctor.ps1") -Destination (Join-Path $SkillTarget "doctor.ps1") -Force
Copy-Item -LiteralPath (Join-Path $SkillSource "doctor.sh") -Destination (Join-Path $SkillTarget "doctor.sh") -Force
Copy-Item -LiteralPath (Join-Path $SkillSource "scripts") -Destination $SkillTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $SkillSource "data") -Destination $SkillTarget -Recurse -Force
Copy-Item -LiteralPath (Join-Path $CommandSourceDir "tts-lychee-preview-match.md") -Destination (Join-Path $CommandTargetDir "tts-lychee-preview-match.md") -Force
Copy-Item -LiteralPath (Join-Path $CommandSourceDir "tts-lychee-list-voices.md") -Destination (Join-Path $CommandTargetDir "tts-lychee-list-voices.md") -Force

if (Test-Path -LiteralPath $LegacyCommand) {
    Remove-Item -LiteralPath $LegacyCommand -Force
    Write-Host "Removed legacy duplicate slash command: $LegacyCommand"
}

Write-Host "Installed skill: $SkillTarget"
Write-Host "Restart Claude Code, then use: /tts-lychee <text to synthesize>"
Write-Host "Set TTS_API_KEY before use. Get an API Key from https://shanhaistudio.lycheeai.com.cn/"
