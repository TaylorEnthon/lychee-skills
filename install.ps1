param(
    [ValidateSet("claude", "codex", "agents", "all")]
    [string]$Target = "claude",
    [string]$ClaudeHome = "$env:USERPROFILE\.claude",
    [string]$CodexHome = $(if ($env:CODEX_HOME) { $env:CODEX_HOME } else { "$env:USERPROFILE\.codex" }),
    [string]$AgentsHome = $(if ($env:AGENTS_HOME) { $env:AGENTS_HOME } else { "$env:USERPROFILE\.agents" })
)

$ErrorActionPreference = "Stop"
$SourceDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$SkillSource = Join-Path $SourceDir "skills\tts-lychee"
$CommandSourceDir = Join-Path $SourceDir "commands"

$RequiredSourcePaths = @(
    (Join-Path $SkillSource "SKILL.md"),
    (Join-Path $SkillSource "doctor.ps1"),
    (Join-Path $SkillSource "doctor.sh"),
    (Join-Path $SkillSource "scripts"),
    (Join-Path $SkillSource "requirements.txt"),
    (Join-Path $SkillSource "requirements-playback.txt"),
    (Join-Path $CommandSourceDir "tts-lychee-search-voices.md"),
    (Join-Path $CommandSourceDir "tts-lychee-list-voices.md")
)

foreach ($RequiredSourcePath in $RequiredSourcePaths) {
    if (-not (Test-Path -LiteralPath $RequiredSourcePath)) {
        throw "Required source path is missing: $RequiredSourcePath"
    }
}

function Install-LycheeSkill {
    param(
        [Parameter(Mandatory = $true)][string]$AgentHome,
        [Parameter(Mandatory = $true)][bool]$InstallCommands
    )

    $SkillTarget = Join-Path $AgentHome "skills\tts-lychee"
    New-Item -ItemType Directory -Path $SkillTarget -Force | Out-Null

    Copy-Item -LiteralPath (Join-Path $SkillSource "SKILL.md") -Destination (Join-Path $SkillTarget "SKILL.md") -Force
    Copy-Item -LiteralPath (Join-Path $SkillSource "doctor.ps1") -Destination (Join-Path $SkillTarget "doctor.ps1") -Force
    Copy-Item -LiteralPath (Join-Path $SkillSource "doctor.sh") -Destination (Join-Path $SkillTarget "doctor.sh") -Force
    Copy-Item -LiteralPath (Join-Path $SkillSource "scripts") -Destination $SkillTarget -Recurse -Force
    Copy-Item -LiteralPath (Join-Path $SkillSource "requirements.txt") -Destination (Join-Path $SkillTarget "requirements.txt") -Force
    Copy-Item -LiteralPath (Join-Path $SkillSource "requirements-playback.txt") -Destination (Join-Path $SkillTarget "requirements-playback.txt") -Force

    $LegacyDataTarget = Join-Path $SkillTarget "data"
    if (Test-Path -LiteralPath $LegacyDataTarget) {
        Remove-Item -LiteralPath $LegacyDataTarget -Recurse -Force
        Write-Host "Removed legacy bundled voice data: $LegacyDataTarget"
    }

    if ($InstallCommands) {
        $CommandTargetDir = Join-Path $AgentHome "commands"
        New-Item -ItemType Directory -Path $CommandTargetDir -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $CommandSourceDir "tts-lychee-list-voices.md") -Destination (Join-Path $CommandTargetDir "tts-lychee-list-voices.md") -Force
        Copy-Item -LiteralPath (Join-Path $CommandSourceDir "tts-lychee-search-voices.md") -Destination (Join-Path $CommandTargetDir "tts-lychee-search-voices.md") -Force
        foreach ($LegacyCommandName in @("tts-lychee-preview-match.md", "tts-lychee.md")) {
            $LegacyCommand = Join-Path $CommandTargetDir $LegacyCommandName
            if (Test-Path -LiteralPath $LegacyCommand) {
                Remove-Item -LiteralPath $LegacyCommand -Force
            }
        }
    }

    Write-Host "Installed skill: $SkillTarget"
    Write-Host "Install core dependencies: & `"$(Join-Path $SkillTarget 'scripts\run.ps1')`" --install-deps"
    Write-Host "Optional live playback: & `"$(Join-Path $SkillTarget 'scripts\run.ps1')`" --install-playback"
}

if ($Target -eq "claude" -or $Target -eq "all") {
    Install-LycheeSkill -AgentHome $ClaudeHome -InstallCommands $true
}
if ($Target -eq "codex" -or $Target -eq "all") {
    Install-LycheeSkill -AgentHome $CodexHome -InstallCommands $false
}
if ($Target -eq "agents" -or $Target -eq "all") {
    Install-LycheeSkill -AgentHome $AgentsHome -InstallCommands $false
}

Write-Host "Set TTS_API_KEY, restart the target Agent, then ask it to synthesize or play speech."
