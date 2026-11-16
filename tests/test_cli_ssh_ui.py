"""SSH launch uses the remote UI entry point and a loopback-only tunnel."""
import shlex
import subprocess

import pytest
from typer.testing import CliRunner

from looplab.cli import app


def test_ssh_ui_forwards_remote_arguments(monkeypatch):
    calls = []

    def ssh(argv, *, check):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr("looplab.cli.ui_cmds.subprocess.run", ssh)
    result = CliRunner().invoke(app, [
        "ui", "--ssh", "wowsearch", "--ssh-directory", "project with spaces; echo nope",
        "--ssh-looplab", ".venv/bin/looplab", "--run-root", "my runs", "--port", "8876",
        "--ssh-port", "9876", "--root-path", "/proxy", "--no-build",
    ])
    assert result.exit_code == 0, result.output
    assert "http://127.0.0.1:8876" in result.output
    argv, = calls
    assert argv[:-1] == [
        "ssh", "-tt", "-o", "ExitOnForwardFailure=yes", "-L",
        "127.0.0.1:8876:127.0.0.1:9876", "wowsearch",
    ]
    assert shlex.split(argv[-1]) == [
        "cd", "./project with spaces; echo nope", "&&", "exec", ".venv/bin/looplab",
        "ui", "--host", "127.0.0.1", "--port", "9876",
        "--run-root", "my runs", "--no-build", "--root-path", "/proxy",
    ]


@pytest.mark.parametrize("options", [
    ["--ssh=-oProxyCommand=echo bad"],
    ["--ssh", "wowsearch", "--host", "0.0.0.0"],
    ["--ssh", "wowsearch", "--ssh-port", "65536"],
    ["--ssh-directory", "/somewhere"],
])
def test_ssh_ui_refuses_invalid_options_without_connecting(monkeypatch, options):
    def unexpected_ssh(*args, **kwargs):
        pytest.fail("invalid options attempted to start SSH")

    monkeypatch.setattr("looplab.cli.ui_cmds.subprocess.run", unexpected_ssh)
    result = CliRunner().invoke(app, ["ui", *options])
    assert result.exit_code == 2, result.output


def test_ssh_ui_propagates_remote_failure(monkeypatch):
    monkeypatch.setattr("looplab.cli.ui_cmds.subprocess.run",
                        lambda argv, **kwargs: subprocess.CompletedProcess(argv, 255))
    result = CliRunner().invoke(app, ["ui", "--ssh", "wowsearch"])
    assert result.exit_code == 255
