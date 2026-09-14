#!/usr/bin/env python3
"""Unit tests for scripts/ops/aura_webhook_receiver.reference.py."""
import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent
RECEIVER_PATH = ROOT / "scripts" / "ops" / "aura_webhook_receiver.reference.py"


def _load_receiver_module():
    spec = importlib.util.spec_from_file_location("aura_webhook_receiver_ref", RECEIVER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("Failed to load receiver module spec")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


receiver = _load_receiver_module()


class TestWebhookReceiverBootstrapAndRecreate(unittest.TestCase):
    def test_current_container_config_returns_none_when_container_missing(self):
        """When docker inspect fails, current_container_config returns None without raising."""
        with patch.object(receiver, "run") as mock_run:
            mock_res = MagicMock()
            mock_res.returncode = 1
            mock_res.stdout = ""
            mock_run.return_value = mock_res
            config = receiver.current_container_config()
            self.assertIsNone(config)

    def test_current_container_config_returns_dict_when_container_exists(self):
        """When docker inspect succeeds, parsed container json is returned."""
        with patch.object(receiver, "run") as mock_run:
            mock_res = MagicMock()
            mock_res.returncode = 0
            mock_res.stdout = json.dumps([{"Id": "abc123", "Config": {"Env": ["A=1"]}}])
            mock_run.return_value = mock_res
            config = receiver.current_container_config()
            self.assertIsNotNone(config)
            self.assertEqual(config["Id"], "abc123")

    def test_bootstrap_arguments_canonical_spec(self):
        """bootstrap_arguments builds canonical arguments matching compose spec."""
        args = receiver.bootstrap_arguments("aura-quant-terminal:1.7.1")
        self.assertIn("docker", args)
        self.assertIn("run", args)
        self.assertIn("-d", args)
        self.assertIn("--name", args)
        self.assertIn(receiver.CONTAINER_NAME, args)
        self.assertIn("--restart", args)
        self.assertIn("unless-stopped", args)
        self.assertIn("--read-only", args)
        self.assertIn("--security-opt", args)
        self.assertIn("no-new-privileges:true", args)
        self.assertIn("--cap-drop", args)
        self.assertIn("ALL", args)
        self.assertIn("--tmpfs", args)
        self.assertIn("/tmp:rw,noexec,nosuid,size=64m", args)
        self.assertIn("-p", args)
        self.assertIn("127.0.0.1:8787:8787", args)
        self.assertIn("-v", args)
        self.assertIn("aura-state:/var/lib/aura", args)
        self.assertIn("-e", args)
        self.assertIn("SYM_PORT=8787", args)
        self.assertEqual(args[-1], "aura-quant-terminal:1.7.1")

    def test_bootstrap_arguments_applies_env_file_if_present(self):
        """When persistent aura_bot.env exists on host, bootstrap_arguments adds --env-file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tf:
            tf.write("AURA_BOT_MODE=server\nAURA_BOT_SCAN_SEC=60\n")
            tf_path = tf.name

        try:
            with patch.dict(os.environ, {"AURA_BOT_ENV_FILE": tf_path}):
                args = receiver.bootstrap_arguments("aura-quant-terminal:1.7.1")
                self.assertIn("--env-file", args)
                self.assertIn(tf_path, args)
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_recreate_arguments_preserves_config_and_applies_env_file(self):
        """recreate_arguments extracts existing container config and adds --env-file if present."""
        sample_config = {
            "HostConfig": {
                "RestartPolicy": {"Name": "unless-stopped"},
                "ReadonlyRootfs": True,
                "SecurityOpt": ["no-new-privileges:true"],
                "CapDrop": ["ALL"],
                "Tmpfs": {"/tmp": "rw,noexec,nosuid,size=64m"},
                "PortBindings": {"8787/tcp": [{"HostIp": "127.0.0.1", "HostPort": "8787"}]},
            },
            "Config": {
                "Env": ["SYM_PORT=8787", "AURA_ALLOWED_HOSTS=127.0.0.1", "AURA_STATE_DIR=/var/lib/aura"],
            },
            "Mounts": [
                {"Type": "volume", "Name": "aura-state", "Destination": "/var/lib/aura", "RW": True},
            ],
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tf:
            tf.write("AURA_BOT_MODE=server\n")
            tf_path = tf.name

        try:
            with patch.dict(os.environ, {"AURA_BOT_ENV_FILE": tf_path}):
                args = receiver.recreate_arguments(sample_config, "aura-quant-terminal:1.7.1")
                self.assertIn("--env-file", args)
                self.assertIn(tf_path, args)
                self.assertIn("-e", args)
                self.assertIn("SYM_PORT=8787", args)
                self.assertIn("aura-state:/var/lib/aura", args)
                self.assertEqual(args[-1], "aura-quant-terminal:1.7.1")
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_ntfy_notify_formatting(self):
        """_ntfy_notify builds correct POST request when AURA_NTFY_URL is set."""
        with patch.dict(os.environ, {"AURA_NTFY_URL": "https://ntfy.example.com/deploy-test"}):
            with patch("urllib.request.urlopen") as mock_urlopen:
                res = receiver._ntfy_notify("Deploy OK", "v1.7.1 deployed", priority=3, category="deploy")
                self.assertTrue(res)
                # Let daemon thread run
                import time
                time.sleep(0.05)
                self.assertTrue(mock_urlopen.called)
                req = mock_urlopen.call_args[0][0]
                self.assertEqual(req.get_header("X-title"), "Deploy OK")
                self.assertEqual(req.get_header("Priority"), "3")
                self.assertEqual(req.get_header("Tags"), "deploy")


if __name__ == "__main__":
    unittest.main()
