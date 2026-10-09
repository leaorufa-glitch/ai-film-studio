"""RunningHub H3 fallback transport. Credentials and webapp ID come only from server env."""
from __future__ import annotations

import hashlib
import json
import mimetypes
import os
import re
import subprocess
import uuid
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from film_core import DomainError
from film_core.darl_h3 import ProviderError
from film_core.h3_profile import darl_h3_profile

HOST = "https://www.runninghub.cn"
IMAGE_NODES = ("51", "49", "50", "43", "19", "23")
AUDIO_NODES = ("48", "14", "15")
VIDEO_NODE = "27"
ALLOWED_MODES = ("INDEPENDENT", "MULTI_SHOT_ONE_PASS", "STATE_CONTINUE_NEW_VIEW", "VISUAL_ANCHOR")


def runninghub_h3_profile():
    """A documented workflow profile; video continuation remains unverified."""
    profile = darl_h3_profile(False)
    profile.update({
        "model_version": "H3 via RunningHub workflow",
        "source": {"workflow": "user-supplied RunningHub HTTP workflow document"},
        "verification_stage": "WORKFLOW_NODES_CONFIRMED_PENDING_REAL_FILM",
        "supported_modes": list(ALLOWED_MODES),
        "duration_envelope": {"verified": True, "min": 4, "max": 15,
                              "source": "workflow duration float node; H3 conservative envelope"},
        "media_capability": {"verified": True, "max_references": 10,
                             "types": ["image", "audio", "video"],
                             "counts": {"reference_image": 6, "reference_audio": 3,
                                        "reference_video": 1},
                             "source": "RunningHub workflow nodes"},
        "temporal_controls": {"verified": False, "first_frame": False, "last_frame": False,
                              "video_continuation": False},
        "parameter_capability": {"verified": True,
                                 "allowed": {"resolution": ["480P"],
                                             "num_inference_steps": [20], "turbo": [False],
                                             "watermark": [False]},
                                 "required": ["resolution", "num_inference_steps", "turbo", "watermark"],
                                 "source": "local default translated to workflow fields"},
        "aspect_ratios": ["16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"],
        "transport": {"base_url": HOST, "create": "/task/openapi/ai-app/run",
                      "query": "/openapi/v2/query", "upload": "/task/openapi/upload"},
        "workflow_constraints": {"reference_video_is_not_video_continuation": True,
                                 "resolution_megapixels": "0.4 approx; output unverified",
                                 "inference_steps": "workflow controlled; no editable step node"},
    })
    return profile


