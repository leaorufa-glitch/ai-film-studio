"""#003 HTTP tests. No network provider call or production media is created."""
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import create_app
from film_core import Core
from film_core.fixture import seed


class CreatorApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / 'studio.sqlite'
        self.media = Path(self.tmp.name) / 'media'
        self.media.mkdir()
        self.app = create_app(self.path, self.media, test_mode=True)
        self.client = TestClient(self.app)

    def tearDown(self):
        self.client.close()
        self.tmp.cleanup()

    def fixture(self):
        core = seed(Core(str(self.path), test_mode=True), production=True)
        core.close()

    def core(self):
        return Core(str(self.path), test_mode=True)

    def test_project_create_read_update_and_script_versions(self):
        created = self.client.post('/api/projects', json={'payload': {'title': '海边', 'aspect_ratio': '16:9', 'idea': '寻找一封信'}})
        self.assertEqual(created.status_code, 200)
        pid = created.json()['project']['id']
        self.assertEqual(self.client.get(f'/api/projects/{pid}').json()['payload']['title'], '海边')
        self.assertEqual(len(self.client.get(f'/api/projects/{pid}/episodes').json()), 1)
        updated = self.client.patch(f'/api/projects/{pid}', json={'payload': {'script': '第一场：海边。'}, 'expected_version': 1})
        self.assertEqual(updated.json()['version'], 2)
        self.assertEqual(self.client.patch(f'/api/projects/{pid}', json={'payload': {'script': '旧覆盖'}, 'expected_version': 1}).status_code, 409)
        core = self.core()
        self.assertEqual(core.get('project', pid, 1)['payload'].get('script'), '寻找一封信')
        core.close()

    def test_scene_shot_update_versioning_and_impact(self):
        self.fixture()
        scene = self.client.get('/api/projects/station-film/scenes').json()[0]
        shot = self.client.get('/api/projects/station-film/shots?scene_id=station-scene').json()[0]
        update = self.client.patch('/api/projects/station-film/shots/S01', json={
            'payload': {'description': '新的导演设计'}, 'expected_version': shot['version'], 'status': 'draft'})
        self.assertEqual(update.json()['version'], 2)
        self.assertEqual(self.client.patch('/api/projects/station-film/shots/S01', json={
            'payload': {'description': '过期写入'}, 'expected_version': 1}).status_code, 409)
        self.assertEqual(self.client.get('/api/projects/station-film/impacts').json()[0]['level'], 'Must Replan / Rebuild')
        scene_update = self.client.patch('/api/projects/station-film/scenes/station-scene', json={
            'payload': {'story': '新故事事实'}, 'expected_version': scene['version']})
        self.assertEqual(scene_update.json()['version'], 2)
        core = self.core()
        self.assertEqual(core.get('shot', 'S01', 1)['payload']['description'], '中近景，林夏坐着展开旧信')
        core.close()

    def test_shot_clip_mapping_revisions_and_brief_versions(self):
        self.fixture()
        clip = next(x for x in self.client.get('/api/projects/station-film/clips').json() if x['id'] == 'A')
        self.assertEqual([x['shot_id'] for x in clip['mappings']], ['S01','S02','S03'])
        result = self.client.put('/api/projects/station-film/clips/A/mappings?expected_revision=0', json=[])
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['version'], 2)
        core = self.core()
        self.assertEqual(len(core.db.execute('SELECT * FROM shot_clip_revisions WHERE clip_id=?', ('A',)).fetchall()), 2)
        old = core.get('brief','brief:A')
        changed = {**old['payload'], 'purpose': '新的制作目的'}
        core.close()
        saved = self.client.post('/api/projects/station-film/clips/A/briefs', json={
            'payload': changed, 'expected_version': 1, 'status': 'approved'})
        self.assertEqual(saved.json()['version'], 2)
        self.assertEqual(len(self.client.get('/api/projects/station-film/clips/A/briefs').json()), 2)
        self.assertEqual(self.client.get('/api/projects/station-film/clips/A/readiness').json()['status'], 'NOT_READY')

    def test_job_snapshot_failed_provider_and_offline_ui_contract(self):
        self.fixture()
        core = self.core()
        task = core.compile_h3('task-api', 'brief:A', 'h3-test-contract')
        core.create_job('job-api', task['id'])
        core.job_event('job-api', 'failed', {'provider_error': {'code': 'fail_to_fetch_task', 'http_status': 404}})
        core.close()
        jobs = self.client.get('/api/projects/station-film/jobs').json()
        self.assertEqual(jobs[0]['snapshot']['task']['source_brief']['id'], 'brief:A')
        self.assertEqual(jobs[0]['status'], 'failed')
        self.assertEqual(self.client.get('/api/projects/station-film/clips/A/readiness').json()['status'], 'READY')
        with patch.dict(os.environ, {'DARL_API_KEY': 'test-key'}, clear=False):
            os.environ.pop('H3_SERVER_ON', None)
            self.assertEqual(self.client.get('/api/providers').json()['h3'], '服务未启动')
            blocked = self.client.post('/api/projects/station-film/clips/A/generate')
        self.assertEqual(blocked.status_code, 503)
        self.assertEqual(len(self.client.get('/api/projects/station-film/jobs').json()), 1)

    def test_valid_take_selection_observation_confirmation_and_timeline(self):
        self.fixture()
        core = self.core()
        task = core.compile_h3('task-test', 'brief:A', 'h3-test-contract')
        core.create_job('job-test', task['id'])
        core.job_event('job-test', 'running', {'provider_task_id': 'test-only'})
        core.job_event('job-test', 'succeeded', {'provider_task_id': 'test-only'})
        media_file = self.media / 'test-only.mp4'
        media_file.write_bytes(b'test-only media for API contract')
        blob = media_file.read_bytes()
        core.register_media('media-test', str(media_file), hashlib.sha256(blob).hexdigest(), len(blob), 'video/mp4')
        core.record_take('take-test', 'job-test', str(media_file), test_only=True, media_id='media-test')
        core.close()
        bad = self.client.post('/api/projects/station-film/clips/B/selection', json={'take_id': 'take-test', 'actor': 'tester'})
        self.assertEqual(bad.status_code, 400)
        chosen = self.client.post('/api/projects/station-film/clips/A/selection', json={'take_id': 'take-test', 'actor': 'tester'})
        self.assertEqual(chosen.status_code, 200)
        self.assertIsNone(self.client.get('/api/projects/station-film/reality').json()['A']['canonical'])
        observed = self.client.post('/api/projects/station-film/clips/A/observed', json={
            'take_id': 'take-test', 'state': {'summary': '左手持信'}, 'observer': 'tester'}).json()
        confirm = self.client.post(f"/api/projects/station-film/clips/A/canonical/{observed['id']}?actor=tester")
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(confirm.json()['payload']['summary'], '左手持信')
        added = self.client.post('/api/projects/station-film/timeline/items', json={
            'clip_id': 'A', 'take_id': 'take-test', 'trim_in': 0, 'volume': 1})
        self.assertEqual(added.status_code, 200)
        iid = added.json()['id']
        self.assertEqual(self.client.patch(f'/api/projects/station-film/timeline/items/{iid}', json={'trim_in': 1}).status_code, 200)
        self.assertEqual(len(self.client.get('/api/projects/station-film/timeline').json()['items']), 1)
        core = self.core()
        self.assertEqual(core.take('take-test')['media_uri'], str(media_file))
        core.close()

    def test_upload_validation_and_legacy_world_resolution(self):
        self.fixture()
        world = self.client.get('/api/projects/station-film/world/character').json()
        self.assertEqual(world[0]['id'], 'linxia')
        bad = self.client.post('/api/projects/station-film/assets/upload?owner_id=linxia&purpose=look',
                               files={'file': ('fake.png', b'not an image', 'image/png')})
        self.assertEqual(bad.status_code, 415)
        valid = self.client.post('/api/projects/station-film/assets/upload?owner_id=linxia&purpose=look',
                                 files={'file': ('real.png', b'\x89PNG\r\n\x1a\n' + b'data', 'image/png')})
        self.assertEqual(valid.status_code, 200)
        asset = valid.json()
        self.assertEqual(self.client.get('/api/media-asset/' + asset['id']).status_code, 200)
        newer = self.client.post('/api/projects/station-film/assets/upload?owner_id=linxia&purpose=look',
                                 files={'file': ('version2.png', b'\x89PNG\r\n\x1a\n' + b'new', 'image/png')}).json()
        self.assertEqual(newer['id'], asset['id'])
        self.assertEqual(newer['version'], 2)
        self.assertEqual(self.client.post('/api/projects/station-film/assets/' + asset['id'] + '/current',
                                          json={'version': 1}).status_code, 200)
        versions = self.client.get('/api/projects/station-film/world/asset_version').json()
        self.assertEqual(len(versions), 2)
        self.assertEqual(next(v['version'] for v in versions if v['is_current']), 1)


if __name__ == '__main__':
    unittest.main()
