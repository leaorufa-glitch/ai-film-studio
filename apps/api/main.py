"""Creator HTTP layer. Formal creative and film objects are written only through film_core.Core."""
from __future__ import annotations
import hashlib
import json
import os
import sqlite3
import subprocess
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError, darl_execution_model
from film_core.h3_profile import LOCAL_H3_MODEL, H3_EXECUTION_MODELS, H3_PROFILE_IDS, current_h3_execution_model, darl_h3_profile
from .ai_providers import AIProviderError, DarlImageAdapter, DarlLLMAdapter
from .job_runtime import JobWorker, generation_provider, utcnow

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
CREATE TABLE IF NOT EXISTS ai_proposals (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, task TEXT NOT NULL, target_id TEXT,
 context TEXT NOT NULL, change TEXT NOT NULL, explanation TEXT NOT NULL,
 provenance TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
 resolved_at TEXT);
CREATE TABLE IF NOT EXISTS asset_candidates (
 id TEXT PRIMARY KEY, project_id TEXT NOT NULL, owner_id TEXT NOT NULL, purpose TEXT NOT NULL,
 prompt TEXT NOT NULL, media_id TEXT NOT NULL, provider TEXT NOT NULL, model TEXT NOT NULL,
 provenance TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
 created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, resolved_at TEXT);
CREATE TABLE IF NOT EXISTS job_runtime (
 job_id TEXT PRIMARY KEY, provider TEXT NOT NULL DEFAULT 'darl',
 provider_task_id TEXT, next_poll_at TEXT, poll_count INTEGER NOT NULL DEFAULT 0,
 transient_count INTEGER NOT NULL DEFAULT 0, download_attempts INTEGER NOT NULL DEFAULT 0,
 last_error_category TEXT, last_error TEXT, submitted_at TEXT, last_polled_at TEXT,
 completed_at TEXT, lease_owner TEXT, lease_until TEXT,
 submit_latency_ms INTEGER, poll_latency_ms INTEGER, download_latency_ms INTEGER);
