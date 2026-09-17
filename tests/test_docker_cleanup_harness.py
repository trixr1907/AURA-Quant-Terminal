"""Deterministische Unit-Tests fuer die Fehlerbehandlungs- und Cleanup-Logik des Docker-Harness.

Behebt und verifiziert gemaess AURA_Review_bb2a464.md folgende Faelle ohne Docker-Daemon:
1. docker-info-Timeout (darf den Fehler nicht entweichen lassen und muss verbliebene Ressourcen nennen).
2. compose-down Exit-Code 1 (muss als Cleanup-Fehler erfasst werden, check=False darf Fehler nicht verschlucken).
3. Urspruengliche Assertion plus Cleanup-Fehler (urspruengliche Assertion bleibt erhalten, Cleanup-Fehler wird gemeldet).
4. Cleanup-Fehler nach ansonsten erfolgreichem Ablauf (kein Exit 0 / PASS, sondern RuntimeError).
"""

from __future__ import annotations

import io
from unittest.mock import patch

import pytest

from scripts.verify_docker_compose_lifecycle import (
    cleanup_run_resources,
    run_lifecycle_with_cleanup,
)


def test_docker_info_timeout_named_resources():
    """docker-info-Timeout darf nicht unkontrolliert entweichen und muss verbliebene Ressourcen benennen."""
    with patch("scripts.verify_docker_compose_lifecycle.run_cmd", side_effect=RuntimeError("Command timed out after 5s (docker info)")):
        errors = cleanup_run_resources(
            project_name="test_proj_timeout",
            run_id="run_timeout_123",
            image_tag="test-image:timeout",
            sentinel_vol="aura_sentinel_vol_timeout",
            sentinel_net="aura_sentinel_net_timeout",
            container_api="aura-api-timeout",
            container_worker="aura-worker-timeout",
            volume_data="aura_data_timeout",
            volume_state="aura_state_timeout",
        )

    # Es darf keine Exception geworfen worden sein, stattdessen strukturierter Fehler
    assert len(errors) == 1
    err_msg = errors[0]
    assert "Docker-Daemon nicht erreichbar waehrend Cleanup" in err_msg
    assert "Command timed out after 5s (docker info)" in err_msg
    # Alle bekannten Run-Ressourcen muessen namentlich enthalten sein
    assert "test_proj_timeout" in err_msg
    assert "aura-api-timeout" in err_msg
    assert "aura-worker-timeout" in err_msg
    assert "aura_data_timeout" in err_msg
    assert "aura_state_timeout" in err_msg
    assert "test-image:timeout" in err_msg
    assert "aura_sentinel_vol_timeout" in err_msg
    assert "aura_sentinel_net_timeout" in err_msg


def test_compose_down_exit_code_1_reported_as_error():
    """compose down mit Exit-Code 1 muss als Cleanup-Fehler erfasst werden (check=False darf nicht errors=[] liefern)."""
    def mock_run_cmd(cmd, **kwargs):
        if "info" in cmd:
            return 0, "Ubuntu 24.04 | 29.1.3", ""
        if "ps" in cmd:
            return 0, "", ""
        return 0, "", ""

    def mock_compose_cmd(args, **kwargs):
        if "down" in args:
            return 1, "", "simulated down failure: volume in use"
        return 0, "", ""

    with patch("scripts.verify_docker_compose_lifecycle.run_cmd", side_effect=mock_run_cmd), \
         patch("scripts.verify_docker_compose_lifecycle.compose_cmd", side_effect=mock_compose_cmd):
        errors = cleanup_run_resources(
            project_name="test_proj_down_fail",
            run_id="run_down_fail",
        )

    assert len(errors) >= 1
    assert any("Compose down failed with exit code 1" in e for e in errors)
    assert any("simulated down failure: volume in use" in e for e in errors)


def test_primary_assertion_preserved_plus_cleanup_error_reported():
    """Urspruengliche Assertion muss exakt erhalten bleiben und Cleanup-Fehler auf stderr gemeldet werden."""
    def failing_lifecycle():
        raise AssertionError("Urspruenglicher Testfehler vor Teardown")

    stderr_capture = io.StringIO()

    with patch(
        "scripts.verify_docker_compose_lifecycle.cleanup_run_resources",
        return_value=["Simulierter Zusatz-Cleanup-Fehler"],
    ) as cleanup_mock:
        with pytest.raises(AssertionError) as exc_info:
            run_lifecycle_with_cleanup(
                failing_lifecycle,
                project_name="test_proj_err",
                run_id="run_err",
                stderr_stream=stderr_capture,
            )

    assert cleanup_mock.call_count == 1

    # Urspruengliche Assertion muss intakt sein
    assert "Urspruenglicher Testfehler vor Teardown" in str(exc_info.value)
    # Zusaetzlicher Cleanup-Fehler muss auf stderr gemeldet werden
    stderr_out = stderr_capture.getvalue()
    assert "[ZUSATZ-CLEANUP-FEHLER]" in stderr_out
    assert "Simulierter Zusatz-Cleanup-Fehler" in stderr_out


def test_cleanup_failure_after_successful_run_raises_runtime_error():
    """Wenn nur der Cleanup fehlschlaegt, darf kein uneingeschraenkter PASS/Exit 0 gemeldet werden."""
    def successful_lifecycle():
        pass  # Alles im Ablauf bestanden

    with patch("scripts.verify_docker_compose_lifecycle.cleanup_run_resources", return_value=["Down exit code 1: volume busy"]):
        with pytest.raises(RuntimeError) as exc_info:
            run_lifecycle_with_cleanup(
                successful_lifecycle,
                project_name="test_proj_success",
                run_id="run_success",
            )

    assert "Ablauf abgeschlossen, aber Cleanup fehlgeschlagen" in str(exc_info.value)
    assert "Down exit code 1: volume busy" in str(exc_info.value)
