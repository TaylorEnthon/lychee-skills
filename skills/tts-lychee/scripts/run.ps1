[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClientArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Client = Join-Path $ScriptDir "tts_client.py"
$UserHome = $HOME
if (-not $UserHome) {
    $UserHome = $env:USERPROFILE
}
if ($env:TTS_RUNTIME_HOME) {
    $RuntimeHome = $env:TTS_RUNTIME_HOME
} else {
    $RuntimeHome = Join-Path $UserHome ".lychee\tts-lychee\runtime"
}
$VenvDir = Join-Path $RuntimeHome "venv"

function Resolve-PythonRuntime {
    param(
        [string]$Name,
        [object[]]$Prefix = @()
    )
    $Command = Get-Command $Name -ErrorAction SilentlyContinue
    if (-not $Command) {
        return $null
    }
    $ProbeArgs = @($Prefix) + @(
        "-c",
        "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
    )
    try {
        & $Command.Source @ProbeArgs *> $null
        if ($LASTEXITCODE -eq 0) {
            return [pscustomobject]@{ Path = $Command.Source; Prefix = @($Prefix) }
        }
    } catch {
        return $null
    }
    return $null
}

function Find-SystemPythonRuntime {
    $Candidates = @(
        [pscustomobject]@{ Name = "python"; Prefix = @() },
        [pscustomobject]@{ Name = "py"; Prefix = @("-3") },
        [pscustomobject]@{ Name = "python3"; Prefix = @() }
    )
    foreach ($Candidate in $Candidates) {
        $Runtime = Resolve-PythonRuntime -Name $Candidate.Name -Prefix $Candidate.Prefix
        if ($Runtime) {
            return $Runtime
        }
    }
    return $null
}

$ExplicitRuntime = $false
$Runtime = $null
if ($env:TTS_PYTHON) {
    $Runtime = Resolve-PythonRuntime -Name $env:TTS_PYTHON
    if (-not $Runtime) {
        [Console]::Error.WriteLine(
            "TTS_PYTHON is not an executable Python 3.8+ runtime: $($env:TTS_PYTHON)"
        )
        exit 127
    }
    $ExplicitRuntime = $true
} else {
    $VenvCandidates = @(
        (Join-Path $VenvDir "Scripts\python.exe"),
        (Join-Path $VenvDir "bin\python")
    )
    foreach ($Candidate in $VenvCandidates) {
        $Runtime = Resolve-PythonRuntime -Name $Candidate
        if ($Runtime) {
            break
        }
    }
}

$InstallMode = $ClientArgs.Count -gt 0 -and (
    $ClientArgs[0] -eq "--install-deps" -or $ClientArgs[0] -eq "--install-playback"
)
if ($InstallMode -and -not $ExplicitRuntime -and -not $Runtime) {
    $Bootstrap = Find-SystemPythonRuntime
    if (-not $Bootstrap) {
        [Console]::Error.WriteLine("Python 3.8+ not found. Install Python and rerun this launcher.")
        exit 127
    }
    New-Item -ItemType Directory -Force -Path $RuntimeHome | Out-Null
    $BootstrapArgs = @($Bootstrap.Prefix) + @("-m", "venv", $VenvDir)
    & $Bootstrap.Path @BootstrapArgs
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
    foreach ($Candidate in $VenvCandidates) {
        $Runtime = Resolve-PythonRuntime -Name $Candidate
        if ($Runtime) {
            break
        }
    }
    if (-not $Runtime) {
        [Console]::Error.WriteLine("Failed to create the tts-lychee Python runtime: $VenvDir")
        exit 1
    }
}

if (-not $Runtime) {
    $Runtime = Find-SystemPythonRuntime
}
if (-not $Runtime) {
    [Console]::Error.WriteLine("Python 3.8+ not found. Install Python and rerun this launcher.")
    exit 127
}

$PythonArgs = @($Runtime.Prefix)
if ($ClientArgs.Count -gt 0 -and $ClientArgs[0] -eq "--install-deps") {
    $PythonArgs += @("-m", "pip", "install", "-r", (Join-Path $ScriptDir "..\requirements.txt"))
} elseif ($ClientArgs.Count -gt 0 -and $ClientArgs[0] -eq "--install-playback") {
    $PythonArgs += @("-m", "pip", "install", "-r", (Join-Path $ScriptDir "..\requirements-playback.txt"))
} else {
    $PythonArgs += $Client
    $PythonArgs += $ClientArgs
}

& $Runtime.Path @PythonArgs
exit $LASTEXITCODE
