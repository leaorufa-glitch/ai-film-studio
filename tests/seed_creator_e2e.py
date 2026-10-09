"""Disposable, explicitly TEST-ONLY browser fixture. Never targets #002 production.sqlite."""
import hashlib
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
core.register_media('media-e2e-test-only', str(source), hashlib.sha256(blob).hexdigest(), len(blob), 'video/mp4')
core.record_take('take-e2e-test-only', 'job-e2e-test-only', str(source), test_only=True,
                 media_id='media-e2e-test-only', provider_metadata={'source': 'TEST ONLY browser fixture'})
core.close()
print('TEST-ONLY E2E fixture ready')
