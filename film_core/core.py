"""Versioned production objects and an H3 compilation boundary.

All persisted creative objects are immutable versions. Execution and selection changes
are append-only events. SQLite is an embedded relational reference implementation.
"""
import copy
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol


class DomainError(ValueError):
    pass


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(encoded(value).encode("utf-8")).hexdigest()


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class QAResult:
    status: str
    reasons: tuple

    @property
    def ready(self):
        return self.status == "READY"


class H3Adapter(Protocol):
    """Provider boundary; #001 intentionally contains no network implementation."""
    def submit(self, compiled_task, idempotency_key):
        """Return a provider task id and provider response metadata."""

    def poll(self, provider_task_id):
        """Return provider state and response metadata."""


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS objects (
  kind TEXT NOT NULL, id TEXT NOT NULL, version INTEGER NOT NULL,
  source TEXT NOT NULL, status TEXT NOT NULL, payload TEXT NOT NULL,
  created_at TEXT NOT NULL, PRIMARY KEY(kind,id,version)
);
CREATE TABLE IF NOT EXISTS shot_clip (
  clip_id TEXT NOT NULL, shot_id TEXT NOT NULL, ordinal INTEGER NOT NULL,
  shot_start REAL NOT NULL, shot_end REAL NOT NULL,
  clip_start REAL NOT NULL, clip_end REAL NOT NULL, cut_before INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY(clip_id,ordinal), UNIQUE(clip_id,shot_id,shot_start)
);
CREATE TABLE IF NOT EXISTS shot_clip_revisions (
  clip_id TEXT NOT NULL, version INTEGER NOT NULL, mappings TEXT NOT NULL,
  source TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(clip_id,version)
);
CREATE TABLE IF NOT EXISTS dependencies (
  clip_id TEXT NOT NULL, upstream_clip_id TEXT NOT NULL, kind TEXT NOT NULL,
  PRIMARY KEY(clip_id,upstream_clip_id,kind)
);
CREATE TABLE IF NOT EXISTS compiled_tasks (
  id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, brief_id TEXT NOT NULL,
  brief_version INTEGER NOT NULL, profile_id TEXT NOT NULL, profile_version INTEGER NOT NULL,
  compiler_version TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES compiled_tasks(id),
  snapshot TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS job_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT NOT NULL REFERENCES jobs(id),
  status TEXT NOT NULL, metadata TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS takes (
  id TEXT PRIMARY KEY, clip_id TEXT NOT NULL, job_id TEXT NOT NULL REFERENCES jobs(id),
  media_uri TEXT NOT NULL, media_id TEXT, provider_metadata TEXT NOT NULL, test_only INTEGER NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS media_records (
  id TEXT PRIMARY KEY, local_path TEXT NOT NULL, sha256 TEXT NOT NULL,
  size_bytes INTEGER NOT NULL, mime TEXT NOT NULL, duration REAL,
  metadata TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS selections (
  id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT NOT NULL, take_id TEXT NOT NULL REFERENCES takes(id),
  actor TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS observed_states (
  id TEXT PRIMARY KEY, take_id TEXT NOT NULL REFERENCES takes(id),
  payload TEXT NOT NULL, observer TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS state_snapshots (
  id INTEGER PRIMARY KEY AUTOINCREMENT, clip_id TEXT NOT NULL,
  selection_id INTEGER NOT NULL REFERENCES selections(id),
  observed_id TEXT NOT NULL REFERENCES observed_states(id),
  payload TEXT NOT NULL, confirmed_by TEXT NOT NULL, created_at TEXT NOT NULL
);
"""


class Core:
    CREATIVE_KINDS = frozenset({
        "project", "episode", "scene", "character", "character_look", "location",
        "prop", "story_fact", "asset_version", "shot", "clip", "brief",
        "reference_binding", "control_media", "model_profile"
    })
    HANDOFFS = frozenset({"INDEPENDENT", "MULTI_SHOT_ONE_PASS", "STATE_CONTINUE_NEW_VIEW",
                          "VISUAL_ANCHOR", "VIDEO_CONTINUATION", "KEYFRAME_CONSTRAINED"})
    JOB_TRANSITIONS = {
        "queued": {"running", "failed", "cancelled"},
        "running": {"succeeded", "failed", "cancelled"},
        "succeeded": set(), "failed": set(), "cancelled": set(),
    }

    def __init__(self, path=":memory:", test_mode=False):
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(SCHEMA)
        self.test_mode = test_mode

    def close(self):
        self.db.close()

    def put(self, kind, id, payload, source, status="approved"):
        if kind not in self.CREATIVE_KINDS or not id or not source or not isinstance(payload, dict):
            raise DomainError("invalid versioned object")
        previous = self.db.execute(
            "SELECT MAX(version) FROM objects WHERE kind=? AND id=?", (kind, id)).fetchone()[0]
        version = (previous or 0) + 1
        self.db.execute("INSERT INTO objects VALUES (?,?,?,?,?,?,?)",
                        (kind, id, version, source, status, encoded(payload), now()))
        self.db.commit()
        return self.get(kind, id, version)

    def get(self, kind, id, version=None):
        if version is None:
            row = self.db.execute("SELECT * FROM objects WHERE kind=? AND id=? ORDER BY version DESC LIMIT 1",
                                  (kind, id)).fetchone()
        else:
            row = self.db.execute("SELECT * FROM objects WHERE kind=? AND id=? AND version=?",
                                  (kind, id, version)).fetchone()
        if row is None:
            raise DomainError("missing %s %s version %s" % (kind, id, version))
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def map_shot(self, clip_id, shot_id, ordinal, shot_start, shot_end, clip_start, clip_end, cut_before=False):
        clip = self.get("clip", clip_id)["payload"]
        shot = self.get("shot", shot_id)["payload"]
        if not (0 <= shot_start < shot_end <= shot["duration"] and
                0 <= clip_start < clip_end <= clip["duration"] and
                abs((shot_end-shot_start)-(clip_end-clip_start)) < 0.001):
            raise DomainError("invalid shot/clip range")
        if self.db.execute("SELECT 1 FROM shot_clip WHERE clip_id=? AND ordinal=?",
                           (clip_id, ordinal)).fetchone():
            raise DomainError("duplicate clip ordinal")
        self.db.execute("INSERT INTO shot_clip VALUES (?,?,?,?,?,?,?,?)",
                        (clip_id, shot_id, ordinal, shot_start, shot_end, clip_start, clip_end, int(cut_before)))
        self.db.commit()

    def mappings(self, clip_id):
        return [dict(r) for r in self.db.execute(
            "SELECT * FROM shot_clip WHERE clip_id=? ORDER BY ordinal", (clip_id,))]

    def mapping_revision(self, clip_id):
        return self.db.execute("SELECT COALESCE(MAX(version),0) FROM shot_clip_revisions WHERE clip_id=?",
                               (clip_id,)).fetchone()[0]

    def replace_mappings(self, clip_id, mappings, source, expected_revision=None):
        """Replace the live Shot↔Clip plan atomically while preserving prior revisions."""
        clip = self.get("clip", clip_id)["payload"]
        current = self.mappings(clip_id)
        revision = self.mapping_revision(clip_id)
        if expected_revision is not None and expected_revision != revision:
            raise DomainError("mapping revision changed")
        if not source or not isinstance(mappings, list):
            raise DomainError("invalid mapping revision")
        if sorted(m["ordinal"] for m in mappings) != list(range(len(mappings))):
            raise DomainError("mapping ordinals must be consecutive")
        seen = set()
        for m in mappings:
            shot = self.get("shot", m["shot_id"])["payload"]
            if shot.get("scene_id") != clip.get("scene_id"):
                raise DomainError("shot and clip must share scene")
            key = (m["shot_id"], m["shot_start"])
            if key in seen or not (0 <= m["shot_start"] < m["shot_end"] <= shot["duration"] and
                0 <= m["clip_start"] < m["clip_end"] <= clip["duration"] and
                abs((m["shot_end"]-m["shot_start"])-(m["clip_end"]-m["clip_start"])) < 0.001):
                raise DomainError("invalid shot/clip range")
            seen.add(key)
        try:
            if revision == 0 and current:
                revision = 1
                self.db.execute("INSERT INTO shot_clip_revisions VALUES (?,?,?,?,?)",
                                (clip_id, revision, encoded(current), "pre-website-plan", now()))
            new_revision = revision + 1
            self.db.execute("DELETE FROM shot_clip WHERE clip_id=?", (clip_id,))
            for m in mappings:
                self.db.execute("INSERT INTO shot_clip VALUES (?,?,?,?,?,?,?,?)", (
                    clip_id, m["shot_id"], m["ordinal"], m["shot_start"], m["shot_end"],
                    m["clip_start"], m["clip_end"], int(bool(m.get("cut_before")))))
            self.db.execute("INSERT INTO shot_clip_revisions VALUES (?,?,?,?,?)",
                            (clip_id, new_revision, encoded(self.mappings(clip_id)), source, now()))
            self.db.commit()
            return {"version": new_revision, "mappings": self.mappings(clip_id)}
        except Exception:
            self.db.rollback()
            raise

    def add_dependency(self, clip_id, upstream_clip_id, kind):
        if kind not in {"STATE_CONTINUITY", "VISUAL_ANCHOR", "VIDEO_CONTINUATION"}:
            raise DomainError("invalid dependency")
        self.get("clip", clip_id)
        self.get("clip", upstream_clip_id)
        self.db.execute("INSERT INTO dependencies VALUES (?,?,?)", (clip_id, upstream_clip_id, kind))
        self.db.commit()

    def save_brief(self, clip_id, payload, source="production-plan", status="approved"):
        self.get("clip", clip_id)
        if payload.get("clip_id") != clip_id:
            raise DomainError("brief clip mismatch")
        return self.put("brief", "brief:" + clip_id, payload, source, status)

    def rebase_brief_state(self, clip_id, upstream_clip_id, source="canonical-context-assembly"):
        """Explicit production revision; prior Brief versions remain immutable."""
        dep = self.db.execute(
            "SELECT 1 FROM dependencies WHERE clip_id=? AND upstream_clip_id=?",
            (clip_id, upstream_clip_id)).fetchone()
        if not dep:
            raise DomainError("upstream clip is not a declared dependency")
        payload = copy.deepcopy(self.get("brief", "brief:" + clip_id)["payload"])
        payload["state_in"] = self.next_clip_context(upstream_clip_id)
        payload["provenance"]["state_in"] = {
            "authority": "DERIVED", "source_snapshot_id": payload["state_in"]["snapshot_id"]}
        return self.save_brief(clip_id, payload, source)

    def brief_qa(self, brief):
        p = brief["payload"]
        reasons = []
        def need(field, code=None):
            if not p.get(field):
                reasons.append({"code": code or "MISSING_FIELD", "field": field})
        for field in ("purpose", "scene_id", "shot_timeline", "subjects", "environment",
                      "state_in", "action_process", "performance", "camera", "sound",
                      "planned_state_out", "handoff", "provenance"):
            need(field)
        if not isinstance(p.get("duration"), (int, float)) or p["duration"] <= 0:
            reasons.append({"code": "INVALID_DURATION", "field": "duration"})
        try:
            clip = self.get("clip", p["clip_id"])
            self.get("scene", p["scene_id"])
            if abs(p.get("duration", -1) - clip["payload"]["duration"]) > 0.001:
                reasons.append({"code": "DURATION_CLIP_MISMATCH", "field": "duration"})
            mapped = self.mappings(p["clip_id"])
            timeline = p.get("shot_timeline", [])
            if not mapped or len(mapped) != len(timeline) or any(
                    m["shot_id"] != t.get("shot_id") or m["clip_start"] != t.get("start") or
                    m["clip_end"] != t.get("end") or bool(m["cut_before"]) != bool(t.get("cut_before"))
                    for m, t in zip(mapped, timeline)):
                reasons.append({"code": "SHOT_TIMELINE_MISMATCH", "field": "shot_timeline"})
            if mapped and (mapped[0]["clip_start"] != 0 or
                           abs(mapped[-1]["clip_end"] - clip["payload"]["duration"]) > 0.001 or
                           any(abs(left["clip_end"] - right["clip_start"]) > 0.001
                               for left, right in zip(mapped, mapped[1:]))):
                reasons.append({"code": "SHOT_TIMELINE_GAP_OR_OVERLAP", "field": "shot_timeline"})
            for m in mapped:
                shot = self.get("shot", m["shot_id"])
                if shot["status"] != "approved":
                    reasons.append({"code": "SHOT_NOT_APPROVED", "field": m["shot_id"]})
                matching = next((t for t in timeline if t.get("shot_id") == m["shot_id"]), None)
                if not matching or matching.get("description") != shot["payload"].get("description"):
                    reasons.append({"code": "SHOT_INTENT_MISMATCH", "field": m["shot_id"]})
        except (DomainError, KeyError, TypeError):
            reasons.append({"code": "UNRESOLVED_SOURCE", "field": "scene_id/clip_id"})
        if p.get("handoff") not in self.HANDOFFS:
            reasons.append({"code": "INVALID_HANDOFF", "field": "handoff"})
        if p.get("state_in", {}).get("source") not in {"canonical_snapshot", "scene_initial"}:
            reasons.append({"code": "STATE_IN_NOT_RECONSTRUCTABLE", "field": "state_in"})
        for subject in p.get("subjects", []):
            try:
                self.get("character", subject["character_id"])
                self.get("character_look", subject["look_id"])
            except (DomainError, KeyError, TypeError):
                reasons.append({"code": "UNRESOLVED_SUBJECT", "field": "subjects"})
        for action in p.get("action_process", []):
            if not all(action.get(k) for k in ("initial", "trigger", "development", "result")):
                reasons.append({"code": "ACTION_NOT_PROCESS", "field": "action_process"})
        if p.get("performance") and not any(p["performance"].get(k) for k in
                                            ("gaze", "breath", "gesture", "posture", "pause", "reaction")):
            reasons.append({"code": "ABSTRACT_PERFORMANCE", "field": "performance"})
        if p.get("camera") and not all(p["camera"].get(k) for k in ("framing", "movement")):
            reasons.append({"code": "CAMERA_UNCLEAR", "field": "camera"})
        if p.get("sound") and "diegetic" not in p["sound"]:
            reasons.append({"code": "SOUND_RELATION_UNCLEAR", "field": "sound"})
        for ref_id in p.get("references", []):
            try:
                ref = self.get("reference_binding", ref_id)["payload"]
                if not ref.get("role"):
                    reasons.append({"code": "REFERENCE_ROLE_MISSING", "field": ref_id})
                if ref.get("asset_id"):
                    self.get("asset_version", ref["asset_id"])
                elif ref.get("control_media_id"):
                    self.get("control_media", ref["control_media_id"])
                else:
                    reasons.append({"code": "REFERENCE_SOURCE_MISSING", "field": ref_id})
            except DomainError:
                reasons.append({"code": "REFERENCE_MISSING", "field": ref_id})
            except KeyError:
                reasons.append({"code": "REFERENCE_ASSET_MISSING", "field": ref_id})
        if not isinstance(p.get("locked_constraints", []), list):
            reasons.append({"code": "INVALID_LOCKED_CONSTRAINTS", "field": "locked_constraints"})
        state_in = p.get("state_in", {}).get("facts", {})
        state_out = p.get("planned_state_out", {})
        for key in ("character_id", "look_id"):
            if state_in.get(key) and state_out.get(key) and state_in[key] != state_out[key]:
                reasons.append({"code": "CONTINUITY_CONFLICT", "field": key})
        return QAResult("READY" if not reasons else "NOT_READY", tuple(reasons))

    def _task_payload(self, brief, profile, task_id, aspect_ratio, parameters, continuation):
        p = brief["payload"]
        ref_objects = [self.get("reference_binding", rid) for rid in p.get("references", [])]
        refs = [{"id": ref["id"], "version": ref["version"], **ref["payload"]}
                for ref in ref_objects]
        control = None
        if continuation and continuation.get("control_media_id"):
            control_object = self.get("control_media", continuation["control_media_id"])
            control = {"id": control_object["id"], "version": control_object["version"],
                       "payload": control_object["payload"]}
        # Deterministic serialization: the compiler never authors new story facts.
        sections = {
            "subject_definitions": p["subjects"],
            "summary": ("[video continuation] " if p["handoff"] == "VIDEO_CONTINUATION" else "") + p["purpose"],
            "retention_analysis": p.get("locked_constraints", []),
            "detailed_description": {k: p.get(k) for k in (
                "shot_timeline", "environment", "props", "state_in", "action_process",
                "performance", "camera", "constraints", "planned_state_out", "handoff")},
            "overall_soundscape": p["sound"],
            "non_diegetic_music": p["sound"].get("music"),
        }
        semantic = {k: p.get(k) for k in (
            "purpose", "shot_timeline", "subjects", "environment", "props", "state_in",
            "action_process", "performance", "camera", "sound", "constraints",
            "locked_constraints", "planned_state_out", "handoff")}
        if not refs and not continuation:
            sections = {
                "integrated_multimodal_description": {
                    "purpose": p["purpose"], "shot_timeline": p["shot_timeline"],
                    "subjects": p["subjects"], "environment": p["environment"],
                    "props": p.get("props"), "state_in": p["state_in"],
                    "action_process": p["action_process"], "performance": p["performance"],
                    "camera": p["camera"], "constraints": p.get("constraints"),
                    "locked_constraints": p.get("locked_constraints"),
                    "planned_state_out": p["planned_state_out"]},
                "overall_soundscape": p["sound"],
                "non_diegetic_music": p["sound"].get("music"),
            }
        prompt = self._render_h3_prompt(p, sections, refs, continuation)
        return {
            "id": task_id, "clip_id": p["clip_id"], "target_model": profile["payload"]["model_id"],
            "task_mode": p["handoff"], "compiled_prompt": prompt, "sections": sections,
            "media_bindings": refs, "duration": p["duration"], "aspect_ratio": aspect_ratio,
            "continuation": continuation, "parameters": parameters,
            "control_media_snapshot": control,
            "source_brief": {"id": brief["id"], "version": brief["version"]},
            "compiler_version": "h3-compiler/0.1", "model_profile": {
                "id": profile["id"], "version": profile["version"]},
            "model_profile_snapshot": profile["payload"],
            "semantic_hash": digest(semantic), "source_semantics": semantic,
            "reference_versions": [ref["version"] for ref in ref_objects]
        }

    def _render_h3_prompt(self, p, sections, refs, continuation):
        """Deterministic text rendering from approved Brief fields; no story invention."""
        location = self.get("location", p["environment"]["location_id"])["payload"]["identity"]
        def visible_state(state):
            facts = state.get("facts", state)
            labels = {"letter_state": "信件状态", "prop_holder": "持信者", "position": "位置",
                      "gaze": "视线", "orientation": "朝向", "emotion": "情绪余韵"}
            parts = []
            for key, value in facts.items():
                if key in {"character_id", "look_id", "location_id"}:
                    continue
                if key == "crying":
                    parts.append("哭泣" if value else "没有哭泣，眼睛无泪")
                else:
                    parts.append(labels.get(key, key) + "：" + str(value))
            return "；".join(parts)
        subject_lines = []
        for subject in p["subjects"]:
            person = self.get("character", subject["character_id"])["payload"]
            look = self.get("character_look", subject["look_id"])["payload"]
            subject_lines.append(person["name"] + " — " + look["description"])
        prop_lines = []
        for prop in p.get("props", []):
            identity = self.get("prop", prop["prop_id"])["payload"]["identity"]
            prop_lines.append(identity + " — " + str(prop.get("state", "")))
        shot_lines = []
        for index, shot in enumerate(p["shot_timeline"], 1):
            cut = "CUT. " if shot.get("cut_before") else ""
            source_range = ("; source Shot %.2f–%.2fs" % (shot["shot_start"], shot["shot_end"])
                            if "shot_start" in shot and "shot_end" in shot else "")
            shot_lines.append("[Shot %d | %.2f–%.2fs%s] %s%s" % (
                index, shot["start"], shot["end"], source_range, cut, shot["description"]))
        action_lines = [" → ".join(str(action[key]) for key in
                        ("initial", "trigger", "development", "result"))
                        for action in p["action_process"]]
        detail = [
            "Purpose: " + p["purpose"],
            "Setting: " + location + "；" + "；".join(
                ("窗外持续下雨" if value else "无雨") if key == "rain" else
                ("夜晚" if value == "night" else str(value))
                for key, value in p["environment"].items() if key != "location_id"),
            "Subjects: " + "；".join(subject_lines),
            "Props: " + "；".join(prop_lines),
            "State in: " + visible_state(p["state_in"]),
            *shot_lines,
            "Action process: " + "；".join(action_lines),
            "Observable performance: " + "；".join(str(value) for value in p["performance"].values()),
            "Camera: " + "；".join(str(value) for value in p["camera"].values()),
            "Constraints: " + "；".join(p.get("constraints", [])),
            "Locked: " + "；".join(p.get("locked_constraints", [])),
            "Planned state out: " + visible_state(p["planned_state_out"]),
        ]
        sound = str(p["sound"].get("diegetic", ""))
        music = str(p["sound"].get("music", ""))
        if "integrated_multimodal_description" in sections:
            return ("integrated_multimodal_description:\n" + "\n".join(detail) +
                    "\noverall_soundscape: " + sound + "\nnon_diegetic_music: " + music)
        labels = []
        picture = video = audio = 0
        for ref in refs:
            if ref["media_type"] == "image":
                picture += 1
                label = "<Picture %d>" % picture
            elif ref["media_type"] == "video":
                video += 1
                label = "<Video %d>" % video
            else:
                audio += 1
                label = "<Audio %d>" % audio
            labels.append(label + " — " + ref["role"] + " from " + ref["id"])
        if continuation:
            video += 1
            labels.append("<Video %d> — selected previous Clip Stable Tail; continuation source" % video)
        summary = ("[video continuation] " if p["handoff"] == "VIDEO_CONTINUATION" else
                   "[reference generation] ") + p["purpose"]
        return ("subject_definitions:\n" + "\n".join(subject_lines + labels) +
                "\nsummary: " + summary +
                "\nretention_analysis: " + "；".join(p.get("locked_constraints", [])) +
                "\ndetailed_description:\n" + "\n".join(detail) +
                "\noverall_soundscape: " + sound + "\nnon_diegetic_music: " + music)

    def compile_h3(self, task_id, brief_id, profile_id, aspect_ratio=None, parameters=None,
                   continuation=None, brief_version=None, profile_version=None):
        brief = self.get("brief", brief_id, brief_version)
        profile = self.get("model_profile", profile_id, profile_version)
        qa = self.brief_qa(brief)
        if not qa.ready:
            raise DomainError("brief QA failed: " + encoded(qa.reasons))
        if profile["payload"].get("family") != "H3":
            raise DomainError("wrong model family")
        if self.db.execute("SELECT 1 FROM compiled_tasks WHERE id=?", (task_id,)).fetchone():
            raise DomainError("task id already exists")
        scene = self.get("scene", brief["payload"]["scene_id"])["payload"]
        episode = self.get("episode", scene["episode_id"])["payload"]
        project_ratio = self.get("project", episode["project_id"])["payload"].get("aspect_ratio")
        if not project_ratio or (aspect_ratio is not None and aspect_ratio != project_ratio):
            raise DomainError("aspect ratio must come from Project decision")
        aspect_ratio = project_ratio
        task = self._task_payload(brief, profile, task_id, aspect_ratio, parameters or {}, continuation)
        if digest(task["source_semantics"]) != task["semantic_hash"]:
            raise DomainError("compilation fidelity failure")
        for constraint in brief["payload"].get("locked_constraints", []):
            if constraint not in task["compiled_prompt"]:
                raise DomainError("locked constraint lost")
        self.db.execute("INSERT INTO compiled_tasks VALUES (?,?,?,?,?,?,?,?,?)",
                        (task_id, task["clip_id"], brief["id"], brief["version"], profile["id"],
                         profile["version"], task["compiler_version"], encoded(task), now()))
        self.db.commit()
        return task

    def task(self, task_id):
        row = self.db.execute("SELECT payload FROM compiled_tasks WHERE id=?", (task_id,)).fetchone()
        if not row:
            raise DomainError("task missing")
        return json.loads(row["payload"])

    def selection(self, clip_id):
        row = self.db.execute("SELECT * FROM selections WHERE clip_id=? ORDER BY id DESC LIMIT 1",
                              (clip_id,)).fetchone()
        return dict(row) if row else None

    def preflight(self, task_id, retry_of=None):
        task = self.task(task_id)
        if retry_of:
            previous = self.job(retry_of)
            original = previous["snapshot"].get("task")
            if (previous["status"] != "failed" or not isinstance(original, dict) or
                    self.task(previous["task_id"]) != original or
                    {**original, "id": task_id} != task):
                raise DomainError("technical retry requires unchanged original failed Job inputs")
            try:
                for kind, source in (("brief", task["source_brief"]),
                                     ("model_profile", task["model_profile"])):
                    if not isinstance(source["version"], int) or source["version"] < 1:
                        raise DomainError("original version missing")
                    self.get(kind, source["id"], source["version"])
                for binding in task["media_bindings"]:
                    if not isinstance(binding["version"], int) or binding["version"] < 1:
                        raise DomainError("original reference version missing")
                    reference = self.get("reference_binding", binding["id"], binding["version"])
                    if {"id": reference["id"], "version": reference["version"], **reference["payload"]} != binding:
                        raise DomainError("original reference snapshot mismatch")
            except (DomainError, KeyError, TypeError):
                raise DomainError("technical retry original inputs unavailable; use Creative Regenerate") from None
        profile = self.get("model_profile", task["model_profile"]["id"],
                           task["model_profile"]["version"])["payload"]
        reasons = []
        def fail(code, field):
            reasons.append({"code": code, "field": field})
        if retry_of and task.get("model_profile_snapshot") != profile:
            fail("RETRY_PROFILE_SNAPSHOT_MISMATCH", "model_profile")
        if not retry_of and self.get("brief", task["source_brief"]["id"])["version"] != task["source_brief"]["version"]:
            fail("BRIEF_VERSION_STALE", "source_brief")
        if not retry_of and self.get("model_profile", task["model_profile"]["id"])["version"] != task["model_profile"]["version"]:
            fail("PROFILE_VERSION_STALE", "model_profile")
        for binding in task["media_bindings"]:
            if not retry_of and self.get("reference_binding", binding["id"])["version"] != binding["version"]:
                fail("REFERENCE_VERSION_STALE", binding["id"])
        if task["task_mode"] not in profile.get("supported_modes", []):
            fail("MODE_UNVERIFIED_OR_UNSUPPORTED", "task_mode")
        envelope = profile.get("duration_envelope")
        if not envelope or not envelope.get("verified"):
            fail("DURATION_UNVERIFIED", "duration")
        elif not isinstance(task["duration"], int) or not envelope["min"] <= task["duration"] <= envelope["max"]:
            fail("DURATION_OUT_OF_RANGE", "duration")
        media = profile.get("media_capability") or {}
        if not media.get("verified"):
            fail("MEDIA_CAPABILITY_UNVERIFIED", "media_bindings")
        else:
            if len(task["media_bindings"]) > media.get("max_references", 0):
                fail("REFERENCE_COUNT_EXCEEDED", "media_bindings")
            for binding in task["media_bindings"]:
                if binding.get("media_type") not in media.get("types", []):
                    fail("REFERENCE_TYPE_UNSUPPORTED", "media_bindings")
                if not binding.get("role") or not (binding.get("asset_id") or binding.get("control_media_id")):
                    fail("INVALID_REFERENCE_BINDING", "media_bindings")
                try:
                    source = (self.get("asset_version", binding["asset_id"],
                                       binding.get("asset_version") if retry_of else None)["payload"]
                              if binding.get("asset_id") else
                              self.get("control_media", binding["control_media_id"])["payload"])
                    if not binding.get("uri") and not source.get("uri"):
                        fail("MISSING_REFERENCE_MEDIA", binding["id"])
                except DomainError:
                    fail("MISSING_REFERENCE_MEDIA", binding["id"])
                if binding.get("control_media_id"):
                    try:
                        control = self.get("control_media", binding["control_media_id"])["payload"]
                        source_take = self.take(control["source_take_id"])
                        selected = self.selection(source_take["clip_id"])
                        if (not selected or selected["take_id"] != source_take["id"] or
                                selected["id"] != control.get("source_selection_id")):
                            fail("STALE_VISUAL_ANCHOR", binding["id"])
                    except (DomainError, KeyError):
                        fail("INVALID_CONTROL_MEDIA", binding["id"])
        parameter_capability = profile.get("parameter_capability") or {}
        if not parameter_capability.get("verified"):
            fail("PARAMETERS_UNVERIFIED", "parameters")
        else:
            for key, value in task["parameters"].items():
                rule = parameter_capability.get("allowed", {}).get(key)
                if rule is None or value not in rule:
                    fail("INVALID_GENERATION_PARAMETER", key)
            for key in parameter_capability.get("required", []):
                if key not in task["parameters"]:
                    fail("REQUIRED_PARAMETER_MISSING", key)
        if task["aspect_ratio"] not in profile.get("aspect_ratios", []):
            fail("ASPECT_RATIO_UNVERIFIED_OR_UNSUPPORTED", "aspect_ratio")
        required_sections = (profile.get("compilation_requirements", {}).get("base_sections", [])
                             if not task["media_bindings"] and not task["continuation"] else
                             profile.get("compilation_requirements", {}).get("required_sections", []))
        for required in required_sections:
            if required not in task["sections"] or task["sections"][required] is None:
                fail("COMPILED_SECTION_MISSING", required)
        if task["source_semantics"].get("sound"):
            audio = profile.get("audio_capability") or {}
            if not audio.get("verified"):
                fail("AUDIO_CAPABILITY_UNVERIFIED", "sound")
        if digest(task["source_semantics"]) != task["semantic_hash"]:
            fail("FIDELITY_HASH_MISMATCH", "source_semantics")
        dependencies = list(self.db.execute(
            "SELECT upstream_clip_id,kind FROM dependencies WHERE clip_id=?", (task["clip_id"],)))
        for dependency in dependencies:
            upstream_id = dependency["upstream_clip_id"]
            try:
                context = self.next_clip_context(upstream_id)
            except DomainError:
                fail("UPSTREAM_CANONICAL_STATE_MISSING", "state_in")
                continue
            if task["source_semantics"]["state_in"] != context:
                fail("STATE_CONTEXT_STALE_OR_MISSING", "state_in")
        if task["task_mode"] == "VIDEO_CONTINUATION":
            temporal = profile.get("temporal_controls") or {}
            if not temporal.get("verified") or not temporal.get("video_continuation"):
                fail("VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED", "task_mode")
            dep = self.db.execute("SELECT upstream_clip_id FROM dependencies WHERE clip_id=? AND kind=?",
                                  (task["clip_id"], "VIDEO_CONTINUATION")).fetchone()
            if not dep:
                fail("CONTINUATION_DEPENDENCY_MISSING", "continuation")
            else:
                current = self.selection(dep["upstream_clip_id"])
                if not current:
                    fail("UPSTREAM_SELECTION_MISSING", "continuation")
                elif not task["continuation"]:
                    fail("CONTINUATION_SOURCE_MISSING", "continuation")
                else:
                    con = task["continuation"]
                    if con.get("selection_id") != current["id"] or con.get("take_id") != current["take_id"]:
                        fail("STALE_UPSTREAM_SELECTION", "continuation")
                    try:
                        control = self.get("control_media", con["control_media_id"])["payload"]
                        if control.get("role") != "stable_tail" or control.get("source_take_id") != current["take_id"]:
                            fail("INVALID_STABLE_TAIL", "continuation")
                        if not task.get("control_media_snapshot") or (
                                task["control_media_snapshot"]["payload"] != control):
                            fail("CONTROL_MEDIA_SNAPSHOT_MISMATCH", "continuation")
                    except (DomainError, KeyError):
                        fail("CONTROL_MEDIA_MISSING", "continuation")
        else:
            if task["continuation"]:
                fail("UNEXPECTED_CONTINUATION", "continuation")
        return QAResult("READY" if not reasons else "NOT_READY", tuple(reasons))

    def create_job(self, job_id, task_id, retry_of=None, cost_estimate=None):
        result = self.preflight(task_id, retry_of=retry_of)
        if not result.ready:
            raise DomainError("preflight failed: " + encoded(result.reasons))
        task = self.task(task_id)
        if retry_of:
            self.job(retry_of)
        snapshot = {"task": task, "retry_of": retry_of, "cost_estimate": cost_estimate}
        self.db.execute("INSERT INTO jobs VALUES (?,?,?,?)", (job_id, task_id, encoded(snapshot), now()))
        self.db.execute("INSERT INTO job_events(job_id,status,metadata,created_at) VALUES (?,?,?,?)",
                        (job_id, "queued", "{}", now()))
        self.db.commit()
        return self.job(job_id)

    def job(self, job_id):
        row = self.db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise DomainError("job missing")
        event = self.db.execute("SELECT * FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT 1",
                                (job_id,)).fetchone()
        result = dict(row)
        result["snapshot"] = json.loads(result["snapshot"])
        result["status"] = event["status"]
        result["metadata"] = json.loads(event["metadata"])
        return result

    def job_event(self, job_id, status, metadata=None):
        job = self.job(job_id)
        if status not in self.JOB_TRANSITIONS[job["status"]]:
            raise DomainError("invalid job transition")
        self.db.execute("INSERT INTO job_events(job_id,status,metadata,created_at) VALUES (?,?,?,?)",
                        (job_id, status, encoded(metadata or {}), now()))
        self.db.commit()
        return self.job(job_id)

    def register_media(self, media_id, local_path, sha256, size_bytes, mime, duration=None, metadata=None):
        from pathlib import Path
        path = Path(local_path)
        if not path.is_file() or not sha256 or size_bytes <= 0 or not mime:
            raise DomainError("managed media must exist with integrity metadata")
        if path.stat().st_size != size_bytes or hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
            raise DomainError("managed media size or checksum mismatch")
        self.db.execute("INSERT INTO media_records VALUES (?,?,?,?,?,?,?,?)",
                        (media_id, local_path, sha256, size_bytes, mime, duration,
                         encoded(metadata or {}), now()))
        self.db.commit()

    def media(self, media_id):
        row = self.db.execute("SELECT * FROM media_records WHERE id=?", (media_id,)).fetchone()
        if not row:
            raise DomainError("media record missing")
        result = dict(row)
        result["metadata"] = json.loads(result["metadata"])
        return result

    def record_take(self, take_id, job_id, media_uri, provider_metadata=None, test_only=False, media_id=None):
        job = self.job(job_id)
        if job["status"] != "succeeded" or not media_uri:
            raise DomainError("take requires succeeded job and media")
        if test_only and not self.test_mode:
            raise DomainError("test take forbidden outside test mode")
        if not test_only and (not media_id or self.media(media_id)["local_path"] != media_uri):
            raise DomainError("real take requires managed media record")
        clip_id = job["snapshot"]["task"]["clip_id"]
        self.db.execute("INSERT INTO takes VALUES (?,?,?,?,?,?,?,?)",
                        (take_id, clip_id, job_id, media_uri, media_id, encoded(provider_metadata or {}),
                         int(test_only), now()))
        self.db.commit()
        return self.take(take_id)

    def take(self, take_id):
        row = self.db.execute("SELECT * FROM takes WHERE id=?", (take_id,)).fetchone()
        if not row:
            raise DomainError("take missing")
        return dict(row)

    def select_take(self, clip_id, take_id, actor):
        take = self.take(take_id)
        if take["clip_id"] != clip_id or not actor:
            raise DomainError("selection clip mismatch or missing actor")
        self.db.execute("INSERT INTO selections(clip_id,take_id,actor,created_at) VALUES (?,?,?,?)",
                        (clip_id, take_id, actor, now()))
        self.db.commit()
        return self.selection(clip_id)

    def observe(self, observed_id, take_id, state, observer):
        self.take(take_id)
        if not state or not observer:
            raise DomainError("invalid observation")
        self.db.execute("INSERT INTO observed_states VALUES (?,?,?,?,?)",
                        (observed_id, take_id, encoded(state), observer, now()))
        self.db.commit()

    def confirm_state(self, clip_id, observed_id, confirmed_by):
        selection = self.selection(clip_id)
        row = self.db.execute("SELECT * FROM observed_states WHERE id=?", (observed_id,)).fetchone()
        if not selection or not row or row["take_id"] != selection["take_id"] or not confirmed_by:
            raise DomainError("canonical state requires selected take and human confirmation")
        self.db.execute("INSERT INTO state_snapshots(clip_id,selection_id,observed_id,payload,confirmed_by,created_at) VALUES (?,?,?,?,?,?)",
                        (clip_id, selection["id"], observed_id, row["payload"], confirmed_by, now()))
        self.db.commit()
        return self.snapshot(clip_id)

    def snapshot(self, clip_id):
        row = self.db.execute("SELECT * FROM state_snapshots WHERE clip_id=? ORDER BY id DESC LIMIT 1",
                              (clip_id,)).fetchone()
        if not row:
            raise DomainError("canonical snapshot missing")
        result = dict(row)
        result["payload"] = json.loads(result["payload"])
        return result

    def next_clip_context(self, upstream_clip_id):
        snapshot = self.snapshot(upstream_clip_id)
        current = self.selection(upstream_clip_id)
        if snapshot["selection_id"] != current["id"]:
            raise DomainError("canonical snapshot needs reconfirmation after selection change")
        return {"source": "canonical_snapshot", "snapshot_id": snapshot["id"],
                "facts": snapshot["payload"]}

    def create_stable_tail(self, control_id, upstream_clip_id, take_id, uri, assessment, source="human-review"):
        current = self.selection(upstream_clip_id)
        if not current or current["take_id"] != take_id or not uri or not assessment.get("stable"):
            raise DomainError("stable tail requires selected take and positive assessment")
        return self.put("control_media", control_id, {"role": "stable_tail", "source_take_id": take_id,
                                                     "uri": uri, "assessment": assessment}, source)

    def continuation_source(self, upstream_clip_id, control_id):
        selection = self.selection(upstream_clip_id)
        if not selection:
            raise DomainError("upstream selection missing")
        control = self.get("control_media", control_id)["payload"]
        if control.get("source_take_id") != selection["take_id"] or control.get("role") != "stable_tail":
            raise DomainError("stable tail does not match current selection")
        return {"selection_id": selection["id"], "take_id": selection["take_id"],
                "control_media_id": control_id}

    def impact(self, task_id):
        result = self.preflight(task_id)
        codes = {r["code"] for r in result.reasons}
        if codes.intersection({"STALE_UPSTREAM_SELECTION", "STALE_VISUAL_ANCHOR", "BRIEF_VERSION_STALE"}):
            return "Must Replan / Rebuild"
        if result.ready:
            return "Still Valid"
        return "Needs Reconfirmation"
