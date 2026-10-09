#!/usr/bin/env python3
"""Explicit, single-job commands for the #002 real H3 vertical slice.

No automatic retries or background polling. Paid submissions require --submit-one.
The secret is read from stdin into this process only and never printed or persisted.
"""
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError, darl_execution_model
from film_core.fixture import seed
from film_core.h3_profile import LOCAL_H3_MODEL, H3_EXECUTION_MODELS, H3_PROFILE_IDS, current_h3_execution_model, darl_h3_profile
from apps.api.job_runtime import generation_provider

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / "output" / "h3-002-2026-10-09"
DB = RUN / "production.sqlite"
PROFILE_ID = "h3-darl"
PARAMETERS = {"resolution": "480P", "num_inference_steps": 20,
              "turbo": False, "watermark": False}


def core_open():
    if not DB.is_file():
        raise DomainError("run 'prepare' first")
    return Core(str(DB))


def credential_adapter():
    key = sys.stdin.readline().strip()
    if not key:
        raise DomainError("NEEDS_CREDENTIALS: provide DARL_API_KEY on stdin")
    os.environ["DARL_API_KEY"] = key
    return DarlH3Adapter()


def prepare():
    if DB.exists():
        raise DomainError("run already exists; refusing to reseed")
    RUN.mkdir(parents=True, exist_ok=True)
    core = seed(Core(str(DB)), production=True)
    core.put("model_profile", PROFILE_ID, darl_h3_profile(False),
             "official-and-Darl-docs-2026-10-09", "documented")
    print(json.dumps({"status": "PREPARED", "database": str(DB),
                      "project_ratio": core.get("project", "station-film")["payload"]["aspect_ratio"],
                      "A_brief_qa": core.brief_qa(core.get("brief", "brief:A")).status}, ensure_ascii=False))
    core.close()


def submit_one(clip, adapter, technical_retry_of=None, backend_repaired=False):
    core = core_open()
    previous = None
    prior = core.db.execute("SELECT COUNT(*) FROM jobs WHERE task_id IN (SELECT id FROM compiled_tasks WHERE clip_id=?)",
                            (clip,)).fetchone()[0]
    if prior or technical_retry_of:
        if not technical_retry_of or not backend_repaired or prior >= 2:
            raise DomainError("cost guard: retry requires explicit failed Job and repaired backend; max two attempts")
        previous = core.job(technical_retry_of)
        if previous["status"] != "failed" or previous["snapshot"]["task"]["clip_id"] != clip:
            raise DomainError("technical retry source must be a failed Job for the same Clip")
        generation_provider(previous)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    job_id = "job-" + clip + "-" + stamp
    if previous:
        task_id = previous['task_id']
        task = core.task(task_id)
        execution_model = darl_execution_model(previous['snapshot']['task'])
        if execution_model == LOCAL_H3_MODEL and os.getenv('H3_SERVER_ON') != '1':
            raise DomainError('EXECUTION_MODEL_UNAVAILABLE: technical retry cannot switch execution model')
    else:
        execution_model = current_h3_execution_model()
        profile_id = H3_PROFILE_IDS[execution_model]
        try:
            profile = core.get('model_profile', profile_id)['payload']
        except DomainError:
            profile = darl_h3_profile(execution_model=execution_model)
            core.put('model_profile', profile_id, profile, 'darl-routing', 'documented')
        if profile['model_id'] != execution_model:
            raise DomainError('Darl execution model profile mismatch')
        if profile.get('provider') != 'darl' or profile.get('execution_model') != execution_model:
            core.put('model_profile', profile_id, {**profile, 'provider': 'darl', 'execution_model': execution_model},
                     'darl-routing', 'documented')
        task_id = "task-" + clip + "-" + stamp
        continuation = core.continuation_source("C1", "tail-C1") if clip == 'C2' else None
        task = core.compile_h3(task_id, "brief:" + clip, profile_id,
                               parameters=PARAMETERS, continuation=continuation)
    check = core.preflight(task_id, retry_of=technical_retry_of)
    if not check.ready:
        raise DomainError("preflight failed: " + json.dumps(check.reasons, ensure_ascii=False))
    # Official public rate is only an estimate; this self-hosted proxy may bill differently.
    input_seconds = (float(core.get("control_media", "tail-C1")["payload"].get("duration", 0))
                     if clip == "C2" else 0)
    estimate = {"reference_rate": "MiniMax official 768P $0.08/output second plus video input",
                "estimated_usd": round((task["duration"] + input_seconds) * 0.08, 2),
                "proxy_actual_rate": "unknown", "candidate_limit": 1,
                "provider": "darl", "execution_model": execution_model,
                "attempt_kind": "technical_retry" if technical_retry_of else "initial"}
    body = adapter.build_request(task)
    if body["model"] != execution_model:
        raise DomainError("model mismatch")
    if clip == "A" and len(body["content"]) != 1:
        raise DomainError("Clip A must be T2VA with one text item")
    if clip == "B" and any(item.get("role") == "reference_video" for item in body["content"]):
        raise DomainError("Clip B must not use video continuation")
    core.create_job(job_id, task_id, retry_of=technical_retry_of, cost_estimate=estimate)
    try:
        response = adapter.submit(task, job_id)
    except ProviderError as exc:
        core.job_event(job_id, "failed", {"provider": "darl", "execution_model": execution_model,
                                           "provider_error": exc.as_dict(),
                                           "note": "no automatic resubmit; uncertain network result needs manual audit"})
        raise
    core.job_event(job_id, "running", {"provider": "darl", "execution_model": execution_model,
                                        "provider_task_id": response["id"],
                                        "create_response": response,
                                        "request_summary": {"model": body["model"], "duration": body["duration"],
                                                            "ratio": body["ratio"], "resolution": body["resolution"],
                                                            "steps": body["num_inference_steps"],
                                                            "media_count": len(body["content"]) - 1}})
    print(json.dumps({"status": "SUBMITTED", "clip": clip, "job_id": job_id,
                      "task_id": task_id, "provider_task_id": response["id"],
                      "cost_estimate": estimate, "technical_retry_of": technical_retry_of,
                      "expected_minutes": 3}, ensure_ascii=False))
    core.close()


