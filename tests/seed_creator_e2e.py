"""Disposable, explicitly TEST-ONLY browser fixture. Never targets #002 production.sqlite."""
import hashlib
import base64
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from film_core import Core
from film_core.fixture import seed
from apps.api.main import APP_SCHEMA

path = Path(os.environ['FILM_STUDIO_DB'])
media = Path(os.environ['FILM_STUDIO_MEDIA'])
if '/e2e/' not in str(path) or path.name != 'studio-test.sqlite':
    raise SystemExit('refusing to seed a non-E2E database')
path.parent.mkdir(parents=True, exist_ok=True)
media.mkdir(parents=True, exist_ok=True)
if path.exists():
    path.unlink()
core = seed(Core(str(path), test_mode=True), production=True)
core.db.executescript(APP_SCHEMA)
task = core.compile_h3('task-e2e-test-only', 'brief:A', 'h3-test-contract')
core.create_job('job-e2e-test-only', task['id'])
core.job_event('job-e2e-test-only', 'running', {'provider_task_id': 'TEST-ONLY'})
core.job_event('job-e2e-test-only', 'succeeded', {'provider_task_id': 'TEST-ONLY'})
source = media / 'TEST-ONLY-no-video.mp4'
source.write_bytes(b'TEST ONLY: synthetic candidate; no video was generated')
blob = source.read_bytes()
core.register_media('media-e2e-test-only', str(source), hashlib.sha256(blob).hexdigest(), len(blob), 'video/mp4',
                    metadata={'kind':'video_take','project_id':'station-film','source':'TEST ONLY fixture','test_only':True})
core.record_take('take-e2e-test-only', 'job-e2e-test-only', str(source), test_only=True,
                 media_id='media-e2e-test-only', provider_metadata={'source': 'TEST ONLY browser fixture'})
core.create_job('job-e2e-failed-test-only',task['id'])
core.job_event('job-e2e-failed-test-only','failed',{'provider_error':{'code':'NETWORK_ERROR','transient':True},'error_category':'NETWORK_ERROR'})
core.create_job('job-e2e-running-test-only',task['id'])
core.job_event('job-e2e-running-test-only','running',{'provider_task_id':'TEST-ONLY-running'})
core.db.execute("INSERT INTO job_runtime(job_id,provider_task_id,next_poll_at,submitted_at) VALUES (?,?,?,CURRENT_TIMESTAMP)",
                ('job-e2e-running-test-only','TEST-ONLY-running','2999-01-01T00:00:00+00:00'))
context={'task':'scene_plan','target_id':'station-scene','instruction':'TEST ONLY','selected_text':'',
         'items':[{'kind':'scene','id':'station-scene','version':1,'authority':'FORMAL','content':core.get('scene','station-scene')['payload']}]}
for pid,proposal_task,change in [
    ('proposal-e2e-scene','scene_plan',{'scenes':[{'place':'站台入口','story':'TEST ONLY 场次提案：林夏望向列车灯。'}]}),
    ('proposal-e2e-shot','shot_plan',{'shots':[{'purpose':'TEST ONLY 观察决心','description':'林夏在站台入口抬眼','action':'停下脚步后望向前方','performance':'呼吸放慢','camera':'中近景固定','sound':'雨声','duration':4}]}),
    ('proposal-e2e-clip','clip_plan',{'clips':[{'name':'TEST ONLY Clip 提案','duration':4,'handoff':'INDEPENDENT'}]})]:
    core.db.execute('INSERT INTO ai_proposals(id,project_id,task,target_id,context,change,explanation,provenance,provider,model,status) VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                    (pid,'station-film',proposal_task,'station-scene',json.dumps(context,ensure_ascii=False),
                     json.dumps(change,ensure_ascii=False),'TEST ONLY 浏览器提案，不是实际模型输出。',
                     json.dumps({'source':'test-fixture','authority':'PROPOSAL','test_only':True}),
                     'test-only','test-only','pending'))
picture=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVQIHWP4z8DwHwAFgAI/ScL/nwAAAABJRU5ErkJggg==')
candidate_file=media/'TEST-ONLY-image-candidate.png';candidate_file.write_bytes(picture)
core.register_media('media-e2e-image-candidate',str(candidate_file),hashlib.sha256(picture).hexdigest(),len(picture),'image/png',
                    metadata={'kind':'image_candidate','project_id':'station-film','source':'TEST ONLY fixture','test_only':True})
core.db.execute('INSERT INTO asset_candidates(id,project_id,owner_id,purpose,prompt,media_id,provider,model,provenance,status) VALUES (?,?,?,?,?,?,?,?,?,?)',
                ('candidate-e2e-test-only','station-film','linxia','TEST ONLY 人物候选','TEST ONLY 图像，仅用于界面测试',
                 'media-e2e-image-candidate','test-only','test-only',
                 json.dumps({'source':'test-fixture','authority':'CANDIDATE','test_only':True}),'pending'))
core.db.commit()
core.close()
print('TEST-ONLY E2E fixture ready')