class RunningHubH3Adapter:
    provider = "runninghub"

    def __init__(self, *, key=None, webapp_id=None, base_url=HOST, opener=urlopen):
        self.key = key or os.getenv("RUNNINGHUB_API_KEY")
        self.webapp_id = webapp_id or os.getenv("RUNNINGHUB_WEBAPP_ID")
        if not self.key or not self.webapp_id:
            raise DomainError("NEEDS_CREDENTIALS: configure RunningHub on the server")
        if not str(self.webapp_id).isdigit():
            raise DomainError("RUNNINGHUB_WEBAPP_ID must be numeric")
        self.base_url = base_url.rstrip("/")
        self.opener = opener

    def _sanitize(self, response):
        secrets = {str(self.key)}

        def sensitive(field):
            name = re.sub(r"[^a-z0-9]", "", str(field).lower())
            return (name.endswith("key") or name in {"auth", "sessionid", "webappid"} or
                    any(part in name for part in ("authorization", "authentication", "credential", "secret", "password",
                                                  "passwd", "token", "cookie", "signature")))

        def collect(value, credential=False):
            if isinstance(value, dict):
                for field, item in value.items():
                    collect(item, credential or sensitive(field))
            elif isinstance(value, list):
                for item in value:
                    collect(item, credential)
            elif credential and isinstance(value, str) and value:
                secrets.add(value)
                if value.lower().startswith(("bearer ", "basic ")):
                    secrets.add(value.split(" ", 1)[1])
            elif credential and isinstance(value, (int, float)) and not isinstance(value, bool):
                secrets.add(str(value))

        collect(response)
        replacements = sorted({secret for value in secrets for secret in (value, quote(value, safe=""))},
                              key=len, reverse=True)

        def text(value):
            for secret in replacements:
                value = value.replace(secret, "[REDACTED]")
            value = re.sub(r"(?i)\b(?:bearer|basic)\s+[A-Za-z0-9._~+/=-]+", "[REDACTED]", value)
            value = re.sub(r"(?i)\b(?:sk-[A-Za-z0-9_-]{8,}|[a-f0-9]{32,})\b", "[REDACTED]", value)
            value = re.sub(r"(https?://)[^\s/:@]+:[^\s/@]+@", r"\1[REDACTED]@", value)
            value = re.sub(r"(?i)\b(?:[A-Za-z0-9_-]*(?:api[_-]?key|token|secret|password|authorization|credential)[A-Za-z0-9_-]*)"
                           r"\s*[=:]\s*(?:\"[^\"]*\"|'[^']*'|[^\s,;&}]+)", "[REDACTED]", value)
            return value[:2048]

        def redact(value, depth=0):
            if depth > 10:
                return "[TRUNCATED]"
            if isinstance(value, dict):
                return {text(str(field)): "[REDACTED]" if sensitive(field) else redact(item, depth + 1)
                        for field, item in list(value.items())[:100]}
            if isinstance(value, list):
                return [redact(item, depth + 1) for item in value[:100]]
            return text(value) if isinstance(value, str) else value

        return redact(response)

    def _create_diagnostics(self, response, http_status):
        safe = self._sanitize(response)
        message = next((safe.get(field) for field in ("msg", "message")
                        if isinstance(safe.get(field), str) and safe[field].strip()), None)
        return {"provider": self.provider, "operation": "create", "provider_code": safe.get("code"),
                "provider_message": message, "http_status": http_status, "response_metadata": safe}

    def _send(self, path, *, payload=None, content_type="application/json", bearer=False, raw=False, timeout=60,
              operation=None):
        data = payload if isinstance(payload, bytes) else json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {"Content-Type": content_type}
        if bearer:
            headers["Authorization"] = "Bearer " + self.key
        request = Request(self.base_url + path, data=data, headers=headers, method="POST")
        http_status = None
        http_error = False
        try:
            with self.opener(request, timeout=timeout) as response:
                http_status = getattr(response, "status", None)
                if http_status is None and hasattr(response, "getcode"):
                    http_status = response.getcode()
                body = response.read()
        except HTTPError as exc:
            if operation != "create":
                raise ProviderError("HTTP_%s" % exc.code, "RunningHub request failed",
                                    transient=exc.code in (408, 429, 500, 502, 503, 504),
                                    http_status=exc.code) from None
            http_status = exc.code
            http_error = True
            body = exc.read()
        except (URLError, TimeoutError):
            detail = self._create_diagnostics({}, http_status) if operation == "create" else None
            raise ProviderError("NETWORK_ERROR", "RunningHub connection failed", transient=True,
                                http_status=http_status, detail=detail) from None
        if raw:
            return body
        try:
            result = json.loads(body)
            if not isinstance(result, dict):
                raise ValueError("non-object response")
        except (ValueError, UnicodeError):
            detail = self._create_diagnostics({"response_format": "invalid_json_object"}, http_status) if operation == "create" else None
            raise ProviderError("INVALID_PROVIDER_RESPONSE", "RunningHub response could not be read",
                                http_status=http_status, detail=detail) from None
        if operation == "create":
            if http_error:
                detail = self._create_diagnostics(result, http_status)
                raise ProviderError("HTTP_%s" % http_status, detail["provider_message"] or "RunningHub request failed",
                                    transient=http_status in (408, 429, 500, 502, 503, 504),
                                    http_status=http_status, detail=detail)
            return result, http_status
        return result

    @staticmethod
    def _node(node_id, field, value):
        return {"nodeId": node_id, "fieldName": field, "value": str(value)}

    def build_request(self, task):
        if task.get("target_model") != "MiniMax-H3":
            raise DomainError("RunningHub H3 model mismatch")
        if task.get("task_mode") not in ALLOWED_MODES or task.get("continuation"):
            raise DomainError("RunningHub VIDEO_CONTINUATION has not been validated")
        params = task.get("parameters") or {}
        if params != {"resolution": "480P", "num_inference_steps": 20,
                      "turbo": False, "watermark": False}:
            raise DomainError("RunningHub workflow supports only the documented local default")
        if not isinstance(task.get("duration"), int) or not 4 <= task["duration"] <= 15:
            raise DomainError("RunningHub duration outside conservative H3 envelope")
        prompt = task.get("compiled_prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 7000:
            raise DomainError("RunningHub H3 prompt must be 1–7000 characters")
        ratio = task.get("aspect_ratio")
        if ratio not in ("16:9", "9:16", "1:1", "4:3", "3:4", "3:2", "2:3", "21:9"):
            raise DomainError("RunningHub aspect ratio unsupported")
        ratio_value = "16:9 (Widescreen)" if ratio == "16:9" else ratio
        nodes = [self._node("263", "text", prompt), self._node("252", "megapixels", "0.4"),
                 self._node("252", "aspect_ratio", ratio_value),
                 self._node("259", "value", task["duration"]),
                 self._node("283", "value", "1.0")]
        # Clear the workflow's example media defaults; never generate with unrelated demo images.
        nodes.extend(self._node(slot, "image", "") for slot in IMAGE_NODES)
        nodes.extend(self._node(slot, "audio", "") for slot in AUDIO_NODES)
        nodes.append(self._node(VIDEO_NODE, "video", ""))
        pending = []
        counts = {"image": 0, "audio": 0, "video": 0}
        for binding in task.get("media_bindings", []):
            kind = binding.get("media_type")
            role = binding.get("role")
            if kind == "image" and role in {
                "character_identity", "character_look", "current_look",
                "environment_identity", "prop_identity", "composition_reference", "continuity_anchor"}:
                slot = IMAGE_NODES[counts[kind]] if counts[kind] < len(IMAGE_NODES) else None
                field = "image"
            elif kind == "audio" and role == "audio_reference":
                slot = AUDIO_NODES[counts[kind]] if counts[kind] < len(AUDIO_NODES) else None
                field = "audio"
            elif kind == "video" and role in {"motion_reference", "camera_reference"}:
                slot = VIDEO_NODE if counts[kind] == 0 else None
                field = "video"
            else:
                raise DomainError("RunningHub reference role is unsupported or unverified")
            if slot is None:
                raise DomainError("RunningHub workflow reference count exceeded")
            uri = binding.get("uri", "")
            if not isinstance(uri, str) or uri.startswith(("http:", "https:", "data:")):
                raise DomainError("RunningHub references must use managed local media")
            path = Path(uri.removeprefix("file://")).resolve()
            if not path.is_file() or path.stat().st_size > 100 * 1024 * 1024:
                raise DomainError("RunningHub reference media missing or too large")
            pending.append((slot, field, path))
            counts[kind] += 1
        return {"nodes": nodes, "uploads": pending}

    def upload(self, path):
        path = Path(path)
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        boundary = "filmstudio" + uuid.uuid4().hex
        def field(name, value):
            return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n").encode()
        suffix = path.suffix.lower() if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".mp3", ".wav", ".mp4"} else ""
        header = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"reference{suffix}\"\r\n"
                  f"Content-Type: {mime}\r\n\r\n").encode()
        body = field("apiKey", self.key) + field("fileType", "input") + header + path.read_bytes() + b"\r\n" + f"--{boundary}--\r\n".encode()
        result = self._send("/task/openapi/upload", payload=body,
                            content_type="multipart/form-data; boundary=" + boundary, timeout=120)
        if result.get("code") != 0 or not isinstance((result.get("data") or {}).get("fileName"), str):
            raise ProviderError("UPLOAD_FAILED", "RunningHub reference upload failed")
        return result["data"]["fileName"]

    def submit(self, compiled_task, idempotency_key):
        spec = self.build_request(compiled_task)
        nodes = list(spec["nodes"])
        for slot, field, path in spec["uploads"]:
            value = self.upload(path)
            next(node for node in nodes if node["nodeId"] == slot and node["fieldName"] == field)["value"] = value
        result, http_status = self._send("/task/openapi/ai-app/run",
                                       payload={"apiKey": self.key, "webappId": int(self.webapp_id),
                                                "nodeInfoList": nodes}, operation="create")
        if result.get("code") != 0:
            detail = self._create_diagnostics(result, http_status)
            raise ProviderError("RUNNINGHUB_CREATE_FAILED", detail["provider_message"] or "RunningHub rejected create request",
                                http_status=http_status, detail=detail)
        data = result.get("data")
        task_id = data.get("taskId") if isinstance(data, dict) else None
        if (isinstance(task_id, bool) or not isinstance(task_id, (str, int)) or
                not re.fullmatch(r"[0-9]+", str(task_id)) or int(task_id) <= 0):
            raise ProviderError("INVALID_CREATE_RESPONSE", "RunningHub did not return a valid task ID",
                                http_status=http_status, detail=self._create_diagnostics(result, http_status))
        return {"id": str(task_id), "status": str(data.get("taskStatus", "QUEUED")).lower()}

    def poll(self, provider_task_id):
        if not str(provider_task_id).isdigit():
            raise ProviderError("INVALID_TASK_ID", "RunningHub task ID is invalid")
        result = self._send("/openapi/v2/query", payload={"taskId": str(provider_task_id)}, bearer=True)
        status = str(result.get("status") or (result.get("data") or {}).get("status") or "").upper()
        if status == "FAILED":
            raw_code = str(result.get("errorCode") or "PROVIDER_FAILED")
            code = raw_code[:64] if raw_code[:64].replace("_", "").replace("-", "").isalnum() else "PROVIDER_FAILED"
            return {"id": str(provider_task_id), "status": "failed", "error_code": code}
        mapping = {"SUCCESS": "succeeded", "QUEUED": "queued", "RUNNING": "processing",
                   "PROCESSING": "processing", "PENDING": "queued"}
        if status not in mapping:
            raise ProviderError("INVALID_QUERY_RESPONSE", "RunningHub returned an unknown task state")
        return {"id": str(provider_task_id), "status": mapping[status]}

    def download(self, provider_task_id, destination):
        result = self._send("/openapi/v2/query", payload={"taskId": str(provider_task_id)}, bearer=True)
        if str(result.get("status") or "").upper() != "SUCCESS":
            raise ProviderError("MEDIA_NOT_READY", "RunningHub media is not ready", transient=True)
        results = result.get("results") or (result.get("data") or {}).get("results") or []
        if isinstance(results, dict):
            results = [results]
        url = next((item for item in results if isinstance(item,str) and item.startswith("https://")),None)
        if not url:
            url = next((item.get(k) for item in results if isinstance(item, dict)
                        for k in ("fileUrl", "url", "videoUrl") if isinstance(item.get(k), str)), None)
        parsed = urlparse(url or "")
        if parsed.scheme != "https" or not parsed.hostname:
            raise ProviderError("INVALID_MEDIA_URL", "RunningHub returned no valid video URL")
        try:
            with self.opener(Request(url), timeout=120) as response:
                raw = response.read(150 * 1024 * 1024 + 1)
        except (HTTPError, URLError, TimeoutError):
            raise ProviderError("MEDIA_DOWNLOAD_FAILED", "RunningHub media download failed", transient=True) from None
        if len(raw) > 150 * 1024 * 1024 or len(raw) < 1024 or not raw.startswith((b"\x00\x00\x00", b"\x00\x00\x01")):
            raise ProviderError("INVALID_MEDIA", "RunningHub returned invalid MP4 media")
        target = Path(destination)
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_suffix(target.suffix + ".partial")
        partial.write_bytes(raw)
        partial.replace(target)
        try:
            probe = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-of", "json", str(target)],
                                   capture_output=True, text=True, check=True, timeout=20)
            duration = float(json.loads(probe.stdout)["format"]["duration"])
        except (OSError, subprocess.SubprocessError, KeyError, ValueError, IndexError):
            target.unlink(missing_ok=True)
            raise ProviderError("INVALID_MEDIA", "RunningHub MP4 probe failed") from None
        return {"local_path": str(target), "sha256": hashlib.sha256(raw).hexdigest(),
                "size_bytes": len(raw), "mime": "video/mp4", "duration": duration,
                "metadata": {"provider": "runninghub", "provider_task_id": str(provider_task_id)}}