def accept_clip(clip, take_id, state_file, actor):
    core = core_open()
    take = core.take(take_id)
    if take["clip_id"] != clip or take["test_only"] or not Path(take["media_uri"]).is_file():
        raise DomainError("human gate requires a real downloaded Take for this Clip")
    state = json.loads(Path(state_file).read_text())
    required = {"character_id", "look_id", "location_id", "letter_state", "crying", "position"}
    if not required.issubset(state):
        raise DomainError("observed state missing core continuity fields")
    selection = core.select_take(clip, take_id, actor)
    observed_id = "observed-" + take_id
    core.observe(observed_id, take_id, state, actor + " with review assistance")
    snapshot = core.confirm_state(clip, observed_id, actor)
    print(json.dumps({"status": "SELECTED_CANONICAL", "clip": clip, "take_id": take_id,
                      "selection_id": selection["id"], "snapshot_id": snapshot["id"]}, ensure_ascii=False))
    core.close()


def make_anchor(upstream, target, second, assessment):
    core = core_open()
    selection = core.selection(upstream)
    if not selection:
        raise DomainError("visual anchor requires selected upstream Take")
    core.next_clip_context(upstream)
    take = core.take(selection["take_id"])
    if take["test_only"]:
        raise DomainError("test Take cannot source real anchor")
    path = RUN / ("anchor-" + upstream + "-" + target + ".png")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(second),
                    "-i", take["media_uri"], "-frames:v", "1", str(path)], check=True)
    if not path.is_file() or path.stat().st_size == 0:
        raise DomainError("frame extraction failed")
    control_id = "anchor-" + upstream + "-" + target
    core.put("control_media", control_id,
             {"role": "visual_anchor", "source_take_id": take["id"], "uri": str(path),
              "source_selection_id": selection["id"], "second": second,
              "assessment": assessment}, "human-reviewed-frame")
    binding_id = "binding-" + target + "-anchor"
    core.put("reference_binding", binding_id,
             {"control_media_id": control_id, "role": "continuity_anchor",
              "media_type": "image", "uri": str(path)}, "visual-anchor-plan")
    core.add_dependency(target, upstream, "VISUAL_ANCHOR")
    payload = core.get("brief", "brief:" + target)["payload"]
    payload["references"] = [binding_id]
    core.save_brief(target, payload, "visual-anchor-plan")
    core.rebase_brief_state(target, upstream)
    print(json.dumps({"status": "ANCHOR_READY", "clip": target, "path": str(path),
                      "source_take": take["id"], "brief_version": core.get("brief", "brief:" + target)["version"]},
                     ensure_ascii=False))
    core.close()


