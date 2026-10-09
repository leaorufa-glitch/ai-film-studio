"""Real Darl New API adapter for MiniMax-H3; never contains a credential literal."""
import base64
import hashlib
import json
import mimetypes
import os
import subprocess
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from .core import DomainError
from .h3_profile import H3_EXECUTION_MODELS, h3_execution_capability_reasons


def darl_execution_model(task):
    model = task.get("execution_model", task.get("target_model"))
    if model not in H3_EXECUTION_MODELS or model != task.get("target_model"):
        raise DomainError("execution model mismatch: no silent substitution")
    profile_model = task.get("model_profile_snapshot", {}).get("model_id", model)
    if profile_model != model:
        raise DomainError("execution model differs from frozen profile")
    if task.get("provider", "darl") != "darl":
        raise DomainError("LEGACY_PROVIDER_UNSUPPORTED")
    reasons = h3_execution_capability_reasons(task)
    if reasons:
        raise DomainError("model capability not ready: " + json.dumps(reasons))
    return model


class ProviderError(RuntimeError):
    def __init__(self, code, message, transient=False, http_status=None, detail=None):
        super().__init__(message)
        self.code = code
        self.transient = transient
        self.http_status = http_status
        self.detail = detail or {}

    def as_dict(self):
        return {"code": self.code, "message": str(self), "transient": self.transient,
                "http_status": self.http_status, "detail": self.detail}


