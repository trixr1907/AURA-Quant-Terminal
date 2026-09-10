
from __future__ import annotations

import threading
import time
import unittest
from unittest.mock import patch

from pathlib import Path

from urllib.error import HTTPError
from urllib.request import urlopen

import bitget_relay


class TestDockerReadinessContract(unittest.TestCase):
    def test_healthchecks_use_ready_with_a_start_period_for_first_public_probe(self):
        root = Path(__file__).resolve().parent.parent
        for name in ("Dockerfile", "docker-compose.yml"):
            text = (root / name).read_text(encoding="utf-8")
            self.assertIn("127.0.0.1:8787/ready", text, name)
            self.assertTrue(
                "start_period: 90s" in text or "--start-period=90s" in text,
                name,
            )



class TestRelayResilience(unittest.TestCase):
    def setUp(self):
        bitget_relay.PUBLIC_CACHE.clear()
        bitget_relay.UPLINK_RATE_LIMITER.reset()
        bitget_relay.reset_market_data_health()

    def test_identical_get_cache_misses_singleflight_to_one_upstream_call(self):
        calls = 0
        calls_lock = threading.Lock()
        barrier = threading.Barrier(8)
        results = []

        def request(*_args, **_kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.04)
            return {"code": "00000", "data": ["one"]}

        def worker():
            barrier.wait()
            results.append(bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "BTCUSDT"}))

        with patch.object(bitget_relay, "_request", side_effect=request):
            threads = [threading.Thread(target=worker) for _ in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2)

        self.assertEqual(calls, 1)
        self.assertEqual(len(results), 8)
        self.assertTrue(all(result[0]["code"] == "00000" for result in results))

    def test_identical_get_failure_is_shared_without_extra_upstream_calls(self):
        calls = 0
        calls_lock = threading.Lock()
        barrier = threading.Barrier(4)
        results = []

        def request(*_args, **_kwargs):
            nonlocal calls
            with calls_lock:
                calls += 1
            time.sleep(0.03)
            return {"code": "ERR", "data": None}

        def worker():
            barrier.wait()
            results.append(bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "ETHUSDT"}))

        with patch.object(bitget_relay, "_request", side_effect=request):
            threads = [threading.Thread(target=worker) for _ in range(4)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join(timeout=2)

        self.assertEqual(calls, 1)
        self.assertEqual(len(results), 4)
        self.assertTrue(all(result[0]["code"] == "ERR" for result in results))

    def test_upstream_429_retries_bounded_respects_retry_after_and_caches_success(self):
        responses = [
            {"code": "429", "_http": 429, "_retry_after": 0},
            {"code": "00000", "data": ["fresh"]},
        ]
        sleeps = []

        with patch.object(bitget_relay, "_request", side_effect=responses) as request, \
             patch.object(bitget_relay, "_sleep", side_effect=sleeps.append):
            result, cached = bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "BTCUSDT"})
            again, cached_again = bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "BTCUSDT"})

        self.assertFalse(cached)
        self.assertEqual(result["code"], "00000")
        self.assertEqual(request.call_count, 2)
        self.assertEqual(sleeps, [0])
        self.assertTrue(cached_again)
        self.assertEqual(again["data"], ["fresh"])

    def test_exhausted_upstream_429_is_distinct_from_relay_busy(self):
        with patch.object(bitget_relay, "_request", return_value={"code": "429", "_http": 429, "_retry_after": 0}), \
             patch.object(bitget_relay, "_sleep"):
            upstream, _ = bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "BTCUSDT"})
        self.assertEqual(upstream["code"], "UPSTREAM_RATE_LIMIT")
        self.assertEqual(upstream["_http"], 429)

        with patch.object(bitget_relay.UPLINK_RATE_LIMITER, "consume", return_value=False):
            busy, _ = bitget_relay._public_request_cached("GET", "/api/v2/mix/market/ticker", {"symbol": "ETHUSDT"})
        self.assertEqual(busy["code"], "RELAY_BUSY")

        self.assertEqual(busy["_http"], 429)



class TestReadyEndpoint(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = bitget_relay.RelayServer(("127.0.0.1", 0), bitget_relay.RelayHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        bitget_relay.reset_market_data_health()

    def ready_status(self):
        try:
            with urlopen(f"http://127.0.0.1:{self.port}/ready", timeout=2) as response:
                return response.status
        except HTTPError as error:
            return error.code

    def test_ready_http_status_tracks_market_data_freshness(self):
        self.assertEqual(self.ready_status(), 503)
        bitget_relay.record_market_data_result({"code": "00000"})
        self.assertEqual(self.ready_status(), 200)
        with bitget_relay.MARKET_DATA_HEALTH.lock:
            bitget_relay.MARKET_DATA_HEALTH.last_success_monotonic -= bitget_relay.READINESS_FRESH_SECONDS + 1
        self.assertEqual(self.ready_status(), 503)


    def test_ready_requires_fresh_successful_public_uplink(self):
        self.assertEqual(bitget_relay.market_data_readiness()["code"], "MARKET_DATA_NOT_READY")
        bitget_relay.record_market_data_result({"code": "00000"})
        self.assertTrue(bitget_relay.market_data_readiness()["ok"])
        with bitget_relay.MARKET_DATA_HEALTH.lock:
            bitget_relay.MARKET_DATA_HEALTH.last_success_monotonic -= bitget_relay.READINESS_FRESH_SECONDS + 1
        self.assertEqual(bitget_relay.market_data_readiness()["code"], "MARKET_DATA_STALE")

if __name__ == "__main__":
    unittest.main()
