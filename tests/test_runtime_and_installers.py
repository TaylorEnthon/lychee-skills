from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "tts-lychee"


def as_bash_path(path: Path) -> str:
    resolved = path.resolve()
    if os.name == "nt":
        return f"/{resolved.drive[0].lower()}{resolved.as_posix()[2:]}"
    return resolved.as_posix()


def venv_python(venv_dir: Path) -> Path:
    windows = venv_dir / "Scripts" / "python.exe"
    return windows if windows.exists() else venv_dir / "bin" / "python"


@pytest.fixture(scope="module")
def isolated_runtime(tmp_path_factory):
    runtime_root = tmp_path_factory.mktemp("tts runtime with spaces")
    venv_dir = runtime_root / "venv"
    result = subprocess.run(
        [sys.executable, "-m", "venv", "--system-site-packages", str(venv_dir)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert venv_python(venv_dir).exists()
    return runtime_root, venv_dir


def assert_doctor_uses(result, expected_python: Path):
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    check = next(item for item in payload["checks"] if item["name"] == "python executable")
    assert Path(check["detail"]).resolve() == expected_python.resolve()


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


def test_bash_launcher_prefers_the_skill_owned_runtime(isolated_runtime):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is unavailable")
    runtime_root, venv_dir = isolated_runtime
    env = os.environ.copy()
    env.pop("TTS_PYTHON", None)
    env["TTS_RUNTIME_HOME"] = as_bash_path(runtime_root)
    env["TTS_API_KEY"] = "test-key"

    result = subprocess.run(
        [bash, str(SKILL / "scripts" / "run.sh"), "--doctor"],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert_doctor_uses(result, venv_python(venv_dir))


def test_powershell_launcher_prefers_the_skill_owned_runtime(isolated_runtime):
    powershell = shutil.which("pwsh") or shutil.which("powershell")
    if not powershell:
        pytest.skip("PowerShell is unavailable")
    runtime_root, venv_dir = isolated_runtime
    env = os.environ.copy()
    env.pop("TTS_PYTHON", None)
    env["TTS_RUNTIME_HOME"] = str(runtime_root)
    env["TTS_API_KEY"] = "test-key"

    result = subprocess.run(
        [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(SKILL / "scripts" / "run.ps1"),
            "--doctor",
        ],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )

    assert_doctor_uses(result, venv_python(venv_dir))


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