class DarlH3Adapter:
    def __init__(self, base_url="https://api.darl.cn", key=None, opener=urlopen):
        self.base_url = base_url.rstrip("/")
        self.key = key or os.environ.get("DARL_API_KEY")
        if not self.key:
            raise DomainError("NEEDS_CREDENTIALS: set DARL_API_KEY in the server environment")
        self.opener = opener

    def _request(self, method, path, body=None, binary=False):
        data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(self.base_url + path, data=data, method=method,
                          headers={"Authorization": "Bearer " + self.key,
                                   "Content-Type": "application/json"})
        try:
            with self.opener(request, timeout=45) as response:
                raw = response.read()
                if binary:
                    return raw, response.headers.get("Content-Type", "application/octet-stream")
                return json.loads(raw)
        except HTTPError as exc:
            raw = exc.read()
            try:
                detail = json.loads(raw)
            except (json.JSONDecodeError, UnicodeDecodeError):
                detail = {"body": raw.decode("utf-8", "replace")[:500]}
            code = detail.get("code") or detail.get("error", {}).get("type") or "HTTP_%s" % exc.code
            message = detail.get("message") or str(detail.get("error") or exc)
            if "<html" in message.lower() or "<!doctype html" in message.lower():
                message = "upstream returned an HTML error page"
                detail = {"code": code, "upstream_html_error": True}
            else:
                message = str(message)[:500]
                detail = {"code": code, "message": message}
            raise ProviderError(str(code), message,
                                transient=exc.code in (408, 429, 500, 502, 503, 504),
                                http_status=exc.code, detail=detail) from None
        except (URLError, TimeoutError) as exc:
            raise ProviderError("NETWORK_ERROR", str(exc), transient=True) from None

    @staticmethod
    def _media_url(uri, media_type):
        if uri.startswith(("https://", "http://", "data:")):
            return uri
        path = Path(uri.removeprefix("file://"))
        if not path.is_file():
            raise DomainError("reference media does not exist: " + str(path))
        mime = mimetypes.guess_type(path.name)[0] or {
            "image": "image/png", "video": "video/mp4", "audio": "audio/mpeg"}[media_type]
        return "data:%s;base64,%s" % (mime, base64.b64encode(path.read_bytes()).decode("ascii"))

    def build_request(self, task):
        execution_model = darl_execution_model(task)
        params = task["parameters"]
        if params.get("turbo") and params.get("num_inference_steps") != 4:
            raise DomainError("Darl H3 Turbo requires exactly 4 steps")
        content = [{"type": "text", "text": task["compiled_prompt"]}]
        if not content[0]["text"] or len(content[0]["text"]) > 7000:
            raise DomainError("H3 prompt must be 1–7000 characters")
        counts = {"reference_image": 0, "reference_video": 0, "reference_audio": 0,
                  "first_frame": 0, "last_frame": 0}
        internal_to_api = {
            "continuity_anchor": "reference_image", "character_identity": "reference_image",
            "character_look": "reference_image", "current_look": "reference_image",
            "environment_identity": "reference_image", "prop_identity": "reference_image",
            "composition_reference": "reference_image", "motion_reference": "reference_video",
            "camera_reference": "reference_video", "audio_reference": "reference_audio",
            "first_frame": "first_frame", "last_frame": "last_frame",
        }
        for binding in task["media_bindings"]:
            role = internal_to_api.get(binding["role"])
            if not role:
                raise DomainError("unmapped reference role: " + binding["role"])
            media_type = binding["media_type"]
            expected = "image" if role in ("reference_image", "first_frame", "last_frame") else (
                "video" if role == "reference_video" else "audio")
            if media_type != expected:
                raise DomainError("reference role/media type mismatch")
            url = self._media_url(binding["uri"], media_type)
            item_type = media_type + "_url"
            content.append({"type": item_type, "role": role, item_type: {"url": url}})
            counts[role] += 1
        if task.get("continuation"):
            if task["task_mode"] != "VIDEO_CONTINUATION":
                raise DomainError("continuation source on non-continuation task")
            control = task["control_media_snapshot"]
            if not control or control["payload"]["role"] != "stable_tail":
                raise DomainError("selected stable tail missing")
            url = self._media_url(control["payload"]["uri"], "video")
            content.append({"type": "video_url", "role": "reference_video", "video_url": {"url": url}})
            counts["reference_video"] += 1
            if "[video continuation]" not in task["compiled_prompt"]:
                raise DomainError("continuation semantic missing from compiled prompt")
        if (counts["first_frame"] or counts["last_frame"]) and (
                counts["reference_image"] or counts["reference_video"] or counts["reference_audio"]):
            raise DomainError("first/last frame and reference modes are mutually exclusive")
        if counts["reference_audio"] and not (counts["reference_image"] or counts["reference_video"]):
            raise DomainError("reference audio cannot be sole media")
        limits = {"reference_image": 9, "reference_video": 3, "reference_audio": 3,
                  "first_frame": 1, "last_frame": 1}
        if any(counts[k] > limits[k] for k in counts):
            raise DomainError("media count exceeds H3 profile")
        ratio = "adaptive" if counts["first_frame"] or counts["last_frame"] else task["aspect_ratio"]
        body = {"model": execution_model, "content": content,
                "duration": task["duration"], "ratio": ratio,
                "resolution": params["resolution"],
                "num_inference_steps": params["num_inference_steps"],
                "turbo": params["turbo"], "watermark": params["watermark"]}
        if len(json.dumps(body).encode("utf-8")) > 64 * 1024 * 1024:
            raise DomainError("request body exceeds 64 MB")
        return body

    def submit(self, compiled_task, idempotency_key):
        # The proxy does not document an idempotency header. Never auto-resubmit on timeout.
        body = self.build_request(compiled_task)
        result = self._request("POST", "/v1/videos", body)
        if not result.get("id") or result.get("status") not in {"queued", "processing"}:
            raise ProviderError("INVALID_CREATE_RESPONSE", "missing public task id", detail=result)
        return result

    def poll(self, provider_task_id):
        result = self._request("GET", "/v1/videos/" + provider_task_id)
        if result.get("id") != provider_task_id or result.get("status") not in {
                "queued", "processing", "succeeded", "failed"}:
            raise ProviderError("INVALID_QUERY_RESPONSE", "invalid task response", detail=result)
        return result

    def cancel(self, provider_task_id):
        return self._request("DELETE", "/v1/videos/" + provider_task_id)

    def download(self, provider_task_id, destination):
        raw, mime = self._request("GET", "/v1/videos/" + provider_task_id + "/content", binary=True)
        if len(raw) < 1024 or not raw.startswith((b"\x00\x00\x00", b"\x00\x00\x01")):
            raise ProviderError("INVALID_MEDIA", "provider did not return a plausible MP4")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(target.suffix + ".partial")
        tmp.write_bytes(raw)
        tmp.replace(target)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(target)],
                               capture_output=True, text=True, check=True)
        duration = float(json.loads(probe.stdout)["format"]["duration"])
        return {"local_path": str(target), "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw), "mime": "video/mp4", "duration": duration,
                "metadata": {"provider_content_type": mime.split(";")[0]}}
