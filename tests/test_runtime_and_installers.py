from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "tts-lychee"


def as_bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name == "nt":
        return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"
    return resolved.as_posix()


def test_runtime_launcher_uses_an_available_python_from_the_skill_directory():
    env = os.environ.copy()
    env["TTS_API_KEY"] = "test-key"

    if os.name == "nt":
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            pytest.skip("PowerShell is unavailable")
        launcher = SKILL / "scripts" / "run.ps1"
        assert launcher.exists()
        command = [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(launcher), "--doctor"]
    else:
        bash = shutil.which("bash")
        if not bash:
            pytest.skip("Bash is unavailable")
        launcher = SKILL / "scripts" / "run.sh"
        assert launcher.exists()
        command = [bash, str(launcher), "--doctor"]

    result = subprocess.run(
        command,
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["success"] is True


def test_bash_installer_supports_the_cross_agent_skills_directory():
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is unavailable")
    with tempfile.TemporaryDirectory(prefix=".installer-test-", dir=str(ROOT)) as temporary:
        install_root = Path(temporary)
        claude_home = install_root / "claude"
        agents_home = install_root / "agents"
        env = os.environ.copy()
        env["CLAUDE_HOME"] = as_bash_path(claude_home)
        env["AGENTS_HOME"] = as_bash_path(agents_home)

        result = subprocess.run(
            [bash, str(ROOT / "install.sh"), "--target", "agents"],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=False,
        )

        assert result.returncode == 0, result.stderr
        assert (agents_home / "skills" / "tts-lychee" / "SKILL.md").exists()
        assert not (claude_home / "skills" / "tts-lychee").exists()


@pytest.mark.skipif(os.name != "nt", reason="PowerShell installer is Windows-specific")
def test_powershell_installer_supports_codex_without_installing_claude(tmp_path: Path):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is unavailable")
    claude_home = tmp_path / "claude"
    codex_home = tmp_path / "codex"

    result = subprocess.run(
        [
            powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "install.ps1"),
            "-Target", "codex", "-ClaudeHome", str(claude_home), "-CodexHome", str(codex_home),
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (codex_home / "skills" / "tts-lychee" / "SKILL.md").exists()
    assert not (claude_home / "skills" / "tts-lychee").exists()
