[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$ClientArgs
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Client = Join-Path $ScriptDir "tts_client.py"

function Find-PythonRuntime {
    $Candidates = @()
    if ($env:TTS_PYTHON) {
        $Candidates += [pscustomobject]@{ Name = $env:TTS_PYTHON; Prefix = @() }
    }
    $Candidates += [pscustomobject]@{ Name = "python"; Prefix = @() }
    $Candidates += [pscustomobject]@{ Name = "py"; Prefix = @("-3") }
    $Candidates += [pscustomobject]@{ Name = "python3"; Prefix = @() }

    foreach ($Candidate in $Candidates) {
        $Command = Get-Command $Candidate.Name -ErrorAction SilentlyContinue
        if (-not $Command) {
            continue
        }
        $ProbeArgs = @($Candidate.Prefix) + @(
            "-c",
            "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"
        )
        try {
            & $Command.Source @ProbeArgs *> $null
            if ($LASTEXITCODE -eq 0) {
                return [pscustomobject]@{ Path = $Command.Source; Prefix = @($Candidate.Prefix) }
            }
        } catch {
            continue
        }
    }
    return $null
}

$Runtime = Find-PythonRuntime
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
