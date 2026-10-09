"""Creator HTTP layer. Formal creative and film objects are written only through film_core.Core."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import subprocess
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError
from film_core.h3_profile import darl_h3_profile

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB = ROOT / 'output' / 'h3-002-2026-10-09' / 'production.sqlite'
APP_SCHEMA = '''
CREATE TABLE IF NOT EXISTS impact_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, project_id TEXT NOT NULL, source_kind TEXT NOT NULL,
 source_id TEXT NOT NULL, clip_id TEXT, level TEXT NOT NULL, message TEXT NOT NULL,
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS timeline_items (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, clip_id TEXT NOT NULL, take_id TEXT NOT NULL REFERENCES takes(id),
 position INTEGER NOT NULL, trim_in REAL NOT NULL DEFAULT 0, trim_out REAL,
 transition TEXT NOT NULL DEFAULT 'cut', volume REAL NOT NULL DEFAULT 1, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS timeline_subtitles (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, start REAL NOT NULL, end REAL NOT NULL,
 text TEXT NOT NULL, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS asset_current (
 project_id TEXT NOT NULL, owner_id TEXT NOT NULL, asset_id TEXT NOT NULL, version INTEGER NOT NULL,
 updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, PRIMARY KEY(project_id,owner_id));
'''


def uid(prefix: str) -> str:
    return prefix + '-' + uuid.uuid4().hex[:12]


def latest(core: Core, kind: str) -> list[dict]:
    rows = core.db.execute('''SELECT o.* FROM objects o JOIN
      (SELECT id, MAX(version) v FROM objects WHERE kind=? GROUP BY id) x
      ON x.id=o.id AND x.v=o.version WHERE o.kind=? ORDER BY o.created_at, o.id''', (kind, kind))
    return [{**dict(row), 'payload': json.loads(row['payload'])} for row in rows]


def belong(core: Core, kind: str, object_id: str, project_id: str) -> dict:
    item = core.get(kind, object_id)
    p = item['payload']
    if kind == 'project':
        owner = object_id
    elif kind == 'episode':
        owner = p.get('project_id')
    elif kind == 'scene':
        owner = belong(core, 'episode', p['episode_id'], project_id)['payload']['project_id']
    elif kind in {'shot', 'clip'}:
        belong(core, 'scene', p['scene_id'], project_id)
        owner = project_id
    elif kind == 'brief':
        belong(core, 'clip', p['clip_id'], project_id)
        owner = project_id
    else:
        owner = p.get('project_id')
        if owner is None and kind in {'character', 'character_look', 'location', 'prop'}:
            owner = project_id if any(x['id'] == object_id for x in project_world(core, project_id, kind)) else None
    if owner != project_id:
        raise DomainError('object does not belong to project')
    return item


def project_clips(core: Core, project_id: str) -> list[dict]:
    scene_ids = {s['id'] for s in latest(core, 'scene') if
                 any(e['id'] == s['payload'].get('episode_id') and e['payload'].get('project_id') == project_id
                     for e in latest(core, 'episode'))}
    return [c for c in latest(core, 'clip') if c['payload'].get('scene_id') in scene_ids]


def mark_impact(core: Core, project_id: str, source_kind: str, source_id: str,
                scene_id: str | None, message: str, level='Needs Reconfirmation') -> None:
    targets = [c for c in project_clips(core, project_id) if scene_id is None or c['payload']['scene_id'] == scene_id]
    if not targets:
        core.db.execute('INSERT INTO impact_events(project_id,source_kind,source_id,clip_id,level,message) VALUES (?,?,?,?,?,?)',
                        (project_id, source_kind, source_id, None, level, message))
    for clip in targets:
        core.db.execute('INSERT INTO impact_events(project_id,source_kind,source_id,clip_id,level,message) VALUES (?,?,?,?,?,?)',
                        (project_id, source_kind, source_id, clip['id'], level, message))
    core.db.commit()


def provider_status() -> dict:
    key = os.getenv('DARL_API_KEY')
    video = '服务未启动' if os.getenv('H3_SERVER_ON') != '1' else ('可用' if key else '未配置')
    return {'llm': '未配置' if not os.getenv('LLM_API_KEY') else '可用',
            'image': '未配置' if not os.getenv('IMAGE_API_KEY') else '可用',
            'h3': video,
            'h3_message': 'H3 视频服务器当前未启动。你可以继续完成镜头和制作计划，启动视频服务器后再生成。'
            if video == '服务未启动' else ('请在服务端配置 DARL_API_KEY。' if video == '未配置' else 'H3 已按运行配置标记为可用。')}


class VersionedInput(BaseModel):
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_version: int | None = None
    source: str = 'creator'
    status: str = 'draft'


class MappingInput(BaseModel):
    shot_id: str
    ordinal: int
    shot_start: float
    shot_end: float
    clip_start: float
    clip_end: float
    cut_before: bool = False


class HandoffInput(BaseModel):
    upstream_clip_id: str
    kind: str = 'state'
    at_second: float = 0
    duration: float = 3
    assessment: str = ''


class AssetCurrentInput(BaseModel):
    version: int


class ReferenceInput(BaseModel):
    asset_id: str
    asset_version: int
    role: str


class SelectionInput(BaseModel):
    take_id: str
    actor: str = 'local-creator'


class ObserveInput(BaseModel):
    take_id: str
    state: dict[str, Any]
    observer: str = 'local-creator'


class TimelineInput(BaseModel):
    clip_id: str
    take_id: str
    trim_in: float = 0
    trim_out: float | None = None
    transition: str = 'cut'
    volume: float = 1


class TimelinePatch(BaseModel):
    position: int | None = None
    take_id: str | None = None
    trim_in: float | None = None
    trim_out: float | None = None
    transition: str | None = None
    volume: float | None = None


class SubtitleInput(BaseModel):
    start: float
    end: float
    text: str


def create_app(db_path: str | Path | None = None, media_root: str | Path | None = None,
               test_mode: bool = False) -> FastAPI:
    path = Path(db_path or os.getenv('FILM_STUDIO_DB') or (DEFAULT_DB if DEFAULT_DB.exists() else ROOT / 'output' / 'studio.sqlite'))
    media_dir = Path(media_root or os.getenv('FILM_STUDIO_MEDIA') or ROOT / 'output' / 'studio-media')
    path.parent.mkdir(parents=True, exist_ok=True)
    boot = Core(str(path), test_mode=test_mode)
    boot.db.executescript(APP_SCHEMA)
    boot.close()
    app = FastAPI(title='AI Film Studio API', version='0.3')
    app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000',
                                                       'http://localhost:3001', 'http://127.0.0.1:3001'],
                       allow_methods=['*'], allow_headers=['*'])

    def execute(fn):
        core = Core(str(path), test_mode=test_mode)
        try:
            return fn(core)
        except DomainError as exc:
            raise HTTPException(400, str(exc)) from exc
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, 'conflicting record') from exc
        finally:
            core.close()

    def update(core, kind, object_id, body: VersionedInput):
        old = core.get(kind, object_id)
        if body.expected_version != old['version']:
            raise HTTPException(409, 'version changed; reload before saving')
        merged = {**old['payload'], **body.payload}
        return core.put(kind, object_id, merged, body.source, body.status)

    @app.get('/api/health')
    def health():
        return {'ok': True, 'database': str(path), 'provider': provider_status()}

    @app.get('/api/providers')
    def providers():
        return provider_status()

    @app.get('/api/model-profiles')
    def profiles():
        return execute(lambda c: latest(c, 'model_profile'))

    @app.get('/api/projects')
    def projects(q: str = ''):
        return execute(lambda c: [p for p in latest(c, 'project') if q.lower() in p['payload'].get('title', '').lower()])

    @app.post('/api/projects')
    def create_project(body: VersionedInput):
        def op(c):
            title = str(body.payload.get('title', '')).strip()
            ratio = body.payload.get('aspect_ratio', '16:9')
            if not title or ratio not in {'16:9', '9:16', '1:1', '4:3', '3:4', '21:9'}:
                raise DomainError('project title and valid aspect ratio required')
            project_id = uid('project')
            item = c.put('project', project_id, {'title': title, 'aspect_ratio': ratio,
                'idea': body.payload.get('idea', ''), 'script': body.payload.get('script') or body.payload.get('idea', ''),
                'preferences': body.payload.get('preferences', '')}, 'creator', 'approved')
            episode = c.put('episode', uid('episode'), {'project_id': project_id, 'number': 1, 'title': '第一集'}, 'creator')
            return {'project': item, 'episode': episode}
        return execute(op)

    @app.get('/api/projects/{pid}')
    def get_project(pid: str):
        return execute(lambda c: c.get('project', pid))

    @app.patch('/api/projects/{pid}')
    def patch_project(pid: str, body: VersionedInput):
        def op(c):
            item = update(c, 'project', pid, body)
            if any(k in body.payload for k in ('script', 'idea')):
                mark_impact(c, pid, 'project', pid, None, '剧本内容已改变；请重新确认相关镜头与制作方案。')
            return item
        return execute(op)

    @app.get('/api/projects/{pid}/episodes')
    def episodes(pid: str):
        return execute(lambda c: [e for e in latest(c, 'episode') if e['payload'].get('project_id') == pid])

    @app.get('/api/projects/{pid}/scenes')
    def scenes(pid: str):
        def op(c):
            episodes = {e['id'] for e in latest(c, 'episode') if e['payload'].get('project_id') == pid}
            return sorted([s for s in latest(c, 'scene') if s['payload'].get('episode_id') in episodes and s['status'] != 'archived'],
                          key=lambda s: (s['payload'].get('ordinal', 0), s['created_at']))
        return execute(op)

    @app.post('/api/projects/{pid}/scenes')
    def add_scene(pid: str, body: VersionedInput):
        def op(c):
            episode_id = body.payload.get('episode_id') or next((e['id'] for e in latest(c, 'episode') if e['payload'].get('project_id') == pid), None)
            if not episode_id:
                raise DomainError('episode missing')
            belong(c, 'episode', episode_id, pid)
            if not str(body.payload.get('story', '')).strip():
                raise DomainError('scene story required')
            payload = {'episode_id': episode_id, 'ordinal': body.payload.get('ordinal', 0),
                       'place': body.payload.get('place', ''), 'story': body.payload['story'],
                       'ready_for_directing': False}
            return c.put('scene', uid('scene'), payload, 'creator', 'draft')
        return execute(op)

    @app.patch('/api/projects/{pid}/scenes/{sid}')
    def patch_scene(pid: str, sid: str, body: VersionedInput):
        def op(c):
            belong(c, 'scene', sid, pid)
            item = update(c, 'scene', sid, body)
            mark_impact(c, pid, 'scene', sid, sid, '场次已修改；相关镜头、制作方案与已有 Take 需要重新确认。')
            return item
        return execute(op)

    @app.delete('/api/projects/{pid}/scenes/{sid}')
    def archive_scene(pid: str, sid: str, expected_version: int):
        def op(c):
            scene = belong(c, 'scene', sid, pid)
            if scene['version'] != expected_version:
                raise HTTPException(409, 'version changed; reload before deleting')
            mark_impact(c, pid, 'scene', sid, sid, '场次已归档；历史镜头、Clip 与 Take 保留。', 'Must Replan / Rebuild')
            return c.put('scene', sid, scene['payload'], 'creator', 'archived')
        return execute(op)

    @app.get('/api/projects/{pid}/world/{kind}')
    def world_list(pid: str, kind: str):
        if kind not in {'character', 'character_look', 'location', 'prop', 'asset_version'}:
            raise HTTPException(404)
        return execute(lambda c: project_world(c, pid, kind))

    @app.post('/api/projects/{pid}/world/{kind}')
    def world_create(pid: str, kind: str, body: VersionedInput):
        if kind not in {'character', 'character_look', 'location', 'prop'}:
            raise HTTPException(404)
        def op(c):
            c.get('project', pid)
            payload = {**body.payload, 'project_id': pid}
            if kind == 'character' and not payload.get('name'):
                raise DomainError('character name required')
            if kind in {'location', 'prop'} and not payload.get('identity'):
                raise DomainError('identity required')
            if kind == 'character_look' and not payload.get('character_id'):
                raise DomainError('character required for look')
            if kind == 'character_look':
                belong(c, 'character', payload['character_id'], pid)
            return c.put(kind, uid(kind), payload, 'creator', 'approved')
        return execute(op)

    @app.patch('/api/projects/{pid}/world/{kind}/{oid}')
    def world_update(pid: str, kind: str, oid: str, body: VersionedInput):
        if kind not in {'character', 'character_look', 'location', 'prop'}:
            raise HTTPException(404)
        def op(c):
            belong(c, kind, oid, pid)
            item = update(c, kind, oid, body)
            mark_impact(c, pid, kind, oid, None, '人物或世界身份已变更；后续片段存在连续性风险。')
            return item
        return execute(op)

    @app.post('/api/projects/{pid}/assets/upload')
    async def upload_asset(pid: str, owner_id: str, purpose: str, file: UploadFile = File(...)):
        allowed = {'image/png': '.png', 'image/jpeg': '.jpg', 'image/webp': '.webp'}
        if file.content_type not in allowed:
            raise HTTPException(415, 'only PNG, JPEG and WebP images are allowed')
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024 or not content:
            raise HTTPException(413, 'image must be 1 byte to 10 MB')
        signatures = {
            'image/png': content.startswith(b'\x89PNG\r\n\x1a\n'),
            'image/jpeg': content.startswith(b'\xff\xd8\xff'),
            'image/webp': content.startswith(b'RIFF') and content[8:12] == b'WEBP',
        }
        if not signatures[file.content_type]:
            raise HTTPException(415, 'file signature does not match image type')
        def op(c):
            c.get('project', pid)
            if not any(x['id'] == owner_id for kind in ('character', 'character_look', 'location', 'prop') for x in project_world(c, pid, kind)):
                raise DomainError('asset owner missing')
            asset_id = 'asset-' + hashlib.sha256((owner_id + '\0' + purpose).encode()).hexdigest()[:16]
            media_dir.mkdir(parents=True, exist_ok=True)
            dest = media_dir / (uid('upload') + allowed[file.content_type])
            dest.write_bytes(content)
            item = c.put('asset_version', asset_id, {'project_id': pid, 'owner_id': owner_id,
                'purpose': purpose, 'uri': str(dest), 'media_type': 'image',
                'sha256': hashlib.sha256(content).hexdigest(), 'mime': file.content_type}, 'creator-upload')
            mark_impact(c, pid, 'asset_version', asset_id, None,
                        '视觉素材有新版本；请检查后续片段是否需要更新参考。')
            return item
        return execute(op)

    @app.get('/api/media-asset/{aid}')
    def serve_asset(aid: str, version: int | None = None):
        def op(c):
            asset = c.get('asset_version', aid, version)['payload']
            target = Path(asset.get('uri', '')).resolve()
            if not target.is_file() or not target.is_relative_to(media_dir.resolve()):
                raise DomainError('managed asset missing or outside media directory')
            return FileResponse(target, media_type=asset.get('mime', 'image/jpeg'))
        return execute(op)

    @app.post('/api/projects/{pid}/assets/{aid}/current')
    def choose_asset(pid: str, aid: str, body: AssetCurrentInput):
        def op(c):
            asset = c.get('asset_version', aid, body.version)
            p = asset['payload']
            if p.get('project_id') != pid:
                raise DomainError('asset belongs to another project')
            c.db.execute('INSERT INTO asset_current(project_id,owner_id,asset_id,version) VALUES (?,?,?,?) '
                         'ON CONFLICT(project_id,owner_id) DO UPDATE SET asset_id=excluded.asset_id,version=excluded.version,updated_at=CURRENT_TIMESTAMP',
                         (pid, p['owner_id'], aid, body.version))
            c.db.commit()
            mark_impact(c, pid, 'asset_current', aid, None,
                        '当前视觉版本已切换；相关后续片段需要检查连续性。')
            return {'owner_id': p['owner_id'], 'asset_id': aid, 'version': body.version}
        return execute(op)

    @app.get('/api/projects/{pid}/visual-prep')
    def visual_prep(pid: str):
        def op(c):
            current_owners = {r['owner_id'] for r in c.db.execute('SELECT owner_id FROM asset_current WHERE project_id=?', (pid,))}
            result = []
            for scene in scenes_for(c, pid):
                missing = []
                for clip in project_clips(c, pid):
                    if clip['payload']['scene_id'] != scene['id']:
                        continue
                    try:
                        brief = c.get('brief', 'brief:' + clip['id'])['payload']
                    except DomainError:
                        continue
                    for subject in brief.get('subjects', []):
                        for kind, key in [('character', 'character_id'), ('character_look', 'look_id')]:
                            oid = subject.get(key)
                            if oid and oid not in current_owners:
                                item = c.get(kind, oid)['payload']
                                missing.append(item.get('name') or item.get('description') or oid)
                    location_id = brief.get('environment', {}).get('location_id')
                    if location_id and location_id not in current_owners:
                        missing.append(c.get('location', location_id)['payload'].get('identity', location_id))
                result.append({'scene_id': scene['id'], 'scene': scene['payload'].get('place', ''),
                               'missing_visual_anchors': list(dict.fromkeys(missing))})
            return result
        return execute(op)

    @app.get('/api/projects/{pid}/shots')
    def shots(pid: str, scene_id: str | None = None):
        def op(c):
            return sorted([s for s in latest(c, 'shot') if (not scene_id or s['payload'].get('scene_id') == scene_id)
                           and any(sc['id'] == s['payload'].get('scene_id') for sc in scenes_for(c, pid))],
                          key=lambda s: (s['payload'].get('ordinal', 0), s['created_at']))
        return execute(op)

    @app.post('/api/projects/{pid}/shots')
    def create_shot(pid: str, body: VersionedInput):
        def op(c):
            scene_id = body.payload.get('scene_id')
            belong(c, 'scene', scene_id, pid)
            if not body.payload.get('description') or float(body.payload.get('duration', 0)) <= 0:
                raise DomainError('shot description and duration required')
            return c.put('shot', uid('shot'), {**body.payload, 'director_approved': False}, 'creator', 'draft')
        return execute(op)

    @app.patch('/api/projects/{pid}/shots/{sid}')
    def patch_shot(pid: str, sid: str, body: VersionedInput):
        def op(c):
            shot = belong(c, 'shot', sid, pid)
            if shot['status'] == 'archived':
                raise DomainError('archived shot cannot be edited')
            item = update(c, 'shot', sid, body)
            mark_impact(c, pid, 'shot', sid, shot['payload']['scene_id'], '镜头已修改；相关 Clip 和最终制作方案需重新准备。', 'Must Replan / Rebuild')
            return item
        return execute(op)

    @app.delete('/api/projects/{pid}/shots/{sid}')
    def archive_shot(pid: str, sid: str, expected_version: int):
        def op(c):
            shot = belong(c, 'shot', sid, pid)
            if shot['version'] != expected_version:
                raise HTTPException(409, 'version changed; reload before deleting')
            mark_impact(c, pid, 'shot', sid, shot['payload']['scene_id'], '镜头已归档；下游需重新规划。', 'Must Replan / Rebuild')
            return c.put('shot', sid, shot['payload'], 'creator', 'archived')
        return execute(op)

    @app.get('/api/projects/{pid}/clips')
    def clips(pid: str, scene_id: str | None = None):
        def op(c):
            return [clip_read(c, x) for x in project_clips(c, pid) if not scene_id or x['payload']['scene_id'] == scene_id]
        return execute(op)

    @app.post('/api/projects/{pid}/clips')
    def create_clip(pid: str, body: VersionedInput):
        def op(c):
            belong(c, 'scene', body.payload.get('scene_id'), pid)
            if body.payload.get('handoff') not in Core.HANDOFFS or float(body.payload.get('duration', 0)) <= 0:
                raise DomainError('valid clip duration and generation strategy required')
            item = c.put('clip', uid('clip'), body.payload, 'creator', 'draft')
            return clip_read(c, item)
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/mappings')
    def add_mapping(pid: str, cid: str, body: MappingInput):
        def op(c):
            clip = belong(c, 'clip', cid, pid)
            shot = belong(c, 'shot', body.shot_id, pid)
            if shot['payload']['scene_id'] != clip['payload']['scene_id']:
                raise DomainError('shot and clip must share scene')
            proposed = c.mappings(cid) + [{'clip_id': cid, **body.model_dump()}]
            result = c.replace_mappings(cid, proposed, 'creator')
            mark_impact(c, pid, 'shot_clip', cid, clip['payload']['scene_id'],
                        'Shot 与 Clip 的时间映射已改变；最终制作方案需重新确认。', 'Must Replan / Rebuild')
            return result
        return execute(op)

    @app.put('/api/projects/{pid}/clips/{cid}/mappings')
    def replace_mappings(pid: str, cid: str, bodies: list[MappingInput], expected_revision: int):
        def op(c):
            clip = belong(c, 'clip', cid, pid)
            result = c.replace_mappings(cid, [{'clip_id': cid, **b.model_dump()} for b in bodies],
                                        'creator', expected_revision)
            mark_impact(c, pid, 'shot_clip', cid, clip['payload']['scene_id'],
                        'Shot 与 Clip 的时间映射已改变；最终制作方案需重新确认。', 'Must Replan / Rebuild')
            return result
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/dependencies/{upstream}')
    def add_clip_dependency(pid: str, cid: str, upstream: str, kind: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            belong(c, 'clip', upstream, pid)
            c.add_dependency(cid, upstream, kind)
            return {'ok': True}
        return execute(op)

    @app.get('/api/projects/{pid}/clips/{cid}/briefs')
    def briefs(pid: str, cid: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            return [b for b in c.db.execute('SELECT * FROM objects WHERE kind=? AND id=? ORDER BY version DESC', ('brief', 'brief:' + cid))]
        def serialize(c):
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in op(c)]
        return execute(serialize)

    @app.get('/api/projects/{pid}/clips/{cid}/references')
    def references(pid: str, cid: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            try:
                brief = c.get('brief', 'brief:' + cid)['payload']
            except DomainError:
                return []
            return [c.get('reference_binding', rid) for rid in brief.get('references', [])]
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/references')
    def bind_reference(pid: str, cid: str, body: ReferenceInput):
        def op(c):
            belong(c, 'clip', cid, pid)
            asset = c.get('asset_version', body.asset_id, body.asset_version)
            if asset['payload'].get('project_id') != pid or body.role not in {
                'character_identity', 'character_look', 'environment_identity', 'prop_identity',
                'composition_reference', 'continuity_anchor', 'first_frame', 'last_frame'}:
                raise DomainError('invalid reference source or role')
            binding_id = uid('reference')
            binding = c.put('reference_binding', binding_id, {'asset_id': body.asset_id,
                'asset_version': body.asset_version, 'role': body.role, 'media_type': 'image',
                'uri': asset['payload']['uri']}, 'creator-reference-plan')
            brief = c.get('brief', 'brief:' + cid)
            payload = {**brief['payload'], 'references': brief['payload'].get('references', []) + [binding_id]}
            revised = c.save_brief(cid, payload, 'creator-reference-plan')
            return {'binding': binding, 'brief': revised}
        return execute(op)

    @app.get('/api/projects/{pid}/control-media')
    def control_media(pid: str):
        def op(c):
            ids = {t['id'] for t in c.db.execute('SELECT * FROM takes') if
                   t['clip_id'] in {clip['id'] for clip in project_clips(c, pid)}}
            return [m for m in latest(c, 'control_media') if m['payload'].get('source_take_id') in ids]
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/briefs')
    def save_brief(pid: str, cid: str, body: VersionedInput):
        def op(c):
            belong(c, 'clip', cid, pid)
            prior = c.db.execute('SELECT MAX(version) FROM objects WHERE kind=? AND id=?', ('brief', 'brief:' + cid)).fetchone()[0]
            if body.expected_version != prior:
                raise HTTPException(409, 'brief version changed; reload before saving')
            if body.payload.get('clip_id') != cid:
                raise DomainError('brief clip mismatch')
            return c.save_brief(cid, body.payload, body.source, body.status)
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/rebase')
    def rebase(pid: str, cid: str, upstream: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            belong(c, 'clip', upstream, pid)
            return c.rebase_brief_state(cid, upstream)
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/prepare-handoff')
    def prepare_handoff(pid: str, cid: str, body: HandoffInput):
        """Explicit human-reviewed continuity media; never promotes a Take to a master asset."""
        def op(c):
            belong(c, 'clip', cid, pid)
            upstream = body.upstream_clip_id
            belong(c, 'clip', upstream, pid)
            dep = c.db.execute('SELECT kind FROM dependencies WHERE clip_id=? AND upstream_clip_id=?',
                               (cid, upstream)).fetchone()
            if not dep:
                raise DomainError('declared upstream dependency missing')
            selection = c.selection(upstream)
            if not selection:
                raise DomainError('wait for upstream Take selection')
            c.next_clip_context(upstream)
            take = c.take(selection['take_id'])
            if take['test_only'] or not take['media_id']:
                raise DomainError('real selected Take required for continuity media')
            media = c.media(take['media_id'])
            source = Path(media['local_path']).resolve()
            if not source.is_file() or body.at_second < 0 or not body.assessment.strip():
                raise DomainError('real media, valid timestamp and human assessment required')
            if media['duration'] is not None and body.at_second >= media['duration']:
                raise DomainError('timestamp exceeds source duration')
            media_dir.mkdir(parents=True, exist_ok=True)
            if body.kind == 'state':
                return c.rebase_brief_state(cid, upstream)
            if body.kind == 'stable_tail':
                if dep['kind'] != 'VIDEO_CONTINUATION' or not 2 <= body.duration <= 15:
                    raise DomainError('video continuation needs declared dependency and 2–15s tail')
                if media['duration'] is not None and body.at_second + body.duration > media['duration']:
                    raise DomainError('tail exceeds source duration')
                dest = media_dir / (uid('stable-tail') + '.mp4')
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(body.at_second), '-i', str(source),
                                '-t', str(body.duration), '-c:v', 'libx264', '-crf', '18', '-an', str(dest)],
                               check=True, timeout=120)
                if not dest.is_file() or not dest.stat().st_size:
                    raise DomainError('Stable Tail extraction failed')
                control_id = uid('tail')
                c.create_stable_tail(control_id, upstream, take['id'], str(dest),
                                     {'stable': True, 'human_assessment': body.assessment})
                payload = c.get('control_media', control_id)['payload']
                c.put('control_media', control_id, {**payload, 'duration': body.duration,
                      'source_selection_id': selection['id']}, 'human-reviewed-tail')
                brief = c.rebase_brief_state(cid, upstream)
                return {'control_media_id': control_id, 'brief': brief}
            if body.kind == 'visual_anchor':
                if dep['kind'] == 'VIDEO_CONTINUATION':
                    raise DomainError('video continuation requires a Stable Tail')
                dest = media_dir / (uid('visual-anchor') + '.png')
                subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(body.at_second), '-i', str(source),
                                '-frames:v', '1', str(dest)], check=True, timeout=120)
                if not dest.is_file() or not dest.stat().st_size:
                    raise DomainError('visual anchor extraction failed')
                control_id, binding_id = uid('anchor'), uid('binding')
                c.put('control_media', control_id, {'role': 'visual_anchor', 'source_take_id': take['id'],
                    'source_selection_id': selection['id'], 'uri': str(dest),
                    'assessment': body.assessment}, 'human-reviewed-frame')
                c.put('reference_binding', binding_id, {'control_media_id': control_id,
                    'role': 'continuity_anchor', 'media_type': 'image', 'uri': str(dest)}, 'production-plan')
                current = c.get('brief', 'brief:' + cid)['payload']
                c.save_brief(cid, {**current, 'references': list(dict.fromkeys(current.get('references', []) + [binding_id]))},
                             'visual-anchor-plan')
                brief = c.rebase_brief_state(cid, upstream)
                return {'control_media_id': control_id, 'reference_binding_id': binding_id, 'brief': brief}
            raise DomainError('invalid handoff kind')
        return execute(op)

    @app.get('/api/projects/{pid}/clips/{cid}/readiness')
    def readiness(pid: str, cid: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            try:
                brief = c.get('brief', 'brief:' + cid)
            except DomainError:
                return {'status': 'NOT_READY', 'reasons': [{'code': 'BRIEF_MISSING', 'field': 'brief'}]}
            qa = c.brief_qa(brief)
            return {'status': qa.status, 'reasons': list(qa.reasons), 'brief_version': brief['version']}
        return execute(op)

    @app.get('/api/projects/{pid}/jobs')
    def jobs(pid: str, clip_id: str | None = None):
        def op(c):
            ids = {x['id'] for x in project_clips(c, pid)}
            result = []
            for row in c.db.execute('SELECT id FROM jobs ORDER BY created_at DESC'):
                job = c.job(row['id'])
                if job['snapshot']['task']['clip_id'] in ids and (not clip_id or job['snapshot']['task']['clip_id'] == clip_id):
                    result.append(job)
            return result
        return execute(op)

    @app.get('/api/projects/{pid}/jobs/{jid}')
    def job_detail(pid: str, jid: str):
        def op(c):
            job = c.job(jid)
            belong(c, 'clip', job['snapshot']['task']['clip_id'], pid)
            return {**job, 'events': [{**dict(r), 'metadata': json.loads(r['metadata'])}
                    for r in c.db.execute('SELECT * FROM job_events WHERE job_id=? ORDER BY id', (jid,))]}
        return execute(op)

    @app.get('/api/projects/{pid}/compiled-tasks')
    def compiled_tasks(pid: str, clip_id: str | None = None):
        def op(c):
            ids = {x['id'] for x in project_clips(c, pid)}
            return [{**dict(r), 'payload': json.loads(r['payload'])} for r in c.db.execute(
                'SELECT * FROM compiled_tasks ORDER BY created_at DESC')
                if r['clip_id'] in ids and (clip_id is None or r['clip_id'] == clip_id)]
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/generate')
    def generate(pid: str, cid: str, retry_of: str | None = None):
        status = provider_status()['h3']
        if status != '可用':
            raise HTTPException(503, {'code': 'PROVIDER_UNAVAILABLE', 'message': provider_status()['h3_message']})
        def op(c):
            belong(c, 'clip', cid, pid)
            previous = [c.job(r['id']) for r in c.db.execute('SELECT id FROM jobs WHERE task_id IN (SELECT id FROM compiled_tasks WHERE clip_id=?) ORDER BY created_at DESC', (cid,))]
            if any(j['status'] in {'queued', 'running'} for j in previous):
                raise DomainError('a generation job is already active for this clip')
            if previous and previous[0]['status'] == 'failed' and retry_of != previous[0]['id']:
                raise DomainError('previous failed job requires an explicit retry_of after review')
            if retry_of and (not previous or previous[0]['id'] != retry_of or previous[0]['status'] != 'failed'):
                raise DomainError('retry_of must name the latest failed Job for this Clip')
            profile_id = 'h3-darl'
            if not any(p['id'] == profile_id for p in latest(c, 'model_profile')):
                c.put('model_profile', profile_id, darl_h3_profile(False), 'documented-profile', 'documented')
            task_id, job_id = uid('task'), uid('job')
            continuation = None
            if c.get('clip', cid)['payload']['handoff'] == 'VIDEO_CONTINUATION':
                dep = c.db.execute("SELECT upstream_clip_id FROM dependencies WHERE clip_id=? AND kind='VIDEO_CONTINUATION'", (cid,)).fetchone()
                if not dep:
                    raise DomainError('continuation dependency missing')
                selected = c.selection(dep['upstream_clip_id'])
                control = c.db.execute("SELECT id FROM objects WHERE kind='control_media' AND json_extract(payload,'$.role')='stable_tail' AND json_extract(payload,'$.source_take_id')=? ORDER BY created_at DESC LIMIT 1",
                                       (selected['take_id'] if selected else '',)).fetchone()
                if not control:
                    raise DomainError('selected upstream Stable Tail missing')
                continuation = c.continuation_source(dep['upstream_clip_id'], control['id'])
            task = c.compile_h3(task_id, 'brief:' + cid, profile_id,
                                parameters={'resolution': '480P', 'num_inference_steps': 20, 'turbo': False, 'watermark': False},
                                continuation=continuation)
            if not c.preflight(task_id).ready:
                raise DomainError('model preflight not ready: ' + json.dumps(c.preflight(task_id).reasons))
            adapter = DarlH3Adapter()
            adapter.build_request(task)
            c.create_job(job_id, task_id, retry_of=retry_of,
                         cost_estimate={'candidate_limit': 1, 'resolution': '480P'})
            try:
                response = adapter.submit(task, job_id)
            except ProviderError as exc:
                c.job_event(job_id, 'failed', {'provider_error': exc.as_dict()})
                raise HTTPException(503, {'code': 'PROVIDER_UNAVAILABLE' if exc.code == 'fail_to_fetch_task' and exc.http_status == 404 else exc.code,
                                          'message': 'H3 视频服务器当前未启动。' if exc.code == 'fail_to_fetch_task' and exc.http_status == 404 else str(exc),
                                          'job_id': job_id}) from exc
            c.job_event(job_id, 'running', {'provider_task_id': response['id'], 'create_response': response})
            return {'job': c.job(job_id), 'expected_minutes': 3}
        return execute(op)

    @app.post('/api/projects/{pid}/jobs/{jid}/sync')
    def sync_job(pid: str, jid: str):
        def op(c):
            job = c.job(jid)
            belong(c, 'clip', job['snapshot']['task']['clip_id'], pid)
            if job['status'] != 'running':
                raise DomainError('job is not running')
            provider_id = job['metadata'].get('provider_task_id')
            if not provider_id:
                raise DomainError('provider task id missing')
            adapter = DarlH3Adapter()
            try:
                response = adapter.poll(provider_id)
            except ProviderError as exc:
                raise HTTPException(503, exc.as_dict()) from exc
            if response['status'] == 'failed':
                return c.job_event(jid, 'failed', {'provider_task_id': provider_id, 'query_response': response})
            if response['status'] != 'succeeded':
                return {'job': job, 'provider_status': response['status']}
            info = adapter.download(provider_id, media_dir / (uid('take') + '.mp4'))
            media_id = uid('media')
            c.register_media(media_id, **{k: v for k, v in info.items() if k != 'metadata'}, metadata=info['metadata'])
            c.job_event(jid, 'succeeded', {'provider_task_id': provider_id, 'query_response': response, 'media_id': media_id})
            take = c.record_take(uid('take'), jid, info['local_path'], response, media_id=media_id)
            return {'job': c.job(jid), 'take': take}
        return execute(op)

    @app.get('/api/projects/{pid}/takes')
    def takes(pid: str, clip_id: str | None = None):
        def op(c):
            ids = {x['id'] for x in project_clips(c, pid)}
            return [dict(r) for r in c.db.execute('SELECT * FROM takes ORDER BY created_at DESC')
                    if r['clip_id'] in ids and (not clip_id or r['clip_id'] == clip_id)]
        return execute(op)

    @app.get('/api/media/{mid}')
    def serve_media(mid: str):
        def op(c):
            media = c.media(mid)
            target = Path(media['local_path']).resolve()
            if not target.is_file() or not any(target.is_relative_to(root.resolve()) for root in (media_dir, ROOT / 'output')):
                raise DomainError('managed media missing or outside output')
            return FileResponse(target, media_type=media['mime'])
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/selection')
    def select(pid: str, cid: str, body: SelectionInput):
        def op(c):
            belong(c, 'clip', cid, pid)
            selection = c.select_take(cid, body.take_id, body.actor)
            for row in c.db.execute('SELECT clip_id FROM dependencies WHERE upstream_clip_id=?', (cid,)):
                c.db.execute('INSERT INTO impact_events(project_id,source_kind,source_id,clip_id,level,message) VALUES (?,?,?,?,?,?)',
                             (pid, 'selection', cid, row['clip_id'], 'Must Replan / Rebuild', '上游采用版本已改变；续接准备需重新确认。'))
            c.db.commit()
            return selection
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/observed')
    def observe(pid: str, cid: str, body: ObserveInput):
        def op(c):
            belong(c, 'clip', cid, pid)
            if c.take(body.take_id)['clip_id'] != cid:
                raise DomainError('take belongs to another clip')
            oid = uid('observed')
            c.observe(oid, body.take_id, body.state, body.observer)
            return {'id': oid, 'take_id': body.take_id, 'state': body.state}
        return execute(op)

    @app.get('/api/projects/{pid}/clips/{cid}/observed')
    def observed_history(pid: str, cid: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            return [{**dict(r), 'payload': json.loads(r['payload'])}
                    for r in c.db.execute('SELECT o.* FROM observed_states o JOIN takes t ON t.id=o.take_id '
                                          'WHERE t.clip_id=? ORDER BY o.created_at DESC', (cid,))]
        return execute(op)

    @app.post('/api/projects/{pid}/clips/{cid}/canonical/{oid}')
    def canonical(pid: str, cid: str, oid: str, actor: str = 'local-creator'):
        return execute(lambda c: (belong(c, 'clip', cid, pid), c.confirm_state(cid, oid, actor))[1])

    @app.get('/api/projects/{pid}/clips/{cid}/canonical')
    def canonical_history(pid: str, cid: str):
        def op(c):
            belong(c, 'clip', cid, pid)
            return [{**dict(r), 'payload': json.loads(r['payload'])}
                    for r in c.db.execute('SELECT * FROM state_snapshots WHERE clip_id=? ORDER BY id DESC', (cid,))]
        return execute(op)

    @app.get('/api/projects/{pid}/reality')
    def reality(pid: str):
        def op(c):
            result = {}
            for clip in project_clips(c, pid):
                cid = clip['id']
                selected = c.selection(cid)
                try:
                    snapshot = c.snapshot(cid)
                except DomainError:
                    snapshot = None
                result[cid] = {'selection': selected, 'canonical': snapshot,
                               'needs_confirmation': bool(selected and (not snapshot or snapshot['selection_id'] != selected['id']))}
            return result
        return execute(op)

    @app.get('/api/projects/{pid}/impacts')
    def impacts(pid: str):
        return execute(lambda c: [dict(r) for r in c.db.execute('SELECT * FROM impact_events WHERE project_id=? ORDER BY id DESC LIMIT 100', (pid,))])

    @app.get('/api/projects/{pid}/timeline')
    def timeline(pid: str):
        def op(c):
            return {'items': [dict(r) for r in c.db.execute('SELECT * FROM timeline_items WHERE project_id=? ORDER BY position', (pid,))],
                    'subtitles': [dict(r) for r in c.db.execute('SELECT * FROM timeline_subtitles WHERE project_id=? ORDER BY start', (pid,))]}
        return execute(op)

    @app.post('/api/projects/{pid}/timeline/items')
    def timeline_add(pid: str, body: TimelineInput):
        def op(c):
            belong(c, 'clip', body.clip_id, pid)
            selection = c.selection(body.clip_id)
            if not selection or selection['take_id'] != body.take_id:
                raise DomainError('timeline requires current selected Take')
            take = c.take(body.take_id)
            if (take['test_only'] and not c.test_mode) or not take['media_id'] or not Path(take['media_uri']).is_file():
                raise DomainError('timeline requires real managed media')
            if body.trim_in < 0 or body.trim_out is not None and body.trim_out <= body.trim_in or not 0 <= body.volume <= 2 or body.transition not in {'cut', 'fade'}:
                raise DomainError('invalid timeline range or volume')
            pos = c.db.execute('SELECT COALESCE(MAX(position),-1)+1 FROM timeline_items WHERE project_id=?', (pid,)).fetchone()[0]
            item_id = uid('timeline')
            c.db.execute('INSERT INTO timeline_items(id,project_id,clip_id,take_id,position,trim_in,trim_out,transition,volume) VALUES (?,?,?,?,?,?,?,?,?)',
                         (item_id, pid, body.clip_id, body.take_id, pos, body.trim_in, body.trim_out, body.transition, body.volume))
            c.db.commit()
            return dict(c.db.execute('SELECT * FROM timeline_items WHERE id=?', (item_id,)).fetchone())
        return execute(op)

    @app.patch('/api/projects/{pid}/timeline/items/{iid}')
    def timeline_patch(pid: str, iid: str, body: TimelinePatch):
        def op(c):
            row = c.db.execute('SELECT * FROM timeline_items WHERE id=? AND project_id=?', (iid, pid)).fetchone()
            if not row:
                raise DomainError('timeline item missing')
            values = {**dict(row), **body.model_dump(exclude_none=True)}
            if values['take_id'] != row['take_id']:
                selection = c.selection(row['clip_id'])
                take = c.take(values['take_id'])
                if not selection or selection['take_id'] != values['take_id'] or (take['test_only'] and not c.test_mode) or not take['media_id'] or not Path(take['media_uri']).is_file():
                    raise DomainError('timeline replacement requires current selected managed Take')
            if values['trim_in'] < 0 or values['trim_out'] is not None and values['trim_out'] <= values['trim_in'] or not 0 <= values['volume'] <= 2 or values['transition'] not in {'cut', 'fade'}:
                raise DomainError('invalid timeline range or volume')
            c.db.execute('UPDATE timeline_items SET position=?,take_id=?,trim_in=?,trim_out=?,transition=?,volume=? WHERE id=?',
                         (values['position'], values['take_id'], values['trim_in'], values['trim_out'], values['transition'], values['volume'], iid))
            c.db.commit()
            return dict(c.db.execute('SELECT * FROM timeline_items WHERE id=?', (iid,)).fetchone())
        return execute(op)

    @app.delete('/api/projects/{pid}/timeline/items/{iid}')
    def timeline_delete(pid: str, iid: str):
        def op(c):
            c.db.execute('DELETE FROM timeline_items WHERE id=? AND project_id=?', (iid, pid))
            c.db.commit()
            return {'ok': True}
        return execute(op)

    @app.post('/api/projects/{pid}/timeline/subtitles')
    def subtitle_add(pid: str, body: SubtitleInput):
        def op(c):
            c.get('project', pid)
            if body.start < 0 or body.end <= body.start or not body.text.strip():
                raise DomainError('invalid subtitle')
            sid = uid('subtitle')
            c.db.execute('INSERT INTO timeline_subtitles(id,project_id,start,end,text) VALUES (?,?,?,?,?)',
                         (sid, pid, body.start, body.end, body.text))
            c.db.commit()
            return {'id': sid, **body.model_dump()}
        return execute(op)

    @app.post('/api/projects/{pid}/timeline/preview')
    def export_preview(pid: str):
        def op(c):
            rows = [dict(r) for r in c.db.execute('SELECT * FROM timeline_items WHERE project_id=? ORDER BY position', (pid,))]
            if not rows:
                raise DomainError('timeline is empty')
            media_dir.mkdir(parents=True, exist_ok=True)
            segments = []
            for row in rows:
                take = c.take(row['take_id'])
                selection = c.selection(row['clip_id'])
                if not selection or selection['take_id'] != take['id'] or take['test_only'] or not take['media_id']:
                    raise DomainError('timeline contains non-current or test Take')
                src = Path(c.media(take['media_id'])['local_path'])
                if not src.is_file():
                    raise DomainError('source media missing')
                target = media_dir / (uid('segment') + '.mp4')
                args = ['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(row['trim_in']), '-i', str(src)]
                if row['trim_out'] is not None:
                    args += ['-t', str(row['trim_out'] - row['trim_in'])]
                if row['transition'] == 'fade':
                    args += ['-vf', 'fade=t=in:st=0:d=0.25']
                args += ['-filter:a', f"volume={row['volume']}", '-c:v', 'libx264', '-c:a', 'aac', str(target)]
                subprocess.run(args, check=True, timeout=180)
                segments.append(target)
            manifest = media_dir / (uid('concat') + '.txt')
            manifest.write_text(''.join("file '" + str(x).replace("'", "'\\''") + "'\n" for x in segments))
            target = media_dir / (uid('preview') + '.mp4')
            subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', str(manifest),
                            '-c', 'copy', str(target)], check=True, timeout=180)
            subtitles = [dict(r) for r in c.db.execute(
                'SELECT * FROM timeline_subtitles WHERE project_id=? ORDER BY start', (pid,))]
            subtitle_path = None
            if subtitles:
                def stamp(seconds):
                    milliseconds = round(seconds * 1000)
                    hours, rem = divmod(milliseconds, 3600000)
                    minutes, rem = divmod(rem, 60000)
                    whole, milli = divmod(rem, 1000)
                    return f'{hours:02}:{minutes:02}:{whole:02},{milli:03}'
                subtitle_path = target.with_suffix('.srt')
                subtitle_path.write_text(''.join(
                    f"{i}\n{stamp(s['start'])} --> {stamp(s['end'])}\n{s['text']}\n\n"
                    for i, s in enumerate(subtitles, 1)), encoding='utf-8')
            return {'path': str(target), 'subtitle_path': str(subtitle_path) if subtitle_path else None,
                    'status': 'ready'}
        return execute(op)

    return app


def scenes_for(core: Core, project_id: str) -> list[dict]:
    episode_ids = {e['id'] for e in latest(core, 'episode') if e['payload'].get('project_id') == project_id}
    return [s for s in latest(core, 'scene') if s['payload'].get('episode_id') in episode_ids and s['status'] != 'archived']


def project_world(core: Core, project_id: str, kind: str) -> list[dict]:
    """Include legacy #002 fixture identities referenced by this project's Briefs."""
    core.get('project', project_id)
    if kind == 'asset_version':
        selected = {(r['owner_id'], r['asset_id'], r['version']) for r in core.db.execute(
            'SELECT owner_id,asset_id,version FROM asset_current WHERE project_id=?', (project_id,))}
        return [{**dict(r), 'payload': json.loads(r['payload']),
                 'is_current': (json.loads(r['payload']).get('owner_id'), r['id'], r['version']) in selected}
                for r in core.db.execute("SELECT * FROM objects WHERE kind='asset_version' ORDER BY created_at DESC")
                if json.loads(r['payload']).get('project_id') == project_id]
    visible = {x['id'] for x in latest(core, kind) if x['payload'].get('project_id') == project_id}
    clip_ids = {c['id'] for c in project_clips(core, project_id)}
    for brief in latest(core, 'brief'):
        p = brief['payload']
        if p.get('clip_id') not in clip_ids:
            continue
        if kind == 'character':
            visible.update(s.get('character_id') for s in p.get('subjects', []))
        elif kind == 'character_look':
            visible.update(s.get('look_id') for s in p.get('subjects', []))
        elif kind == 'location':
            visible.add(p.get('environment', {}).get('location_id'))
        elif kind == 'prop':
            visible.update(s.get('prop_id') for s in p.get('props', []))
    return [x for x in latest(core, kind) if x['id'] in visible]


def clip_read(core: Core, clip: dict) -> dict:
    cid = clip['id']
    mappings = core.mappings(cid)
    dependencies = [dict(r) for r in core.db.execute('SELECT * FROM dependencies WHERE clip_id=?', (cid,))]
    selection = core.selection(cid)
    return {**clip, 'mappings': mappings, 'mapping_revision': core.mapping_revision(cid), 'dependencies': dependencies,
            'selection': selection, 'take_count': core.db.execute('SELECT COUNT(*) FROM takes WHERE clip_id=?', (cid,)).fetchone()[0]}


app = create_app(test_mode=os.getenv('FILM_STUDIO_TEST_MODE') == '1')
