"""Offline adapter contract tests. These never create a paid remote task."""
import io
import hashlib
import json
import os
import tempfile
import unittest
from urllib.error import HTTPError

from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError
from film_core.fixture import seed
from film_core.h3_profile import darl_h3_profile


class AdapterContractTests(unittest.TestCase):
    def setUp(self):
        self.core = seed(Core(test_mode=True), production=True)
        self.core.put("model_profile", "h3-darl", darl_h3_profile(False), "documented", "documented")
        self.adapter = DarlH3Adapter(key="offline-test-token")

    def tearDown(self):
        self.core.close()

    def task(self, clip="A", task_id="task-a"):
        return self.core.compile_h3(task_id, "brief:" + clip, "h3-darl",
                                    parameters={"resolution": "768P", "num_inference_steps": 20,
                                                "turbo": False, "watermark": False})

    def test_documented_profile_and_project_ratio(self):
        profile = self.core.get("model_profile", "h3-darl")["payload"]
        self.assertEqual(profile["verification_stage"], "DOCUMENTED_PENDING_REAL_REQUEST")
        self.assertEqual(profile["model_id"], "MiniMax-H3")
        self.assertEqual(profile["duration_envelope"], {"verified": True, "min": 4, "max": 15,
            "source": profile["duration_envelope"]["source"]})
        task = self.task()
        self.assertTrue(self.core.preflight(task["id"]).ready)
        self.assertEqual(task["aspect_ratio"], self.core.get("project", "station-film")["payload"]["aspect_ratio"])
        with self.assertRaises(DomainError):
            self.core.compile_h3("bad-ratio", "brief:A", "h3-darl", aspect_ratio="9:16",
                                 parameters=task["parameters"])

    def test_t2va_request_and_reference_role_mapping(self):
        task = self.task()
        body = self.adapter.build_request(task)
        self.assertEqual(body["model"], "MiniMax-H3")
        self.assertEqual(body["ratio"], "16:9")
        self.assertEqual(body["resolution"], "768P")
        self.assertEqual(body["num_inference_steps"], 20)
        self.assertEqual(len(body["content"]), 1)
        self.assertEqual(body["content"][0]["type"], "text")
        task["media_bindings"] = [{"id": "r1", "role": "continuity_anchor", "media_type": "image",
                                   "uri": "https://example.com/frame.png", "control_media_id": "frame-a"}]
        body = self.adapter.build_request(task)
        self.assertEqual(body["content"][1]["role"], "reference_image")
        self.assertNotIn("first_frame", [item.get("role") for item in body["content"]])
        self.assertEqual(body["ratio"], "16:9")

    def test_first_last_reference_exclusion_and_continuation_semantics(self):
        task = self.task()
        task["media_bindings"] = [
            {"id": "first", "role": "first_frame", "media_type": "image", "uri": "https://example.com/first.png"},
            {"id": "ref", "role": "continuity_anchor", "media_type": "image", "uri": "https://example.com/ref.png"},
        ]
        with self.assertRaises(DomainError):
            self.adapter.build_request(task)
        task["media_bindings"] = task["media_bindings"][:1]
        self.assertEqual(self.adapter.build_request(task)["ratio"], "adaptive")
        task["task_mode"] = "VIDEO_CONTINUATION"
        task["media_bindings"] = []
        task["continuation"] = {"take_id": "selected-c1"}
        task["control_media_snapshot"] = {"payload": {"role": "stable_tail", "uri": "https://example.com/tail.mp4"}}
        with self.assertRaises(DomainError):
            self.adapter.build_request(task)
        task["compiled_prompt"] += " [video continuation]"
        self.assertEqual(self.adapter.build_request(task)["content"][1]["role"], "reference_video")

    def test_provider_error_classification_and_real_media_gate(self):
        def failing_opener(request, timeout):
            raise HTTPError(request.full_url, 429, "Too Many Requests", {},
                            io.BytesIO(json.dumps({"code": "rate_limit", "message": "slow down"}).encode()))
        adapter = DarlH3Adapter(key="offline-test-token", opener=failing_opener)
        with self.assertRaises(ProviderError) as caught:
            adapter.poll("task-offline")
        self.assertEqual(caught.exception.code, "rate_limit")
        self.assertTrue(caught.exception.transient)
        task = self.task()
        self.core.create_job("job-a", task["id"])
        self.core.job_event("job-a", "running", {"provider_task_id": "offline"})
        self.core.job_event("job-a", "succeeded", {"usage": {"output_seconds": 10}})
        with self.assertRaises(DomainError):
            self.core.record_take("take-without-media", "job-a", "/tmp/absent.mp4")
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "offline-contract.mp4")
            with open(path, "wb") as media:
                media.write(b"contract-test-only")
            self.core.register_media("media-a", path, hashlib.sha256(b"contract-test-only").hexdigest(),
                                     os.path.getsize(path), "video/mp4", 1.0)
            take = self.core.record_take("take-a", "job-a", path,
                                         provider_metadata={"id": "offline"}, media_id="media-a")
            self.assertEqual(take["media_id"], "media-a")
            self.assertEqual(self.core.media("media-a")["local_path"], path)

    def test_visual_anchor_for_cut_becomes_stale_after_selection_change(self):
        c = self.core
        task_a = self.task()
        c.create_job("job-a", task_a["id"])
        c.job_event("job-a", "running")
        c.job_event("job-a", "succeeded")
        c.record_take("take-a1", "job-a", "test-only://a1", test_only=True)
        c.record_take("take-a2", "job-a", "test-only://a2", test_only=True)
        selected = c.select_take("A", "take-a1", "fixture human")
        c.observe("obs-a", "take-a1", {"character_id": "linxia", "look_id": "linxia-rain",
                                         "location_id": "old-station", "crying": False}, "fixture observer")
        c.confirm_state("A", "obs-a", "fixture human")
        c.put("control_media", "anchor-a", {"role": "visual_anchor", "source_take_id": "take-a1",
                                               "source_selection_id": selected["id"],
                                               "uri": "data:image/png;base64,YWJj"}, "fixture")
        c.put("reference_binding", "ref-b", {"control_media_id": "anchor-a",
                                                "role": "continuity_anchor", "media_type": "image",
                                                "uri": "data:image/png;base64,YWJj"}, "fixture")
        c.add_dependency("B", "A", "VISUAL_ANCHOR")
        brief = c.get("brief", "brief:B")["payload"]
        brief["references"] = ["ref-b"]
        c.save_brief("B", brief)
        c.rebase_brief_state("B", "A")
        task_b = c.compile_h3("task-b", "brief:B", "h3-darl",
                              parameters={"resolution": "768P", "num_inference_steps": 20,
                                          "turbo": False, "watermark": False})
        self.assertTrue(c.preflight(task_b["id"]).ready)
        roles = [item.get("role") for item in self.adapter.build_request(task_b)["content"]]
        self.assertIn("reference_image", roles)
        self.assertNotIn("reference_video", roles)
        c.select_take("A", "take-a2", "fixture human")
        self.assertEqual(c.impact(task_b["id"]), "Must Replan / Rebuild")

    def test_adapter_create_query_response_flows_into_job_and_test_take(self):
        class Response:
            headers = {"Content-Type": "application/json"}
            def __init__(self, payload):
                self.payload = payload
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return json.dumps(self.payload).encode()
        def opener(request, timeout):
            if request.get_method() == "POST":
                return Response({"id": "task-provider-test", "status": "queued"})
            return Response({"id": "task-provider-test", "status": "succeeded",
                             "content": {"video_url": "https://example.com/contract-only.mp4"},
                             "usage": {"output_seconds": 10}})
        adapter = DarlH3Adapter(key="offline-test-token", opener=opener)
        task = self.task()
        self.core.create_job("job-provider-contract", task["id"])
        created = adapter.submit(task, "job-provider-contract")
        self.core.job_event("job-provider-contract", "running", {"provider_task_id": created["id"]})
        queried = adapter.poll(created["id"])
        self.core.job_event("job-provider-contract", "succeeded", {"query_response": queried})
        take = self.core.record_take("take-provider-contract", "job-provider-contract",
                                     "test-only://contract", provider_metadata=queried, test_only=True)
        self.assertEqual(take["job_id"], "job-provider-contract")
        self.assertEqual(self.core.job("job-provider-contract")["metadata"]["query_response"]["usage"]["output_seconds"], 10)


if __name__ == "__main__":
    unittest.main()
