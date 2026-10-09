import copy
import os
import tempfile
import unittest

from film_core import Core, DomainError
from film_core.fixture import seed


class ProductionCoreTests(unittest.TestCase):
    def setUp(self):
        self.core = seed(Core(test_mode=True))

    def tearDown(self):
        self.core.close()

    def compile(self, clip, suffix="1", continuation=None):
        return self.core.compile_h3("task-" + clip + "-" + suffix,
                                    "brief:" + clip, "h3-test-contract",
                                    continuation=continuation)

    def succeed(self, clip, suffix="1", continuation=None):
        task = self.compile(clip, suffix, continuation)
        self.assertTrue(self.core.preflight(task["id"]).ready)
        job_id = "job-" + clip + "-" + suffix
        self.core.create_job(job_id, task["id"])
        self.core.job_event(job_id, "running", {"provider_task_id": "synthetic-" + job_id})
        self.core.job_event(job_id, "succeeded", {"provider_task_id": "synthetic-" + job_id})
        take_id = "take-" + clip + "-" + suffix
        self.core.record_take(take_id, job_id, "test-only://" + take_id,
                              {"provider": "synthetic contract adapter"}, test_only=True)
        return task, job_id, take_id

    def select_confirm(self, clip, take_id, suffix="1"):
        self.core.select_take(clip, take_id, "fixture human selector")
        self.core.observe("observed-" + clip + "-" + suffix, take_id,
                          {"character_id": "linxia", "look_id": "linxia-rain",
                           "location_id": "old-station", "crying": False,
                           "letter_state": "folded", "position": clip}, "fixture observer")
        return self.core.confirm_state(clip, "observed-" + clip + "-" + suffix,
                                       "fixture human confirmer")

    def test_mapping_and_fixture_structure(self):
        c = self.core
        self.assertEqual([m["shot_id"] for m in c.mappings("A")], ["S01", "S02", "S03"])
        self.assertEqual([(m["shot_start"], m["shot_end"]) for m in c.mappings("C1")], [(0, 12)])
        self.assertEqual([(m["shot_start"], m["shot_end"]) for m in c.mappings("C2")], [(12, 20)])
        self.assertEqual([m["clip_start"] for m in c.mappings("A")], [0, 3, 5])
        self.assertEqual([m["cut_before"] for m in c.mappings("A")], [0, 1, 1])
        for cid in ("A", "B", "C1", "C2"):
            self.assertTrue(c.brief_qa(c.get("brief", "brief:" + cid)).ready)
        self.assertEqual(c.get("clip", "B")["payload"]["handoff"], "STATE_CONTINUE_NEW_VIEW")

    def test_brief_versions_fidelity_and_job_failure(self):
        c = self.core
        original = c.get("brief", "brief:A")
        task = self.compile("A")
        self.assertEqual(task["sections"]["retention_analysis"], ["林夏没有哭", "不得新增关键剧情动作"])
        self.assertIn("林夏没有哭", task["compiled_prompt"])
        self.assertIn("不哭", task["compiled_prompt"])
        self.assertEqual(c.get("shot", "S03")["version"], 1)
        self.assertEqual(c.get("brief", "brief:A")["version"], 1)
        c.create_job("completed-job", task["id"])
        c.job_event("completed-job", "running")
        c.job_event("completed-job", "succeeded")
        c.record_take("historical-take", "completed-job", "test-only://historical-take", test_only=True)
        c.create_job("failed-job", task["id"])
        c.job_event("failed-job", "running")
        c.job_event("failed-job", "failed", {"error": "synthetic transport failure"})
        retry = c.create_job("retry-job", task["id"], retry_of="failed-job")
        changed = copy.deepcopy(original["payload"])
        changed["purpose"] += "；延长停顿"
        c.save_brief("A", changed)
        self.assertEqual(c.get("brief", "brief:A")["version"], 2)
        self.assertEqual(c.get("brief", "brief:A", 1)["payload"], original["payload"])
        self.assertEqual(c.task(task["id"])["source_brief"]["version"], 1)
        self.assertEqual(c.get("brief", "brief:A", 1)["payload"], original["payload"])
        self.assertEqual(c.take("historical-take")["job_id"], "completed-job")
        self.assertEqual(c.impact(task["id"]), "Must Replan / Rebuild")
        with self.assertRaises(DomainError):
            c.create_job("stale-retry", task["id"], retry_of="failed-job")
        self.assertEqual(retry["snapshot"]["retry_of"], "failed-job")
        self.assertEqual(retry["snapshot"]["task"]["source_brief"]["version"], 1)
        self.assertEqual(retry["snapshot"]["task"]["compiler_version"], "h3-compiler/0.1")
        self.assertEqual(retry["snapshot"]["task"]["model_profile"]["version"], 1)
        self.assertEqual(retry["snapshot"]["task"]["media_bindings"][0]["role"], "character_look")
        self.assertEqual(c.get("shot", "S03")["version"], 1)

    def test_qa_preflight_and_no_silent_repair(self):
        c = self.core
        p = copy.deepcopy(c.get("brief", "brief:A")["payload"])
        p["action_process"] = [{"label": "sad"}]
        p["performance"] = {"emotion": "sad"}
        p["references"] = ["missing-ref"]
        bad = c.save_brief("A", p)
        codes = {r["code"] for r in c.brief_qa(bad).reasons}
        self.assertIn("ACTION_NOT_PROCESS", codes)
        self.assertIn("ABSTRACT_PERFORMANCE", codes)
        self.assertIn("REFERENCE_MISSING", codes)
        with self.assertRaises(DomainError):
            c.compile_h3("bad-task", bad["id"], "h3-test-contract")
        # The older approved version remains independently compilable.
        task = c.compile_h3("older-task", "brief:A", "h3-test-contract", brief_version=1)
        self.assertEqual(task["source_brief"]["version"], 1)
        self.assertEqual(c.impact(task["id"]), "Must Replan / Rebuild")
        real_profile_task = c.compile_h3("unverified-task", "brief:A", "h3-unverified", brief_version=1)
        result = c.preflight(real_profile_task["id"])
        self.assertFalse(result.ready)
        self.assertIn("DURATION_UNVERIFIED", {r["code"] for r in result.reasons})
        with self.assertRaises(DomainError):
            c.create_job("unsafe-job", real_profile_task["id"])
        bad_parameter_task = c.compile_h3("bad-parameter-task", "brief:A", "h3-test-contract",
                                          parameters={"unverified_knob": 5}, brief_version=1)
        self.assertIn("INVALID_GENERATION_PARAMETER",
                      {r["code"] for r in c.preflight(bad_parameter_task["id"]).reasons})

    def test_sqlite_versions_survive_reopen(self):
        with tempfile.TemporaryDirectory() as directory:
            path = os.path.join(directory, "core.sqlite")
            first = Core(path)
            first.put("project", "p", {"title": "first"}, "human")
            first.put("project", "p", {"title": "second"}, "human")
            first.close()
            reopened = Core(path)
            self.assertEqual(reopened.get("project", "p", 1)["payload"]["title"], "first")
            self.assertEqual(reopened.get("project", "p")["payload"]["title"], "second")
            reopened.close()

    def test_takes_selection_and_canonical_gate(self):
        c = self.core
        _, _, take_a = self.succeed("A", "1")
        _, _, take_b = self.succeed("A", "2")
        c.observe("unselected-observation", take_b, {"crying": True}, "AI observer")
        c.select_take("A", take_a, "human selector")
        with self.assertRaises(DomainError):
            c.confirm_state("A", "unselected-observation", "human confirmer")
        snapshot = self.select_confirm("A", take_a)
        self.assertEqual(snapshot["payload"]["crying"], False)
        self.assertEqual(c.next_clip_context("A")["facts"]["position"], "A")
        c.select_take("A", take_b, "human selector")
        self.assertEqual(c.take(take_a)["id"], take_a)
        self.assertEqual(c.take(take_b)["id"], take_b)
        with self.assertRaises(DomainError):
            c.next_clip_context("A")
        c.confirm_state("A", "unselected-observation", "human confirmer")
        self.assertEqual(c.next_clip_context("A")["facts"]["crying"], True)

    def test_complete_rainy_station_chain_and_continuation_impact(self):
        c = self.core
        task_a, _, take_a = self.succeed("A")
        self.select_confirm("A", take_a)
        c.rebase_brief_state("B", "A")
        task_b, _, take_b = self.succeed("B")
        self.assertIsNone(task_b["continuation"])
        self.assertTrue(c.preflight(task_b["id"]).ready)
        self.assertEqual(c.next_clip_context("A")["facts"]["position"], "A")
        self.select_confirm("B", take_b)
        c.rebase_brief_state("C1", "B")
        _, _, take_c1 = self.succeed("C1")
        self.select_confirm("C1", take_c1)
        # A continuation-specific task may be drafted, but cannot be READY yet.
        pending = self.compile("C2", "pending")
        self.assertIn("CONTINUATION_SOURCE_MISSING",
                      {r["code"] for r in c.preflight(pending["id"]).reasons})
        self.assertIn("STATE_CONTEXT_STALE_OR_MISSING",
                      {r["code"] for r in c.preflight(pending["id"]).reasons})
        c.create_stable_tail("tail-c1", "C1", take_c1, "test-only://tail-c1",
                             {"stable": True, "identity": True, "prop": True})
        c.rebase_brief_state("C2", "C1")
        continuation = c.continuation_source("C1", "tail-c1")
        task_c2, _, take_c2 = self.succeed("C2", "ready", continuation)
        self.assertEqual(task_c2["continuation"]["take_id"], take_c1)
        self.assertEqual(c.next_clip_context("C1")["facts"]["position"], "C1")
        self.select_confirm("C2", take_c2)
        self.assertEqual(c.next_clip_context("C2")["facts"]["position"], "C2")
        self.assertEqual(len([c.get("brief", "brief:" + x) for x in ("A", "B", "C1", "C2")]), 4)
        self.assertEqual(c.impact(task_c2["id"]), "Still Valid")
        _, _, replacement = self.succeed("C1", "replacement")
        c.select_take("C1", replacement, "human selector")
        self.assertEqual(c.impact(task_c2["id"]), "Must Replan / Rebuild")
        self.assertIn("UPSTREAM_CANONICAL_STATE_MISSING",
                      {r["code"] for r in c.preflight(task_c2["id"]).reasons})
        self.assertEqual(c.take(take_c2)["id"], take_c2)
        self.assertEqual(c.job("job-C2-ready")["status"], "succeeded")
        self.assertEqual(c.get("brief", "brief:C2")["version"], 2)
        self.assertEqual(c.get("brief", "brief:C2", 1)["payload"]["state_in"]["source"], "scene_initial")
        self.assertEqual(task_a["target_model"], "new-h3-video")


if __name__ == "__main__":
    unittest.main()