def make_tail(start, duration, assessment):
    core = core_open()
    selection = core.selection("C1")
    if not selection:
        raise DomainError("Stable Tail requires C1 Selection")
    core.next_clip_context("C1")
    take = core.take(selection["take_id"])
    if take["test_only"] or duration < 2 or duration > 15:
        raise DomainError("real selected C1 Take and 2–15s tail required")
    path = RUN / "tail-C1.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-ss", str(start),
                    "-i", take["media_uri"], "-t", str(duration), "-c:v", "libx264",
                    "-crf", "18", "-preset", "fast", "-an", str(path)], check=True)
    if not path.is_file() or path.stat().st_size == 0:
        raise DomainError("tail extraction failed")
    core.create_stable_tail("tail-C1", "C1", take["id"], str(path), assessment)
    payload = core.get("control_media", "tail-C1")["payload"]
    payload["duration"] = duration
    core.put("control_media", "tail-C1", payload, "verified-tail-duration")
    core.rebase_brief_state("C2", "C1")
    print(json.dumps({"status": "STABLE_TAIL_READY", "path": str(path), "source_take": take["id"],
                      "selection_id": selection["id"], "duration": duration}, ensure_ascii=False))
    core.close()


def make_preview():
    core = core_open()
    files = []
    for clip in ("A", "B", "C1", "C2"):
        selection = core.selection(clip)
        if not selection:
            raise DomainError("preview requires all four human Selections")
        core.next_clip_context(clip)
        take = core.take(selection["take_id"])
        if take["test_only"] or not Path(take["media_uri"]).is_file():
            raise DomainError("preview requires four real managed media files")
        files.append(take["media_uri"])
    manifest = RUN / "preview-concat.txt"
    manifest.write_text("".join("file '" + path.replace("'", "'\\''") + "'\n" for path in files))
    output = RUN / "rainy-station-A-B-C1-C2-preview.mp4"
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0",
                    "-i", str(manifest), "-c", "copy", str(output)], check=True)
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(output)],
                           capture_output=True, text=True, check=True)
    print(json.dumps({"status": "PREVIEW_READY", "path": str(output),
                      "duration": float(json.loads(probe.stdout)["format"]["duration"])}, ensure_ascii=False))
    core.close()


