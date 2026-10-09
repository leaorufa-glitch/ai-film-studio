"""Documented H3 capability for Darl's New API transport.

Official model limits and proxy-specific options are intentionally distinguished.
Runtime validation promotes a new immutable profile version after a real request.
"""
from datetime import date
import os

OFFICIAL_CREATE = "https://platform.minimax.io/docs/api-reference/video-generation-v2-create"
PROXY_GUIDE = "https://fwr0187eq6.apifox.cn/9352472m0"
LOCAL_H3_MODEL = "MiniMax-H3"
CLOUD_H3_MODEL = "runninghub-minimax-h3"
H3_EXECUTION_MODELS = {LOCAL_H3_MODEL: "自建 H3", CLOUD_H3_MODEL: "云端 H3 · 备用"}
H3_PROFILE_IDS = {LOCAL_H3_MODEL: "h3-darl", CLOUD_H3_MODEL: "h3-darl-cloud"}
CLOUD_H3_SUPPORTED_MODES = ["INDEPENDENT", "MULTI_SHOT_ONE_PASS", "STATE_CONTINUE_NEW_VIEW", "VISUAL_ANCHOR"]


def current_h3_execution_model():
    return LOCAL_H3_MODEL if os.getenv("H3_SERVER_ON") == "1" else CLOUD_H3_MODEL


def h3_execution_capability_reasons(task, profile=None):
    snapshot = task.get("model_profile_snapshot") or {}
    profile = profile or {}
    models = (task.get("execution_model"), task.get("target_model"),
              snapshot.get("execution_model"), snapshot.get("model_id"),
              profile.get("execution_model"), profile.get("model_id"))
    if CLOUD_H3_MODEL not in models and task.get("model_profile", {}).get("id") != H3_PROFILE_IDS[CLOUD_H3_MODEL]:
        return []
    reasons = []
    mode = task.get("task_mode")
    if mode not in CLOUD_H3_SUPPORTED_MODES:
        reasons.append({"code": "MODE_UNVERIFIED_OR_UNSUPPORTED", "field": "task_mode"})
    control = (task.get("control_media_snapshot") or {}).get("payload", {})
    if mode == "VIDEO_CONTINUATION" or task.get("continuation") or control.get("role") == "stable_tail":
        reasons.append({"code": "VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED", "field": "task_mode"})
    keyframes = any(binding.get("role") in {"first_frame", "last_frame"}
                    for binding in task.get("media_bindings", []))
    if mode == "KEYFRAME_CONSTRAINED" or keyframes:
        reasons.append({"code": "KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED", "field": "task_mode"})
    return reasons


def darl_h3_profile(runtime_verified=False, execution_model=LOCAL_H3_MODEL):
    if execution_model not in H3_EXECUTION_MODELS:
        raise ValueError("unsupported Darl H3 execution model")
    profile = {
        "family": "H3", "model_id": execution_model, "model_version": "H3 via Darl V2",
        "provider": "darl", "execution_model": execution_model,
        "source": {"official_model": OFFICIAL_CREATE, "proxy_transport": PROXY_GUIDE},
        "verified_at": date.today().isoformat(),
        "verification_stage": "REAL_REQUEST_CONFIRMED" if runtime_verified else "DOCUMENTED_PENDING_REAL_REQUEST",
        "supported_modes": ["INDEPENDENT", "MULTI_SHOT_ONE_PASS", "STATE_CONTINUE_NEW_VIEW",
                            "VISUAL_ANCHOR", "VIDEO_CONTINUATION", "KEYFRAME_CONSTRAINED"],
        "duration_envelope": {"verified": True, "min": 4, "max": 15,
                              "source": [OFFICIAL_CREATE, PROXY_GUIDE]},
        "media_capability": {"verified": True, "max_references": 12,
                             "types": ["image", "video", "audio"],
                             "counts": {"reference_image": 9, "reference_video": 3, "reference_audio": 3,
                                        "first_frame": 1, "last_frame": 1},
                             "video_seconds_per_clip": [2, 15], "video_seconds_total": 15,
                             "audio_seconds_per_clip": [2, 15], "audio_seconds_total": 15,
                             "source": [OFFICIAL_CREATE, PROXY_GUIDE]},
        "temporal_controls": {"verified": True, "first_frame": True, "last_frame": True,
                              "video_continuation": True,
                              "source": [OFFICIAL_CREATE, PROXY_GUIDE]},
        "audio_capability": {"verified": True, "native_audio": True,
                             "source": PROXY_GUIDE},
        "parameter_capability": {"verified": True,
                                 "allowed": {"resolution": ["384P", "480P", "768P"],
                                             "num_inference_steps": list(range(1, 101)),
                                             "turbo": [False, True], "watermark": [False]},
                                 "required": ["resolution", "num_inference_steps", "turbo", "watermark"],
                                 "source": PROXY_GUIDE},
        "aspect_ratios": ["21:9", "16:9", "4:3", "1:1", "3:4", "9:16"],
        "hard_capability_source": {"official": OFFICIAL_CREATE, "proxy": PROXY_GUIDE},
        "reliability_knowledge": {"source": None, "observations": []},
        "compilation_requirements": {
            "base_sections": ["integrated_multimodal_description", "overall_soundscape", "non_diegetic_music"],
            "required_sections": ["subject_definitions", "summary", "retention_analysis",
                                  "detailed_description", "overall_soundscape", "non_diegetic_music"]},
        "transport": {"base_url": "https://api.darl.cn", "create": "/v1/videos",
                      "query": "/v1/videos/{id}", "content": "/v1/videos/{id}/content",
                      "cancel": "/v1/videos/{id}", "states": ["queued", "processing", "succeeded", "failed"],
                      "source": PROXY_GUIDE},
        "official_model_output": {"resolutions": ["768P", "2K"], "source": OFFICIAL_CREATE},
        "proxy_output": {"resolutions": ["384P", "480P", "768P"], "source": PROXY_GUIDE},
    }
    if execution_model == CLOUD_H3_MODEL:
        profile["supported_modes"] = list(CLOUD_H3_SUPPORTED_MODES)
        profile["temporal_controls"] = {
            "verified": False, "first_frame": False, "last_frame": False, "video_continuation": False,
            "source": None, "verification_stage": "MODEL_SPECIFIC_EVIDENCE_REQUIRED"}
        profile["media_capability"]["counts"].update({"first_frame": 0, "last_frame": 0})
    return profile