CREATE TABLE IF NOT EXISTS active_generation (
 clip_id TEXT PRIMARY KEY, job_id TEXT NOT NULL, reserved_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS generation_requests (
 request_id TEXT PRIMARY KEY, project_id TEXT NOT NULL, clip_id TEXT NOT NULL,
 job_id TEXT, created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS system_config (
 key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE IF NOT EXISTS capability_packages (
 type TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, version INTEGER NOT NULL,
 status TEXT NOT NULL, scope TEXT NOT NULL, applicability TEXT NOT NULL,
 dependencies TEXT NOT NULL, provenance TEXT NOT NULL, published_at TEXT,
 PRIMARY KEY(type,id,version));
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
    self_hosted = os.getenv('H3_SERVER_ON') == '1'
    execution_model = current_h3_execution_model()
    return {'llm': '未配置' if not (os.getenv('LLM_API_KEY') or key) else '可用',
            'image': '未配置' if not (os.getenv('IMAGE_API_KEY') or key) else '可用',
            'h3': '可用' if key else '未配置', 'provider': 'darl',
            'execution_model': execution_model, 'execution_route': H3_EXECUTION_MODELS[execution_model],
            'self_hosted_h3': ('可用' if key else '未配置') if self_hosted else '服务未启动',
            'cloud_h3': '可用' if key else '未配置',
            'h3_message': '请在服务端配置 DARL_API_KEY。' if not key else
                ('当前执行路线：自建 H3。' if self_hosted else '自建 H3 未开启；新的生成使用云端 H3 · 备用。')}


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


class ProposalInput(BaseModel):
    task: str
    target_id: str | None = None
    instruction: str = ''
    selected_text: str = ''


class ImageCandidateInput(BaseModel):
    owner_id: str
    purpose: str
    prompt: str


class AdminConfigInput(BaseModel):
    key: str
    value: str


class AdminRetryInput(BaseModel):
    request_id: str


def create_app(db_path: str | Path | None = None, media_root: str | Path | None = None,
               test_mode: bool = False, start_worker: bool | None = None) -> FastAPI:
    path = Path(db_path or os.getenv('FILM_STUDIO_DB') or (DEFAULT_DB if DEFAULT_DB.exists() else ROOT / 'output' / 'studio.sqlite'))
    media_dir = Path(media_root or os.getenv('FILM_STUDIO_MEDIA') or ROOT / 'output' / 'studio-media')
    path.parent.mkdir(parents=True, exist_ok=True)
    boot = Core(str(path), test_mode=test_mode)
    boot.db.executescript(APP_SCHEMA)
    runtime_columns={r['name'] for r in boot.db.execute('PRAGMA table_info(job_runtime)')}
    if 'provider' not in runtime_columns:
        boot.db.execute("ALTER TABLE job_runtime ADD COLUMN provider TEXT NOT NULL DEFAULT 'darl'")
    for name in ('submit_latency_ms','poll_latency_ms','download_latency_ms'):
        if name not in runtime_columns:
            boot.db.execute(f'ALTER TABLE job_runtime ADD COLUMN {name} INTEGER')
    for key,value in {'llm_enabled':'true','image_enabled':'true','h3_enabled':'true',
                      'poll_seconds':'180','max_transient':'3','max_download':'2'}.items():
        boot.db.execute('INSERT OR IGNORE INTO system_config(key,value) VALUES (?,?)',(key,value))
    boot.db.commit()
    boot_config={r['key']:r['value'] for r in boot.db.execute('SELECT key,value FROM system_config')}
    boot.close()
    app = FastAPI(title='AI Film Studio API', version='0.3')
    app.add_middleware(CORSMiddleware, allow_origins=['http://localhost:3000', 'http://127.0.0.1:3000',
                                                       'http://localhost:3001', 'http://127.0.0.1:3001'],
                       allow_methods=['*'], allow_headers=['*'])
    request_log=logging.getLogger('film_studio.api')
    @app.middleware('http')
    async def request_observability(request, call_next):
        request_id=uuid.uuid4().hex[:12];started=time.monotonic()
        try:
            response=await call_next(request)
            response.headers['X-Request-ID']=request_id
            request_log.info(json.dumps({'request_id':request_id,'method':request.method,'path':request.url.path,
                                         'status':response.status_code,'duration_ms':round((time.monotonic()-started)*1000)},ensure_ascii=False))
            return response
        except Exception:
            request_log.error(json.dumps({'request_id':request_id,'method':request.method,'path':request.url.path,
                                          'error_category':'UNHANDLED','duration_ms':round((time.monotonic()-started)*1000)},ensure_ascii=False))
            raise
    worker = JobWorker(path, media_dir, test_mode=test_mode,
                       poll_seconds=int(boot_config['poll_seconds']),
                       max_transient=int(boot_config['max_transient']),
                       max_download=int(boot_config['max_download']))
    app.state.job_worker = worker
    if (start_worker if start_worker is not None else not test_mode):
        @app.on_event('startup')
        def start_job_worker(): worker.start()

        @app.on_event('shutdown')
        def stop_job_worker(): worker.stop()

    def provider_state():
        state=provider_status()
        c=Core(str(path),test_mode=test_mode)
        try:
            config={r['key']:r['value'] for r in c.db.execute('SELECT key,value FROM system_config')}
        finally:c.close()
        for key,field in (('llm_enabled','llm'),('image_enabled','image')):
            if config.get(key)=='false':state[field]='未配置'
        if config.get('h3_enabled')=='false':
            state['h3']='服务未启动';state['h3_message']='H3 视频服务已由本地管理台停用；仍可继续制作计划。'
        return state

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

    shot_fields = {'purpose': '镜头目的', 'description': '观众看到什么', 'action': '动作过程',
                   'performance': '表演', 'camera': '摄影', 'sound': '声音', 'duration': '时长'}

    def missing_shot_fields(payload):
        missing = [label for key, label in shot_fields.items() if key != 'duration' and
                   (not isinstance(payload.get(key), str) or not payload[key].strip())]
        try:
            if float(payload.get('duration', 0)) <= 0:
                missing.append('时长')
        except (TypeError, ValueError):
            missing.append('时长')
        return missing

    def shot_read(shot):
        missing = missing_shot_fields(shot['payload'])
        return {**shot, 'missing_director_fields': missing,
                'confirmation_status': 'needs_reconfirmation' if (shot['status'] == 'approved' or shot['payload'].get('director_approved')) and missing
                else shot['status']}

    @app.get('/api/health')
    def health():
        return {'ok': True, 'database': str(path), 'provider': provider_state()}

    @app.get('/api/providers')
    def providers():
        return provider_state()

    @app.get('/api/model-profiles')
    def profiles():
        return execute(lambda c: latest(c, 'model_profile'))

    proposal_tasks = {'scene_plan', 'script_rewrite', 'script_tone', 'story_check',
                      'shot_plan', 'shot_action', 'shot_performance', 'shot_check',
                      'clip_plan', 'clip_explain', 'brief_draft', 'brief_qa', 'review_observation'}
    advisory_tasks = {'story_check', 'shot_check', 'clip_explain', 'brief_qa'}

    def proposal_row(row):
        return {**dict(row), **{key: json.loads(row[key]) for key in ('context', 'change', 'provenance')}}

    def assemble_context(c, pid, body):
        project = c.get('project', pid)
        items = []
        def add(kind, item, authority='FORMAL', fields=None):
            value = item['payload'] if fields is None else {key: item['payload'].get(key) for key in fields}
            items.append({'kind': kind, 'id': item['id'], 'version': item['version'],
                          'authority': authority, 'content': value})
        task = body.task
        if task.startswith('script_') or task in {'scene_plan', 'story_check'}:
            add('project', project, fields=('script', 'idea', 'preferences'))
            if body.target_id:
                add('scene', belong(c, 'scene', body.target_id, pid))
        elif task.startswith('shot_'):
            target = belong(c, 'shot', body.target_id, pid) if body.target_id and task != 'shot_plan' else belong(c, 'scene', body.target_id, pid)
            add(target['kind'], target)
            scene_id = target['id'] if target['kind'] == 'scene' else target['payload']['scene_id']
            for fact in latest(c, 'story_fact'):
                if fact['payload'].get('scene_id') == scene_id:
                    add('story_fact', fact)
            for kind in ('character', 'character_look', 'location', 'prop'):
                for item in project_world(c, pid, kind)[:8]:
                    add(kind, item)
        elif task in {'clip_plan', 'clip_explain', 'brief_draft', 'brief_qa'}:
            target = belong(c, 'clip', body.target_id, pid) if task != 'clip_plan' else belong(c, 'scene', body.target_id, pid)
            add(target['kind'], target)
            scene_id = target['id'] if target['kind'] == 'scene' else target['payload']['scene_id']
            if target['kind'] == 'clip':
                try: add('brief', c.get('brief', 'brief:' + target['id']))
                except DomainError: pass
            for shot in sorted([s for s in latest(c, 'shot') if s['payload'].get('scene_id') == scene_id and s['status'] == 'approved'], key=lambda s:s['payload'].get('ordinal',0))[:12]:
                add('shot', shot)
            for dep in c.db.execute('SELECT upstream_clip_id FROM dependencies WHERE clip_id=?', (target['id'],)) if target['kind']=='clip' else []:
                try:
                    state = c.snapshot(dep['upstream_clip_id'])
                    items.append({'kind':'canonical_state','id':str(state['id']),'version':1,
                                  'upstream_clip_id':dep['upstream_clip_id'],
                                  'authority':'CANONICAL','content':state['payload']})
                except DomainError: pass
            for profile in latest(c, 'model_profile')[:1]:
                add('model_knowledge', profile, 'DOCUMENTED', ('family','hard_capabilities','reliability_knowledge'))
        elif task == 'review_observation':
            target = belong(c, 'clip', body.target_id, pid)
            add('clip', target, fields=('name', 'duration'))
            try: add('brief', c.get('brief', 'brief:' + target['id']), fields=('planned_state_out',))
            except DomainError: pass
            selected = c.selection(target['id'])
            if not selected: raise DomainError('请先采用一条 Take。')
            items.append({'kind':'selection','id':str(selected['id']),'version':1,
                          'authority':'HUMAN_SELECTION','content':{'take_id':selected['take_id']}})
            if not body.instruction.strip():
                raise DomainError('请先输入你对实际 Take 的观察。')
        else:
            raise DomainError('unsupported proposal task')
        return {'task': task, 'target_id': body.target_id, 'instruction': body.instruction[:2000],
                'selected_text': body.selected_text[:5000], 'items': items,
                'unknown_policy': '缺失事实标为未知；不得假装观察到未提供的媒体。'}

    def validate_proposal(task, change, context):
        if not isinstance(change, dict):
            raise DomainError('AI 提案格式无效。')
        if task == 'scene_plan':
            scenes = change.get('scenes')
            if not isinstance(scenes, list) or not 1 <= len(scenes) <= 5 or any(
                    not isinstance(x, dict) or not str(x.get('story','')).strip() for x in scenes):
                raise DomainError('场次提案需要 1–5 条有内容的场次。')
        elif task in {'script_rewrite','script_tone'}:
            if not context['selected_text'] or not str(change.get('replacement','')).strip():
                raise DomainError('改写提案需要选中文字和替换文本。')
        elif task == 'shot_plan':
            shots = change.get('shots')
            if not isinstance(shots, list) or not 1 <= len(shots) <= 8 or any(
                    not isinstance(x, dict) or any(not str(x.get(k,'')).strip() for k in ('purpose','description','action','performance','camera','sound'))
                    or not isinstance(x.get('duration'),(int,float)) or not 0 < x['duration'] <= 60 for x in shots):
                raise DomainError('镜头提案缺少完整导演信息。')
        elif task in {'shot_action','shot_performance'}:
            if not str(change.get('text','')).strip(): raise DomainError('镜头提案内容为空。')
        elif task == 'clip_plan':
            clips = change.get('clips')
            if not isinstance(clips,list) or not 1 <= len(clips) <= 4 or any(
                    not isinstance(x,dict) or not str(x.get('name','')).strip() or
                    x.get('handoff') not in Core.HANDOFFS or not isinstance(x.get('duration'),(int,float)) or
                    not 0 < x['duration'] <= 60 for x in clips):
                raise DomainError('Clip 提案需要名称、策略和有效时长。')
        elif task == 'brief_draft':
            allowed = {'purpose','action_process','performance','camera','sound','planned_state_out'}
            if not change or set(change)-allowed or not str(change.get('purpose','')).strip():
                raise DomainError('制作方案提案字段无效。')
        elif task == 'review_observation':
            if not str(change.get('summary','')).strip(): raise DomainError('观察摘要为空。')
        elif task in advisory_tasks:
            if not str(change.get('advice','')).strip(): raise DomainError('建议内容为空。')

    @app.get('/api/projects/{pid}/proposals')
    def proposals(pid: str, task: str | None = None):
        def op(c):
            c.get('project', pid)
            return [proposal_row(r) for r in c.db.execute('SELECT * FROM ai_proposals WHERE project_id=? AND (? IS NULL OR task=?) ORDER BY rowid DESC', (pid,task,task))]
        return execute(op)

    @app.post('/api/projects/{pid}/proposals')
    def create_proposal(pid: str, body: ProposalInput):
        if body.task not in proposal_tasks: raise HTTPException(400, 'unsupported proposal task')
        if not test_mode and provider_state()['llm']!='可用':
            raise HTTPException(503,{'code':'PROVIDER_UNAVAILABLE','message':'文本 AI 服务未配置或已停用。'})
        def op(c):
            context = assemble_context(c,pid,body)
            system = ('你是影视创作辅助。只根据给定的带来源上下文提出建议，不把未知信息当事实。'
                      '只输出 JSON 对象，格式为 {"change":{...},"explanation":"简短中文说明"}。'
                      '严格使用以下字段名，不要添加 markdown 或另一层 proposal。'
                      'scene_plan 示例：{"change":{"scenes":[{"place":"地点","story":"这一场发生什么"}]},"explanation":"理由"}。'
                      'shot_plan 示例：{"change":{"shots":[{"purpose":"目的","description":"画面","action":"动作过程","performance":"可见表演","camera":"摄影","sound":"声音","duration":5}]},"explanation":"理由"}。'
                      'clip_plan 时 change.clips 为包含 name、duration、handoff 的片段数组；script_rewrite/script_tone 时 change.replacement 为替换文字；'
                      'shot_action/shot_performance 时 change.text 为文字；brief_draft 时 change 只能含目的、动作、表演、摄影、声音、计划结束状态字段；'
                      'review_observation 时 change.summary 为用户观察的客观整理；检查或解释类任务用 change.advice。'
                      '禁止输出 Raw Prompt、虚构媒体分析或自动批准声明。')
            try:
                adapter = DarlLLMAdapter(key=os.getenv('LLM_API_KEY') or os.getenv('DARL_API_KEY'))
                result = adapter.propose(system,context)
            except AIProviderError as exc:
                raise HTTPException(503, {'code':exc.category,'message':str(exc)}) from exc
            change, explanation = result.get('change'), result.get('explanation')
            validate_proposal(body.task,change,context)
            if not isinstance(explanation,str) or not explanation.strip(): raise DomainError('提案缺少解释。')
            proposal_id=uid('proposal')
            c.db.execute('INSERT INTO ai_proposals(id,project_id,task,target_id,context,change,explanation,provenance,provider,model,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                         (proposal_id,pid,body.task,body.target_id,json.dumps(context,ensure_ascii=False),
                          json.dumps(change,ensure_ascii=False),explanation.strip()[:2000],
                          json.dumps({'authority':'PROPOSAL','source':'contextual-ai','test_only':test_mode},ensure_ascii=False),adapter.provider,adapter.model,'pending'))
            c.db.commit()
            return proposal_row(c.db.execute('SELECT * FROM ai_proposals WHERE id=?',(proposal_id,)).fetchone())
        return execute(op)

    def proposal_source_is_current(c, context):
        for item in context['items']:
            if item['kind'] == 'selection':
                current = c.selection(context['target_id'])
                if not current or str(current['id']) != item['id']: return False
            elif item['kind'] == 'canonical_state':
                if not c.db.execute('SELECT 1 FROM state_snapshots WHERE id=?',(item['id'],)).fetchone(): return False
                upstream=item.get('upstream_clip_id')
                if upstream and str(c.snapshot(upstream)['id']) != item['id']: return False
            else:
                kind = 'model_profile' if item['kind']=='model_knowledge' else item['kind']
                if c.get(kind,item['id'])['version'] != item['version']: return False
        return True

    @app.post('/api/projects/{pid}/proposals/{proposal_id}/reject')
    def reject_proposal(pid: str, proposal_id: str):
        def op(c):
            row=c.db.execute('SELECT * FROM ai_proposals WHERE id=? AND project_id=?',(proposal_id,pid)).fetchone()
            if not row: raise DomainError('proposal missing')
            if row['status']!='pending': return proposal_row(row)
            c.db.execute("UPDATE ai_proposals SET status='rejected',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND status='pending'",(proposal_id,))
            c.db.commit()
            return proposal_row(c.db.execute('SELECT * FROM ai_proposals WHERE id=?',(proposal_id,)).fetchone())
        return execute(op)

    @app.post('/api/projects/{pid}/proposals/{proposal_id}/accept')
    def accept_proposal(pid: str, proposal_id: str):
        def op(c):
            row=c.db.execute('SELECT * FROM ai_proposals WHERE id=? AND project_id=?',(proposal_id,pid)).fetchone()
            if not row: raise DomainError('proposal missing')
            if row['status']=='accepted': return proposal_row(row)
            if row['status']!='pending': raise DomainError('proposal is no longer pending')
            proposal=proposal_row(row); context=proposal['context']; change=proposal['change']; task=row['task']
            if not proposal_source_is_current(c,context):
                c.db.execute("UPDATE ai_proposals SET status='superseded',resolved_at=CURRENT_TIMESTAMP WHERE id=?",(proposal_id,))
                c.db.commit()
                raise HTTPException(409,'提案依据的正式内容已经变化，请重新生成提案。')
            validate_proposal(task,change,context)
            c.db.execute("UPDATE ai_proposals SET status='applying' WHERE id=? AND status='pending'",(proposal_id,))
            c.db.commit()
            source='human-accepted-proposal:' + proposal_id
            target=row['target_id']
            if task=='scene_plan':
                episodes=[e for e in latest(c,'episode') if e['payload'].get('project_id')==pid]
                if not episodes: raise DomainError('episode missing')
                existing=scenes_for(c,pid)
                for i,scene in enumerate(change['scenes']):
                    c.put('scene',uid('scene'),{'episode_id':episodes[0]['id'],'ordinal':len(existing)+i,
                         'place':str(scene.get('place',''))[:200],'story':str(scene['story'])[:10000],
                         'ready_for_directing':False},source,'draft')
            elif task in {'script_rewrite','script_tone'}:
                project=c.get('project',pid); script=project['payload'].get('script',''); selected=context['selected_text']
                if script.count(selected)!=1: raise DomainError('选中文字已变化或不唯一；请重新生成提案。')
                c.put('project',pid,{**project['payload'],'script':script.replace(selected,str(change['replacement']),1)},source,'approved')
                mark_impact(c,pid,'project',pid,None,'剧本文本已接受 AI 提案；相关制作计划需要重新检查。')
            elif task=='shot_plan':
                scene=belong(c,'scene',target,pid)
                existing=[s for s in latest(c,'shot') if s['payload'].get('scene_id')==scene['id']]
                for i,shot in enumerate(change['shots']):
                    c.put('shot',uid('shot'),{'scene_id':scene['id'],'ordinal':len(existing)+i,
                          **{k:shot[k] for k in ('purpose','description','action','performance','camera','sound','duration')},
                          'director_approved':False},source,'draft')
            elif task in {'shot_action','shot_performance'}:
                shot=belong(c,'shot',target,pid); field='action' if task=='shot_action' else 'performance'
                c.put('shot',target,{**shot['payload'],field:str(change['text'])[:5000],
                                    'director_approved':False},source,'draft')
                mark_impact(c,pid,'shot',target,shot['payload']['scene_id'],'镜头接受了 AI 提案；请人工重新确认，并检查相关制作方案。')
            elif task=='clip_plan':
                scene=belong(c,'scene',target,pid)
                for clip in change['clips']:
                    c.put('clip',uid('clip'),{'scene_id':scene['id'],'name':str(clip['name'])[:150],
                           'duration':clip['duration'],'handoff':clip['handoff']},source,'draft')
            elif task=='brief_draft':
                clip=belong(c,'clip',target,pid)
                try: old=c.get('brief','brief:'+target)['payload']
                except DomainError: old={}
                c.save_brief(target,{**old,**change,'clip_id':target,'scene_id':clip['payload']['scene_id'],
                    'duration':clip['payload']['duration'],'handoff':clip['payload']['handoff'],
                    'provenance':{**old.get('provenance',{}),'accepted_proposal':proposal_id}},source,'draft')
            elif task=='review_observation':
                selected=c.selection(target)
                c.observe(uid('observed'),selected['take_id'],{'summary':str(change['summary'])[:2000]},source)
            c.db.execute("UPDATE ai_proposals SET status='accepted',resolved_at=CURRENT_TIMESTAMP WHERE id=? AND status='applying'",(proposal_id,))
            c.db.commit()
            return proposal_row(c.db.execute('SELECT * FROM ai_proposals WHERE id=?',(proposal_id,)).fetchone())
        return execute(op)

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
            checksum=hashlib.sha256(content).hexdigest();media_id=uid('media')
            c.register_media(media_id,str(dest),checksum,len(content),file.content_type,
                             metadata={'kind':'image_asset','source':'uploaded','project_id':pid,
                                       'owner_id':owner_id,'test_only':test_mode})
            item = c.put('asset_version', asset_id, {'project_id': pid, 'owner_id': owner_id,
                'purpose': purpose, 'uri': str(dest), 'media_type': 'image',
                'sha256': checksum, 'mime': file.content_type,'media_id':media_id,
                'provenance':{'source':'uploaded','authority':'CREATOR_UPLOAD'}}, 'creator-upload')
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

    @app.get('/api/projects/{pid}/assets/candidates')
    def image_candidates(pid: str, owner_id: str | None = None):
        def op(c):
            c.get('project', pid)
            rows=c.db.execute('SELECT * FROM asset_candidates WHERE project_id=? AND (? IS NULL OR owner_id=?) ORDER BY created_at DESC',
                              (pid,owner_id,owner_id)).fetchall()
            return [{**dict(r),'provenance':json.loads(r['provenance'])} for r in rows]
        return execute(op)

    @app.post('/api/projects/{pid}/assets/candidates')
    def generate_image_candidate(pid: str, body: ImageCandidateInput):
        prompt=body.prompt.strip()
        if not 8 <= len(prompt) <= 2000 or not body.purpose.strip():
            raise HTTPException(400,'图片描述需为 8–2000 字，并说明用途。')
        if not test_mode and provider_state()['image']!='可用':
            raise HTTPException(503,{'code':'PROVIDER_UNAVAILABLE','message':'图片服务未配置或已停用。'})
        def op(c):
            owner=next((x for kind in ('character','character_look','location','prop')
                        for x in project_world(c,pid,kind) if x['id']==body.owner_id),None)
            if not owner: raise DomainError('asset owner missing')
            try:
                adapter=DarlImageAdapter(key=os.getenv('IMAGE_API_KEY') or os.getenv('DARL_API_KEY'))
                image,mime,provider_meta=adapter.generate(prompt)
            except AIProviderError as exc:
                raise HTTPException(503,{'code':exc.category,'message':str(exc)}) from exc
            media_dir.mkdir(parents=True,exist_ok=True)
            candidate_id=uid('candidate'); media_id=uid('media')
            target=media_dir/(candidate_id+'.png'); partial=target.with_suffix('.partial')
            partial.write_bytes(image); partial.replace(target)
            checksum=hashlib.sha256(image).hexdigest()
            c.register_media(media_id,str(target),checksum,len(image),mime,metadata={
                'kind':'image_candidate','source':'generated','project_id':pid,'owner_id':body.owner_id,
                'provider':'darl','model':adapter.model,'test_only':test_mode})
            provenance={'source':'generated','owner_kind':owner['kind'],'owner_version':owner['version'],
                        'prompt':prompt,'provider_response':provider_meta,'authority':'CANDIDATE',
                        'test_only':test_mode}
            c.db.execute('INSERT INTO asset_candidates(id,project_id,owner_id,purpose,prompt,media_id,provider,model,provenance) VALUES (?,?,?,?,?,?,?,?,?)',
                         (candidate_id,pid,body.owner_id,body.purpose.strip()[:200],prompt,media_id,
                          adapter.provider,adapter.model,json.dumps(provenance,ensure_ascii=False)))
            c.db.commit()
            return {'id':candidate_id,'status':'pending','owner_id':body.owner_id,'media_id':media_id,
                    'purpose':body.purpose,'provenance':provenance}
        return execute(op)

    @app.get('/api/projects/{pid}/assets/candidates/{candidate_id}/image')
    def candidate_image(pid: str,candidate_id: str):
        def op(c):
            row=c.db.execute('SELECT media_id FROM asset_candidates WHERE id=? AND project_id=?',(candidate_id,pid)).fetchone()
            if not row: raise DomainError('candidate missing')
            media=c.media(row['media_id']); target=Path(media['local_path']).resolve()
            if not target.is_file() or not target.is_relative_to(media_dir.resolve()):
                raise DomainError('candidate media unavailable')
            return FileResponse(target,media_type=media['mime'])
        return execute(op)

    @app.post('/api/projects/{pid}/assets/candidates/{candidate_id}/reject')
    def reject_image_candidate(pid: str,candidate_id: str):
        def op(c):
            row=c.db.execute('SELECT * FROM asset_candidates WHERE id=? AND project_id=?',(candidate_id,pid)).fetchone()
            if not row: raise DomainError('candidate missing')
            if row['status']=='pending':
                c.db.execute("UPDATE asset_candidates SET status='rejected',resolved_at=CURRENT_TIMESTAMP WHERE id=?",(candidate_id,));c.db.commit()
            return {'id':candidate_id,'status':'rejected'}
        return execute(op)

    @app.post('/api/projects/{pid}/assets/candidates/{candidate_id}/adopt')
    def adopt_image_candidate(pid: str,candidate_id: str):
        def op(c):
            row=c.db.execute('SELECT * FROM asset_candidates WHERE id=? AND project_id=?',(candidate_id,pid)).fetchone()
            if not row: raise DomainError('candidate missing')
            if row['status']=='adopted':
                return {'id':candidate_id,'status':'adopted'}
            if row['status']!='pending': raise DomainError('candidate is no longer pending')
            media=c.media(row['media_id']); target=Path(media['local_path']).resolve()
            if not target.is_file() or not target.is_relative_to(media_dir.resolve()):
                raise DomainError('candidate image missing')
            asset_id='asset-'+hashlib.sha256((row['owner_id']+'\0'+row['purpose']).encode()).hexdigest()[:16]
            c.db.execute("UPDATE asset_candidates SET status='applying' WHERE id=? AND status='pending'",(candidate_id,));c.db.commit()
            item=c.put('asset_version',asset_id,{'project_id':pid,'owner_id':row['owner_id'],
                'purpose':row['purpose'],'uri':str(target),'media_type':'image',
                'sha256':media['sha256'],'mime':media['mime'],'media_id':row['media_id'],
                'provenance':{'source':'generated','candidate_id':candidate_id,'provider':row['provider'],
                              'model':row['model'],'authority':'HUMAN_ADOPTED'}},'human-adopted-generated')
            c.db.execute('INSERT INTO asset_current(project_id,owner_id,asset_id,version) VALUES (?,?,?,?) '
                         'ON CONFLICT(project_id,owner_id) DO UPDATE SET asset_id=excluded.asset_id,version=excluded.version,updated_at=CURRENT_TIMESTAMP',
                         (pid,row['owner_id'],asset_id,item['version']))
            c.db.execute("UPDATE asset_candidates SET status='adopted',resolved_at=CURRENT_TIMESTAMP WHERE id=?",(candidate_id,))
            c.db.commit()
            mark_impact(c,pid,'asset_current',asset_id,None,'采用了新的视觉素材版本；请检查后续片段的参考绑定。')
            return {'id':candidate_id,'status':'adopted','asset':item}
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
            return [shot_read(s) for s in sorted([s for s in latest(c, 'shot') if (not scene_id or s['payload'].get('scene_id') == scene_id)
                           and any(sc['id'] == s['payload'].get('scene_id') for sc in scenes_for(c, pid))],
                          key=lambda s: (s['payload'].get('ordinal', 0), c.get('shot', s['id'], 1)['created_at']))]
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
            if body.status == 'approved':
                missing = missing_shot_fields({**shot['payload'], **body.payload})
                if missing:
                    raise DomainError('确认镜头前还需要补充：' + '、'.join(missing))
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
                try:
                    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(body.at_second), '-i', str(source),
                                    '-t', str(body.duration), '-c:v', 'libx264', '-crf', '18', '-an', str(dest)],
                                   check=True, timeout=120, capture_output=True)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise DomainError('Stable Tail 提取失败；请检查媒体文件与提取时间。') from exc
                if not dest.is_file() or not dest.stat().st_size:
                    raise DomainError('Stable Tail extraction failed')
                tail_bytes=dest.read_bytes();checksum=hashlib.sha256(tail_bytes).hexdigest();media_id=uid('media')
                c.register_media(media_id,str(dest),checksum,len(tail_bytes),'video/mp4',duration=body.duration,
                                 metadata={'kind':'control_media','role':'stable_tail','project_id':pid,
                                           'derived_from_take':take['id'],'selection_id':selection['id'],
                                           'extraction_range':[body.at_second,body.at_second+body.duration],
                                           'source':'selected_take','test_only':False})
                control_id = uid('tail')
                c.create_stable_tail(control_id, upstream, take['id'], str(dest),
                                     {'stable': True, 'human_assessment': body.assessment})
                payload = c.get('control_media', control_id)['payload']
                c.put('control_media', control_id, {**payload, 'duration': body.duration,
                      'source_selection_id': selection['id'],'extraction_range':[body.at_second,body.at_second+body.duration],
                      'checksum':checksum,'media_id':media_id,'derived_from_take':take['id']}, 'human-reviewed-tail')
                brief = c.rebase_brief_state(cid, upstream)
                return {'control_media_id': control_id, 'brief': brief}
            if body.kind == 'visual_anchor':
                if dep['kind'] == 'VIDEO_CONTINUATION':
                    raise DomainError('video continuation requires a Stable Tail')
                dest = media_dir / (uid('visual-anchor') + '.png')
                try:
                    subprocess.run(['ffmpeg', '-y', '-loglevel', 'error', '-ss', str(body.at_second), '-i', str(source),
                                    '-frames:v', '1', str(dest)], check=True, timeout=120, capture_output=True)
                except (OSError, subprocess.SubprocessError) as exc:
                    raise DomainError('Stable Frame 提取失败；请检查媒体文件与提取时间。') from exc
                if not dest.is_file() or not dest.stat().st_size:
                    raise DomainError('visual anchor extraction failed')
                frame_bytes=dest.read_bytes();checksum=hashlib.sha256(frame_bytes).hexdigest();media_id=uid('media')
                c.register_media(media_id,str(dest),checksum,len(frame_bytes),'image/png',
                                 metadata={'kind':'control_media','role':'stable_frame','project_id':pid,
                                           'derived_from_take':take['id'],'selection_id':selection['id'],
                                           'extraction_range':[body.at_second,body.at_second],
                                           'source':'selected_take','test_only':False})
                control_id, binding_id = uid('anchor'), uid('binding')
                c.put('control_media', control_id, {'role': 'visual_anchor', 'source_take_id': take['id'],
                    'source_selection_id': selection['id'], 'uri': str(dest),
                    'assessment': body.assessment,'checksum':checksum,'media_id':media_id,
                    'extraction_kind':'stable_frame','extraction_range':[body.at_second,body.at_second],
                    'derived_from_take':take['id']}, 'human-reviewed-frame')
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
            for row in c.db.execute('SELECT id FROM jobs ORDER BY rowid DESC'):
                job = c.job(row['id'])
                if job['snapshot']['task']['clip_id'] in ids and (not clip_id or job['snapshot']['task']['clip_id'] == clip_id):
                    runtime=c.db.execute('SELECT next_poll_at,poll_count,transient_count,last_error_category,completed_at FROM job_runtime WHERE job_id=?',(job['id'],)).fetchone()
                    result.append({**job,'runtime':dict(runtime) if runtime else None})
            return result
        return execute(op)

    @app.get('/api/projects/{pid}/jobs/{jid}')
    def job_detail(pid: str, jid: str):
        def op(c):
            job = c.job(jid)
            belong(c, 'clip', job['snapshot']['task']['clip_id'], pid)
            runtime=c.db.execute('SELECT * FROM job_runtime WHERE job_id=?',(jid,)).fetchone()
            return {**job,'runtime':dict(runtime) if runtime else None, 'events': [{**dict(r), 'metadata': json.loads(r['metadata'])}
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
    def generate(pid: str, cid: str, retry_of: str | None = None,
                 creative_reason: str | None = None, request_id: str | None = None,
                 provider: str | None = None):
        if provider is not None and provider != 'darl':
            raise HTTPException(400, 'only darl is supported for H3 generation')
        if retry_of and creative_reason is not None:
            raise HTTPException(400, 'technical retry and creative regenerate are separate actions')
        if request_id and (len(request_id)>100 or not request_id.replace('-','').isalnum()):
            raise HTTPException(400, 'invalid request id')
        def op(c):
            belong(c, 'clip', cid, pid)
            selected_provider = provider or 'darl'
            original = None
            if retry_of:
                original = c.job(retry_of)
                if original['snapshot']['task']['clip_id'] != cid:
                    raise DomainError('技术重试必须指向此 Clip 的失败 Job。')
                selected_provider = generation_provider(original)
                if provider is not None and provider != selected_provider:
                    raise DomainError('技术重试必须沿用原 Provider；切换通道请明确进行创作重生成。')
            state = provider_state()
            execution_model = darl_execution_model(original['snapshot']['task']) if original else state['execution_model']
            if state['h3'] != '可用':
                raise HTTPException(503, {'code': 'PROVIDER_UNAVAILABLE',
                                          'message': state['h3_message']})
            if original and execution_model == LOCAL_H3_MODEL and state['self_hosted_h3'] != '可用':
                raise HTTPException(503, {'code': 'EXECUTION_MODEL_UNAVAILABLE',
                                          'message': '原任务使用的自建 H3 未开启；技术重试不能切换 execution model。'})
            handoff = original['snapshot']['task']['task_mode'] if original else c.get('clip',cid)['payload']['handoff']
            if request_id:
                existing=c.db.execute('SELECT * FROM generation_requests WHERE request_id=?',(request_id,)).fetchone()
                if existing:
                    if existing['project_id']!=pid or existing['clip_id']!=cid: raise DomainError('request id belongs to another Clip')
                    if existing['job_id']: return {'job':c.job(existing['job_id']),'idempotent':True,'expected_minutes':3}
                    raise HTTPException(409,'生成请求正在提交，请勿重复点击。')
            previous = [c.job(r['id']) for r in c.db.execute(
                'SELECT id FROM jobs WHERE task_id IN (SELECT id FROM compiled_tasks WHERE clip_id=?) ORDER BY rowid DESC',(cid,))]
            if any(j['status'] in {'queued','running'} for j in previous):
                raise DomainError('此 Clip 已有生成中的任务。')
            if previous and not retry_of and not creative_reason and previous[0]['status']=='failed':
                raise DomainError('上次任务失败，请明确选择技术重试或修改方案后创作重生成。')
            if previous and not retry_of and not creative_reason and previous[0]['status']=='succeeded':
                raise DomainError('已有成功 Take；再次生成请明确填写创作重生成原因。')
            if retry_of:
                if not previous or previous[0]['id']!=retry_of or previous[0]['status']!='failed':
                    raise DomainError('技术重试必须指向此 Clip 最新的失败 Job。')
                chain=0;parent=previous[0]
                while parent['snapshot'].get('retry_of'):
                    chain+=1;parent=c.job(parent['snapshot']['retry_of'])
                if chain>=2: raise DomainError('技术重试次数已达上限。')
                metadata=previous[0]['metadata']
                category=metadata.get('provider_error',{}).get('code') or metadata.get('error_category','')
                if category not in {'fail_to_fetch_task','NETWORK_ERROR','HTTP_408','HTTP_429','HTTP_500','HTTP_502','HTTP_503','HTTP_504','MEDIA_DOWNLOAD_FAILED','RATE_LIMIT'}:
                    raise DomainError('此失败不属于可技术重试的临时错误；请检查制作方案。')
            if creative_reason is not None and not creative_reason.strip():
                raise DomainError('请说明创作重生成的原因。')
            job_id=uid('job')
            try:
                c.db.execute('INSERT INTO active_generation(clip_id,job_id) VALUES (?,?)',(cid,job_id))
                if request_id:
                    c.db.execute('INSERT INTO generation_requests(request_id,project_id,clip_id) VALUES (?,?,?)',
                                 (request_id,pid,cid))
                c.db.commit()
            except sqlite3.IntegrityError as exc:
                c.db.rollback()
                raise HTTPException(409,'此 Clip 已有提交中的任务；请刷新状态。') from exc
            created=False
            try:
                if original:
                    task_id=original['task_id']
                    task=c.task(task_id)
                else:
                    profile_id=H3_PROFILE_IDS[execution_model]
                    profiles=[profile for profile in latest(c,'model_profile') if profile['id']==profile_id]
                    if not profiles:
                        profile=darl_h3_profile(False, execution_model=execution_model)
                        c.put('model_profile',profile_id,profile,'documented-profile','documented')
                    else:
                        profile=profiles[0]['payload']
                        if profile['model_id'] != execution_model:
                            raise DomainError('Darl execution model profile mismatch')
                        if profile.get('provider') != 'darl' or profile.get('execution_model') != execution_model:
                            c.put('model_profile',profile_id,{**profile,'provider':'darl','execution_model':execution_model},
                                  'darl-routing','documented')
                    task_id=uid('task');continuation=None
                    if handoff=='VIDEO_CONTINUATION':
                        dep=c.db.execute("SELECT upstream_clip_id FROM dependencies WHERE clip_id=? AND kind='VIDEO_CONTINUATION'",(cid,)).fetchone()
                        if not dep: raise DomainError('continuation dependency missing')
                        selected=c.selection(dep['upstream_clip_id'])
                        control=c.db.execute("SELECT id FROM objects WHERE kind='control_media' AND json_extract(payload,'$.role')='stable_tail' AND json_extract(payload,'$.source_take_id')=? ORDER BY created_at DESC LIMIT 1",
                                             (selected['take_id'] if selected else '',)).fetchone()
                        if not control: raise DomainError('selected upstream Stable Tail missing')
                        continuation=c.continuation_source(dep['upstream_clip_id'],control['id'])
                    task=c.compile_h3(task_id,'brief:'+cid,profile_id,
                                      parameters={'resolution':'480P','num_inference_steps':20,'turbo':False,'watermark':False},
                                      continuation=continuation)
                preflight=c.preflight(task_id,retry_of=retry_of)
                if not preflight.ready: raise DomainError('model preflight not ready: '+json.dumps(preflight.reasons))
                adapter=DarlH3Adapter()
                adapter.build_request(task)
                if not c.preflight(task_id,retry_of=retry_of).ready:
                    raise DomainError('compiled task became stale before submission')
                attempt='technical_retry' if retry_of else 'creative_regenerate' if creative_reason else 'initial'
                c.create_job(job_id,task_id,retry_of=retry_of,
                             cost_estimate={'candidate_limit':1,'resolution':task['parameters'].get('resolution'),'attempt_kind':attempt,
                                            'creative_reason':(creative_reason or '')[:500], 'provider':selected_provider,
                                            'execution_model':execution_model})
                created=True
                if request_id:
                    c.db.execute('UPDATE generation_requests SET job_id=? WHERE request_id=?',(job_id,request_id));c.db.commit()
                try:
                    submit_started=time.monotonic()
                    response=adapter.submit(task,job_id)
                except ProviderError as exc:
                    c.job_event(job_id,'failed',{'provider':selected_provider,'execution_model':execution_model,
                                               'provider_error':exc.as_dict(),'error_category':exc.code})
                    c.db.execute('DELETE FROM active_generation WHERE clip_id=? AND job_id=?',(cid,job_id));c.db.commit()
                    self_hosted_offline=execution_model==LOCAL_H3_MODEL and exc.code=='fail_to_fetch_task' and exc.http_status==404
                    raise HTTPException(503,{'code':'PROVIDER_UNAVAILABLE' if self_hosted_offline else exc.code,
                                             'message':'自建 H3 视频服务器当前未启动。' if self_hosted_offline else '视频服务提交失败。',
                                             'job_id':job_id}) from exc
                c.job_event(job_id,'running',{'provider':selected_provider,'provider_task_id':response['id'],
                                              'provider_status':response['status'],'execution_model':execution_model})
                next_poll=(utcnow()+__import__('datetime').timedelta(seconds=180)).isoformat()
                c.db.execute('INSERT INTO job_runtime(job_id,provider,provider_task_id,next_poll_at,submitted_at,submit_latency_ms) VALUES (?,?,?,?,?,?)',
                             (job_id,selected_provider,response['id'],next_poll,utcnow().isoformat(),round((time.monotonic()-submit_started)*1000)))
                c.db.commit()
                return {'job':c.job(job_id),'expected_minutes':3}
            except Exception:
                if created and c.job(job_id)['status']=='queued':
                    c.job_event(job_id,'failed',{'error_category':'SUBMISSION_UNKNOWN',
                                                 'message':'Submit did not complete; no automatic resubmit'})
                c.db.execute('DELETE FROM active_generation WHERE clip_id=? AND job_id=?',(cid,job_id))
                if not created and request_id:
                    c.db.execute('DELETE FROM generation_requests WHERE request_id=? AND job_id IS NULL',(request_id,))
                c.db.commit()
                raise
        return execute(op)

    @app.post('/api/projects/{pid}/jobs/{jid}/sync')
    def sync_job(pid: str, jid: str):
        def schedule(c):
            job=c.job(jid);belong(c,'clip',job['snapshot']['task']['clip_id'],pid)
            if job['status']=='running':
                c.db.execute('UPDATE job_runtime SET next_poll_at=? WHERE job_id=?',(utcnow().isoformat(),jid))
                c.db.commit()
            return job
        execute(schedule)
        worker.tick()
        return execute(lambda c:{'job':c.job(jid),'take':dict(c.db.execute('SELECT * FROM takes WHERE job_id=?',(jid,)).fetchone()) if c.db.execute('SELECT 1 FROM takes WHERE job_id=?',(jid,)).fetchone() else None})

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

    @app.get('/api/projects/{pid}/timeline/export-readiness')
    def timeline_export_readiness(pid: str):
        def op(c):
            c.get('project', pid)
            rows = c.db.execute('SELECT * FROM timeline_items WHERE project_id=? ORDER BY position', (pid,)).fetchall()
            reasons = []
            if not rows:
                reasons.append('时间线为空，请先加入已采用的真实片段。')
            for index, row in enumerate(rows, 1):
                try:
                    take = c.take(row['take_id'])
                    selection = c.selection(row['clip_id'])
                    if not selection or selection['take_id'] != row['take_id']:
                        reasons.append(f'第 {index} 段采用的 Take 已变化，请更新片段。')
                    if take['test_only']:
                        reasons.append(f'第 {index} 段是 TEST ONLY，不能导出正式预览。')
                    if not take['media_id']:
                        reasons.append(f'第 {index} 段缺少受管理的视频媒体。')
                    else:
                        try:
                            media = c.media(take['media_id'])
                            if not Path(media['local_path']).is_file():
                                reasons.append(f'第 {index} 段的视频文件已缺失。')
                        except DomainError:
                            reasons.append(f'第 {index} 段的视频媒体记录已缺失。')
                except DomainError:
                    reasons.append(f'第 {index} 段的 Take 已缺失。')
            return {'ready': not reasons, 'reasons': reasons}
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

    @app.get('/api/admin/overview')
    def admin_overview():
        def op(c):
            jobs=[c.job(r['id']) for r in c.db.execute('SELECT id FROM jobs ORDER BY rowid DESC LIMIT 30')]
            media=list(c.db.execute('SELECT id,size_bytes,local_path FROM media_records'))
            return {'test_mode':test_mode,'providers':provider_state(),
                    'jobs':{'total':c.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0],
                            'running':sum(j['status']=='running' for j in jobs),
                            'failed':sum(j['status']=='failed' for j in jobs),
                            'recent':[{'id':j['id'],'status':j['status'],
                                       'clip_id':j['snapshot']['task']['clip_id'],
                                       'created_at':j['created_at']} for j in jobs[:8]]},
                    'media':{'count':len(media),'bytes':sum(m['size_bytes'] for m in media),
                             'missing':sum(not Path(m['local_path']).is_file() for m in media)},
                    'profiles':[{'id':p['id'],'version':p['version'],'status':p['status']}
                                for p in latest(c,'model_profile')],
                    'recent_errors':[{'job_id':r['job_id'],'category':r['last_error_category']}
                                     for r in c.db.execute('SELECT job_id,last_error_category FROM job_runtime WHERE last_error_category IS NOT NULL ORDER BY rowid DESC LIMIT 8')]}
        return execute(op)

    @app.get('/api/admin/providers')
    def admin_providers():
        from urllib.parse import urlsplit,urlunsplit
        raw=os.getenv('DARL_BASE_URL') or 'https://api.darl.cn'
        parsed=urlsplit(raw)
        safe_url=urlunsplit((parsed.scheme,parsed.hostname or '',parsed.path,'',''))
        statuses=provider_state()
        def op(c):
            last=c.db.execute("SELECT last_error_category,last_polled_at FROM job_runtime WHERE provider='darl' AND last_error_category IS NOT NULL ORDER BY rowid DESC LIMIT 1").fetchone()
            checked=utcnow().isoformat()
            return [{'name':'Darl LLM','model':'deepseek-v4.1-flash','status':statuses['llm'],
                     'configured':bool(os.getenv('LLM_API_KEY') or os.getenv('DARL_API_KEY')),
                     'base_url':safe_url,'last_checked':checked,'last_error':None},
                    {'name':'Darl Image','model':'gpt-image-2','status':statuses['image'],
                     'configured':bool(os.getenv('IMAGE_API_KEY') or os.getenv('DARL_API_KEY')),
                     'base_url':safe_url,'last_checked':checked,'last_error':None},
                    {'name':'Darl H3','model':statuses['execution_model'],'status':statuses['h3'],
                     'execution_models':[{'id':model,'name':name,'status':statuses['self_hosted_h3' if model==LOCAL_H3_MODEL else 'cloud_h3']}
                                         for model,name in H3_EXECUTION_MODELS.items()],
                     'configured':bool(os.getenv('DARL_API_KEY')),'base_url':safe_url,
                     'last_checked':last['last_polled_at'] if last else checked,
                     'last_error':last['last_error_category'] if last else None}]
        return execute(op)

    @app.get('/api/admin/jobs')
    def admin_jobs(status: str | None = None):
        if status and status not in {'queued','running','succeeded','failed','cancelled'}:
            raise HTTPException(400,'invalid job status')
        def op(c):
            result=[]
            for row in c.db.execute('SELECT id FROM jobs ORDER BY rowid DESC LIMIT 100'):
                job=c.job(row['id'])
                if status and job['status']!=status:continue
                task=job['snapshot']['task'];runtime=c.db.execute('SELECT * FROM job_runtime WHERE job_id=?',(job['id'],)).fetchone()
                result.append({'id':job['id'],'status':job['status'],'test_only':test_mode,
                               'provider':runtime['provider'] if runtime else job['metadata'].get('provider','darl'),
                               'execution_model':task.get('execution_model',task.get('target_model')),
                               'legacy_provider':any(value and value!='darl' for value in (
                                   job['metadata'].get('provider'),task.get('provider'),
                                   (job['snapshot'].get('cost_estimate') or {}).get('provider'),runtime['provider'] if runtime else None))
                                   or task.get('model_profile',{}).get('id') not in H3_PROFILE_IDS.values(),
                               'project_id':JobWorker._project_for_clip(c,task['clip_id']),
                               'clip_id':task['clip_id'],'task_id':task['id'],
                               'provider_task_id':job['metadata'].get('provider_task_id') or (runtime['provider_task_id'] if runtime else None),
                               'retry_of':job['snapshot'].get('retry_of'),'attempt':(job['snapshot'].get('cost_estimate') or {}).get('attempt_kind','legacy'),
                               'created_at':job['created_at'],'completed_at':runtime['completed_at'] if runtime else None,
                               'error_category':job['metadata'].get('error_category') or job['metadata'].get('provider_error',{}).get('code'),
                               'media_id':job['metadata'].get('media_id'),'poll_count':runtime['poll_count'] if runtime else 0})
            return result
        return execute(op)

    @app.post('/api/admin/jobs/{jid}/technical-retry')
    def admin_retry(jid: str, body: AdminRetryInput):
        def find(c):
            job=c.job(jid)
            if job['status']!='failed':raise DomainError('only failed jobs may be retried')
            cid=job['snapshot']['task']['clip_id']
            return JobWorker._project_for_clip(c,cid),cid,generation_provider(job)
        pid,cid,provider=execute(find)
        return generate(pid,cid,retry_of=jid,request_id=body.request_id,provider=provider)

    @app.get('/api/admin/media')
    def admin_media():
        def op(c):
            return [{'id':r['id'],'kind':meta.get('kind','unknown'),'project_id':meta.get('project_id'),
                     'source':meta.get('source','unknown'),'mime':r['mime'],'size_bytes':r['size_bytes'],
                     'duration':r['duration'],'width':meta.get('width'),'height':meta.get('height'),
                     'checksum':r['sha256'],'available':Path(r['local_path']).is_file(),
                     'test_only':bool(meta.get('test_only')),'created_at':r['created_at']}
                    for r in c.db.execute('SELECT * FROM media_records ORDER BY rowid DESC LIMIT 100')
                    for meta in [json.loads(r['metadata'])]]
        return execute(op)

    @app.get('/api/admin/profiles')
    def admin_profiles():
        def redact(value):
            if isinstance(value,dict):
                return {key:('***' if key.lower() in {'api_key','key','secret','token','password','authorization','credentials'} or key.lower().endswith('_api_key') else redact(item))
                        for key,item in value.items()}
            if isinstance(value,list):return [redact(item) for item in value]
            return value
        def op(c):
            result=[]
            for row in c.db.execute("SELECT * FROM objects WHERE kind='model_profile' ORDER BY id,version DESC LIMIT 100"):
                payload=json.loads(row['payload'])
                if payload.get('provider','darl')!='darl' or payload.get('transport',{}).get('base_url','https://api.darl.cn')!='https://api.darl.cn':
                    continue
                result.append({**dict(row),'payload':redact(payload)})
            return result
        return execute(op)

    @app.get('/api/admin/config')
    def admin_config():
        allowed={'llm_enabled','image_enabled','h3_enabled','poll_seconds','max_transient','max_download'}
        return execute(lambda c:{r['key']:r['value'] for r in c.db.execute('SELECT key,value FROM system_config') if r['key'] in allowed})

    @app.post('/api/admin/config')
    def admin_update_config(body: AdminConfigInput):
        if body.key in {'llm_enabled','image_enabled','h3_enabled'}:
            if body.value not in {'true','false'}:raise HTTPException(400,'invalid boolean setting')
        elif body.key=='poll_seconds':
            if not body.value.isdigit() or not 180<=int(body.value)<=900:raise HTTPException(400,'poll interval must be 180–900 seconds')
        elif body.key in {'max_transient','max_download'}:
            if not body.value.isdigit() or not 1<=int(body.value)<=3:raise HTTPException(400,'retry limit must be 1–3')
        else:raise HTTPException(400,'setting not allowed')
        def op(c):
            c.db.execute('UPDATE system_config SET value=?,updated_at=CURRENT_TIMESTAMP WHERE key=?',(body.value,body.key))
            c.db.commit()
            if body.key=='poll_seconds':worker.poll_seconds=int(body.value)
            if body.key=='max_transient':worker.max_transient=int(body.value)
            if body.key=='max_download':worker.max_download=int(body.value)
            return {'key':body.key,'value':body.value}
        return execute(op)

    @app.get('/api/admin/capability-packages')
    def admin_capability_packages():
        return execute(lambda c:[dict(r) for r in c.db.execute('SELECT * FROM capability_packages ORDER BY type,id,version DESC LIMIT 100')])

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
