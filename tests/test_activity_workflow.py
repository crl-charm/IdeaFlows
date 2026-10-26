"""Run the actual activity step against disposable local Git repositories."""

import os
from pathlib import Path
import re
import shutil
import subprocess
import textwrap

import pytest


@pytest.fixture(autouse=True)
def isolated_database():
    """This shell-only check does not need the shared Flask database fixture."""


@pytest.mark.parametrize("schedule,expected", [
    ("0 16 * * *", 4),
    ("15 1 * * *", 2),
    ("25 12 * * *", 2),
    ("", 2),  # Manual dispatch.
    ("unrecognized", 0),
])
def test_activity_commit_counts_and_readme_preservation(tmp_path, schedule, expected):
    bash = shutil.which("bash")
    if os.name == "nt":
        candidate = Path("C:/Program Files/Git/bin/bash.exe")
        bash = str(candidate) if candidate.is_file() else None
    if not bash or not shutil.which("git"):
        pytest.skip("Git and Bash are required for the workflow check")

    workflow = (Path(__file__).resolve().parents[1] / ".github/workflows/activity.yml").read_text(encoding="utf-8")
    assert re.findall(r"- cron: '([^']+)'", workflow) == [
        "0 16 * * *", "15 1 * * *", "25 12 * * *",
    ]
    script = textwrap.dedent(workflow.split("        run: |\n", 1)[1])

    def git(*args, cwd=tmp_path):
        return subprocess.check_output(["git", *args], cwd=cwd, text=True, stderr=subprocess.PIPE).strip()

    origin = tmp_path / "origin.git"
    checkout = tmp_path / "checkout"
    git("init", "--bare", "--initial-branch=master", str(origin))
    git("clone", str(origin), str(checkout))
    git("config", "user.name", "Isolated Test", cwd=checkout)
    git("config", "user.email", "test@example.invalid", cwd=checkout)
    visible_readme = "# IdeaFlow\n\nKeep these instructions.\n"
    (checkout / "README.md").write_text(visible_readme + "<!-- telemetry: old -->\n", encoding="utf-8")
    git("add", "README.md", cwd=checkout)
    git("commit", "-m", "Initial fixture", cwd=checkout)
    git("push", "origin", "master", cwd=checkout)
    initial = git("rev-parse", "HEAD", cwd=checkout)

    result = subprocess.run(
        [bash, "-c", script], cwd=checkout,
        env={**os.environ, "SCHEDULE": schedule, "GITHUB_RUN_ID": "isolated-check"},
        text=True, capture_output=True, timeout=45,
    )
    assert (result.returncode == 0) == bool(expected), result.stdout + result.stderr
    assert int(git("rev-list", "--count", f"{initial}..master", cwd=origin)) == expected
    readme = (checkout / "README.md").read_text(encoding="utf-8")
    assert readme.startswith(visible_readme)
    if expected:
        assert readme.count("<!-- activity:") == 1
        assert "<!-- telemetry:" not in readme
        assert f"commit={expected}/{expected}" in readme
