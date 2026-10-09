"""Rainy-station contract fixture. Synthetic provider results exist only in test mode."""
from copy import deepcopy
from .core import Core


H3_PROFILE_UNVERIFIED = {
    "family": "H3", "model_id": "new-h3-video", "model_version": "unknown",
    "source": "unverified: no current provider specification supplied to #001",
    "verified_at": None, "supported_modes": [],
    "duration_envelope": {"verified": False, "min": None, "max": None},
    "media_capability": {"verified": False, "max_references": None, "types": []},
    "temporal_controls": {"verified": False, "first_frame": None, "last_frame": None,
                          "video_continuation": None},
    "audio_capability": {"verified": False, "native_audio": None},
    "parameter_capability": {"verified": False, "allowed": {}, "required": []},
    "aspect_ratios": [], "hard_capability_source": None,
    "reliability_knowledge": {"source": None, "observations": []},
    "compilation_requirements": {"required_sections": [
        "subject_definitions", "summary", "retention_analysis", "detailed_description",
        "overall_soundscape", "non_diegetic_music"]}
}


def test_profile():
    """Only validates the contract harness; never describes real H3 capabilities."""
    p = deepcopy(H3_PROFILE_UNVERIFIED)
    p.update({"model_version": "TEST-ONLY", "source": "synthetic #001 contract test",
              "verified_at": "test-only", "supported_modes": [
                  "MULTI_SHOT_ONE_PASS", "STATE_CONTINUE_NEW_VIEW", "INDEPENDENT",
                  "VIDEO_CONTINUATION"], "aspect_ratios": ["16:9"]})
    p["duration_envelope"] = {"verified": True, "min": 1, "max": 30}
    p["media_capability"] = {"verified": True, "max_references": 4, "types": ["image"]}
    p["temporal_controls"] = {"verified": True, "first_frame": False,
                              "last_frame": False, "video_continuation": True}
    p["audio_capability"] = {"verified": True, "native_audio": True}
    p["parameter_capability"] = {"verified": True, "allowed": {}, "required": []}
    return p


