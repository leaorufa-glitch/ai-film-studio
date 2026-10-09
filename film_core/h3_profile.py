"""Documented H3 capability for Darl's self-hosted New API transport (#002).

Official model limits and proxy-specific options are intentionally distinguished.
Runtime validation promotes a new immutable profile version after a real request.
"""
from datetime import date

OFFICIAL_CREATE = "https://platform.minimax.io/docs/api-reference/video-generation-v2-create"
PROXY_GUIDE = "https://fwr0187eq6.apifox.cn/9352472m0"


def darl_h3_profile(runtime_verified=False):
    return {
        "family": "H3", "model_id": "MiniMax-H3", "model_version": "H3 via Darl local V2",
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
