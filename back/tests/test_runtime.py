"""Atalhos simulados precisam falhar antes de iniciar serviços implantados."""

import pytest

from domain.runtime import AWS_RUNTIME_VARIABLES, check_simulated_clients


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch):
    for name in AWS_RUNTIME_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "simulated_v1")


@pytest.mark.parametrize("environment", [None, "production", "staging"])
def test_simulation_refused_outside_local(monkeypatch, environment):
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    with pytest.raises(RuntimeError, match="simulated_v1"):
        check_simulated_clients()


@pytest.mark.parametrize("marker", AWS_RUNTIME_VARIABLES)
def test_local_label_does_not_bypass_aws_runtime(monkeypatch, marker):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv(marker, "runtime")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        check_simulated_clients()


def test_explicit_local_simulation_is_allowed(monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    check_simulated_clients()


def test_cli_refuses_simulation_before_running_a_command(monkeypatch):
    from cli import main

    monkeypatch.setenv("APP_ENV", "production")
    with pytest.raises(RuntimeError, match="simulated_v1"):
        main(["--help"])


@pytest.mark.parametrize("repository", ["", "bedrock_titan_v1"])
def test_real_or_disabled_client_does_not_trigger_simulation_guard(monkeypatch, repository):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMBEDDING_REPOSITORY", repository)
    check_simulated_clients()


@pytest.mark.parametrize("environment", [None, "production"])
def test_simulated_llm_refused_outside_local(monkeypatch, environment):
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "")
    monkeypatch.setenv("LLM_REPOSITORY", "simulated_v1")
    if environment is None:
        monkeypatch.delenv("APP_ENV", raising=False)
    else:
        monkeypatch.setenv("APP_ENV", environment)
    with pytest.raises(RuntimeError, match="LLM_REPOSITORY=simulated_v1"):
        check_simulated_clients()


def test_simulated_llm_refused_in_aws_runtime(monkeypatch):
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "")
    monkeypatch.setenv("LLM_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("ECS_CONTAINER_METADATA_URI_V4", "runtime")
    with pytest.raises(RuntimeError, match="LLM_REPOSITORY"):
        check_simulated_clients()


def test_simulated_llm_allowed_locally_and_bedrock_anywhere(monkeypatch):
    monkeypatch.setenv("EMBEDDING_REPOSITORY", "")
    monkeypatch.setenv("LLM_REPOSITORY", "simulated_v1")
    monkeypatch.setenv("APP_ENV", "local")
    check_simulated_clients()
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("LLM_REPOSITORY", "bedrock_v1")
    check_simulated_clients()