def seed(core: Core):
    core.put("project", "station-film", {"title": "雨夜车站"}, "fixture")
    core.put("episode", "episode-1", {"project_id": "station-film", "number": 1}, "fixture")
    core.put("scene", "station-scene", {"episode_id": "episode-1", "place": "雨夜旧车站候车厅",
                                       "story": "林夏打开旧信，认出失踪多年的母亲的字迹；她没有哭，随后走向站台。"}, "fixture")
    core.put("character", "linxia", {"name": "林夏", "identity": "失踪母亲的女儿"}, "fixture")
    core.put("character_look", "linxia-rain", {"character_id": "linxia", "description": "雨夜旅行装束"}, "fixture")
    core.put("location", "old-station", {"identity": "旧车站候车厅与站台入口"}, "fixture")
    core.put("prop", "old-letter", {"identity": "母亲留下的旧信"}, "fixture")
    core.put("story_fact", "mother-handwriting", {"fact": "林夏能认出母亲字迹", "scene_id": "station-scene"}, "fixture")
    core.put("asset_version", "linxia-look-asset", {"owner_id": "linxia-rain", "media_type": "image",
                                                   "uri": "fixture://reference/linxia.png"}, "fixture")
    core.put("reference_binding", "linxia-reference", {"asset_id": "linxia-look-asset", "role": "character_look",
                                                         "media_type": "image", "uri": "fixture://reference/linxia.png"}, "fixture")
    core.put("model_profile", "h3-unverified", H3_PROFILE_UNVERIFIED, "#001-unverified", "unverified")
    if core.test_mode:
        core.put("model_profile", "h3-test-contract", test_profile(), "synthetic-test", "test_only")
    shots = [
        ("S01", 3, "中近景，林夏坐着展开旧信"),
        ("S02", 2, "信件特写，出现可识别字迹与署名"),
        ("S03", 5, "回人物，认出字迹，不哭，呼吸变浅，抬眼"),
        ("S04", 6, "CUT 到过肩侧后机位，望向列车灯"),
        ("S05", 20, "连续长镜头，折信、起身、穿过候车厅、停在站台门口"),
    ]
    for sid, duration, description in shots:
        core.put("shot", sid, {"scene_id": "station-scene", "duration": duration,
                               "description": description, "director_approved": True}, "fixture-director")
    clips = [("A", 10, "MULTI_SHOT_ONE_PASS"), ("B", 6, "STATE_CONTINUE_NEW_VIEW"),
             ("C1", 12, "INDEPENDENT"), ("C2", 8, "VIDEO_CONTINUATION")]
    for cid, duration, handoff in clips:
        core.put("clip", cid, {"scene_id": "station-scene", "duration": duration,
                               "handoff": handoff}, "fixture-production")
    for args in [
        ("A", "S01", 0, 0, 3, 0, 3, False),
        ("A", "S02", 1, 0, 2, 3, 5, True),
        ("A", "S03", 2, 0, 5, 5, 10, True),
        ("B", "S04", 0, 0, 6, 0, 6, True),
        ("C1", "S05", 0, 0, 12, 0, 12, False),
        ("C2", "S05", 0, 12, 20, 0, 8, False),
    ]:
        core.map_shot(*args)
    core.add_dependency("B", "A", "STATE_CONTINUITY")
    core.add_dependency("C1", "B", "STATE_CONTINUITY")
    core.add_dependency("C2", "C1", "VIDEO_CONTINUATION")
    initial = {"source": "scene_initial", "facts": {
        "character_id": "linxia", "look_id": "linxia-rain", "location_id": "old-station",
        "prop_holder": "linxia", "letter_state": "folded", "crying": False}}
    for cid, duration, handoff in clips:
        mapping = core.mappings(cid)
        state_out = {"character_id": "linxia", "look_id": "linxia-rain", "location_id": "old-station",
                     "crying": False, "letter_state": "folded" if cid in ("C1", "C2") else "open"}
        if cid == "A":
            action = {"initial": "信仍折着", "trigger": "林夏发现署名", "development": "展开并辨认字迹，停顿",
                      "result": "按住信纸，缓慢抬眼"}
        elif cid == "B":
            action = {"initial": "林夏坐着看向站台", "trigger": "远处列车灯亮起",
                      "development": "视线沿轨道移动", "result": "视线停在灯光上"}
        elif cid == "C1":
            action = {"initial": "信展开在手中", "trigger": "列车靠近",
                      "development": "折信，起身，走过候车厅前半段", "result": "动作继续，尚未到门口"}
        else:
            action = {"initial": "林夏正在穿过候车厅", "trigger": "脚步继续",
                      "development": "走向站台门口", "result": "稳定停在门口"}
        brief = {
            "clip_id": cid, "scene_id": "station-scene", "purpose": "呈现林夏认出母亲字迹后克制的反应与赴站台的决定",
            "duration": duration, "shot_timeline": [{"shot_id": m["shot_id"], "start": m["clip_start"],
                "end": m["clip_end"], "cut_before": bool(m["cut_before"])} for m in mapping],
            "subjects": [{"character_id": "linxia", "look_id": "linxia-rain"}],
            "environment": {"location_id": "old-station", "rain": True, "time": "night"},
            "props": [{"prop_id": "old-letter", "state": "held by Lin Xia"}],
            "state_in": initial, "action_process": [action],
            "performance": {"gaze": "由信纸缓慢转向站台", "breath": "变浅", "gesture": "手指压住纸边",
                            "pause": "认出字迹后停顿", "reaction": "克制，不哭"},
            "camera": {"framing": "按批准 Shot 的机位与景别", "movement": "按批准 Shot 的运动；S05 保持连续"},
            "sound": {"diegetic": "雨声与远处列车声", "music": "无新增非叙事音乐"},
            "references": ["linxia-reference"], "constraints": ["不改变导演 Shot 顺序"],
            "locked_constraints": ["林夏没有哭", "不得新增关键剧情动作"],
            "planned_state_out": state_out, "handoff": handoff,
            "provenance": {"source": "fixture-director-plan", "authority": "LOCKED",
                           "field_authority": {"locked_constraints": "LOCKED", "action_process": "PLANNED"}},
        }
        core.save_brief(cid, brief, "fixture-production")
    return core
