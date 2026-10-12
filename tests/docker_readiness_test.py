"""Verify readiness on a Compose CLI which rejects the newer --wait flag."""

import os
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).parents[1] / "docker" / "wait-for-stack.sh"


@pytest.fixture
def docker_env(tmp_path):
    docker = tmp_path / "docker"
    docker.write_text('''#!/usr/bin/env python3
import os, sys
args = sys.argv[1:]
if any(arg.startswith("--wait") for arg in args):
    sys.exit("unknown flag: --wait")
if args[0] == "inspect":
    print(os.environ.get("FAKE_CONTAINER_STATE", "running healthy"))
elif "ps" in args and "-q" in args:
    print(args[-1] + "-container")
elif "logs" in args:
    print("Collector diagnostics")
''')
    docker.chmod(0o755)
    return dict(os.environ, PATH=str(tmp_path) + os.pathsep + os.environ["PATH"])


def run_check(env, *services):
    return subprocess.run(["sh", str(SCRIPT), *services], env=env,
                          capture_output=True, text=True, timeout=10)


def test_readiness_works_without_compose_wait_flag(docker_env):
    result = run_check(docker_env)
    assert result.returncode == 0, result.stderr
    assert "Dashboard: http://localhost:3000" in result.stdout


def test_stopped_container_fails_and_shows_logs(docker_env):
    docker_env["FAKE_CONTAINER_STATE"] = "exited unhealthy"
    result = run_check(docker_env, "collector")
    assert result.returncode == 1
    assert "collector stopped" in result.stderr
    assert "Collector diagnostics" in result.stderr


def test_running_process_is_not_enough_for_readiness(docker_env):
    docker_env["FAKE_CONTAINER_STATE"] = "running starting"
    docker_env["QUICKSTART_TIMEOUT"] = "1"
    result = run_check(docker_env)
    assert result.returncode == 1
    assert "Timed out" in result.stderr


def test_timeout_setting_must_be_positive(docker_env):
    docker_env["QUICKSTART_TIMEOUT"] = "0"
    result = run_check(docker_env)
    assert result.returncode == 2