def sync_one(job_id, adapter):
    core = core_open()
    job = core.job(job_id)
    generation_provider(job)
    execution_model = darl_execution_model(job['snapshot']['task'])
    if execution_model == LOCAL_H3_MODEL and os.getenv('H3_SERVER_ON') != '1':
        raise DomainError('EXECUTION_MODEL_UNAVAILABLE')
    if job["status"] in {"succeeded", "failed", "cancelled"}:
        raise DomainError("job already terminal")
    provider_id = job["metadata"].get("provider_task_id")
    if not provider_id:
        raise DomainError("provider task id missing")
    response = adapter.poll(provider_id)
    state = response["status"]
    if state == "failed":
        core.job_event(job_id, "failed", {"provider": "darl", "execution_model": execution_model,
                                          "provider_task_id": provider_id,
                                          "query_response": response})
        print(json.dumps({"status": "FAILED", "job_id": job_id, "provider": response}, ensure_ascii=False))
    elif state == "succeeded":
        clip = job["snapshot"]["task"]["clip_id"]
        target = RUN / ("clip-" + clip + "-" + provider_id + ".mp4")
        info = adapter.download(provider_id, target)
        media_id = "media-" + provider_id
        core.register_media(media_id, **{k: v for k, v in info.items() if k != "metadata"},
                            metadata={**info.get("metadata", {}), "provider": "darl",
                                      "execution_model": execution_model, "provider_task_id": provider_id})
        core.job_event(job_id, "succeeded", {"provider": "darl", "execution_model": execution_model,
                                             "provider_task_id": provider_id,
                                             "query_response": response, "media_id": media_id})
        take_id = "take-" + provider_id
        core.record_take(take_id, job_id, info["local_path"],
                         provider_metadata=response, media_id=media_id)
        profile_id = job['snapshot']['task']['model_profile']['id']
        if core.get("model_profile", profile_id)["payload"].get("verification_stage") != "REAL_REQUEST_CONFIRMED":
            core.put("model_profile", profile_id, darl_h3_profile(True, execution_model=execution_model),
                     "real-request-" + provider_id, "verified")
        print(json.dumps({"status": "TAKE_READY_FOR_HUMAN_REVIEW", "clip": clip,
                          "take_id": take_id, "job_id": job_id, "media": info}, ensure_ascii=False))
    else:
        print(json.dumps({"status": "PENDING", "job_id": job_id,
                          "provider_task_id": provider_id, "provider_status": state}, ensure_ascii=False))
    core.close()


def models(adapter):
    result = adapter._request("GET", "/v1/models")
    names = [item.get("id") for item in result.get("data", []) if item.get("id") in H3_EXECUTION_MODELS]
    print(json.dumps({"MiniMax_H3_model_ids": names}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["prepare", "models", "submit", "sync",
                                            "accept", "anchor", "tail", "preview"])
    parser.add_argument("--clip", choices=["A", "B", "C1", "C2"])
    parser.add_argument("--job-id")
    parser.add_argument("--take-id")
    parser.add_argument("--state-file")
    parser.add_argument("--actor")
    parser.add_argument("--upstream", choices=["A", "B"])
    parser.add_argument("--second", type=float)
    parser.add_argument("--duration", type=float)
    parser.add_argument("--assessment-file")
    parser.add_argument("--submit-one", action="store_true")
    parser.add_argument("--technical-retry-of")
    parser.add_argument("--backend-repaired", action="store_true")
    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare()
            return
        if args.command == "preview":
            make_preview()
            return
        if args.command == "accept":
            if not all((args.clip, args.take_id, args.state_file, args.actor)):
                raise DomainError("accept requires clip, take, observed state file, human actor")
            accept_clip(args.clip, args.take_id, args.state_file, args.actor)
            return
        if args.command == "anchor":
            if args.upstream not in ("A", "B") or args.clip not in ("B", "C1") or (
                    (args.upstream, args.clip) not in (("A", "B"), ("B", "C1"))) or (
                    args.second is None or not args.assessment_file):
                raise DomainError("anchor requires A→B or B→C1, second, assessment file")
            make_anchor(args.upstream, args.clip, args.second,
                        json.loads(Path(args.assessment_file).read_text()))
            return
        if args.command == "tail":
            if args.second is None or args.duration is None or not args.assessment_file:
                raise DomainError("tail requires start second, duration, assessment file")
            make_tail(args.second, args.duration,
                      json.loads(Path(args.assessment_file).read_text()))
            return
        adapter = credential_adapter()
        if args.command == "models":
            models(adapter)
        elif args.command == "submit":
            if not args.submit_one or not args.clip:
                raise DomainError("paid submission requires --clip and --submit-one")
            submit_one(args.clip, adapter, args.technical_retry_of, args.backend_repaired)
        else:
            if not args.job_id:
                raise DomainError("sync requires --job-id")
            sync_one(args.job_id, adapter)
    except (DomainError, ProviderError) as exc:
        print(json.dumps({"error": exc.as_dict() if isinstance(exc, ProviderError) else str(exc)},
                         ensure_ascii=False), file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
