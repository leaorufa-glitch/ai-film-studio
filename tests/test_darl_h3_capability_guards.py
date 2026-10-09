"""Cloud capability and 404 regressions. All jobs, media and HTTP responses are TEST ONLY."""
import copy
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from fastapi.testclient import TestClient

from apps.api.job_runtime import JobWorker
from apps.api.main import create_app
from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter
from film_core.fixture import seed
from film_core.h3_profile import CLOUD_H3_MODEL, LOCAL_H3_MODEL, H3_PROFILE_IDS, darl_h3_profile


class CloudCapabilityGuardTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'studio.sqlite'
        self.media = Path(temporary.name) / 'media'
        self.core = seed(Core(str(self.path), test_mode=True), production=True)
        self.addCleanup(self.core.close)
        environment = patch.dict(os.environ, {'DARL_API_KEY': 'TEST-ONLY', 'H3_SERVER_ON': '0'})
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(create_app(self.path, self.media, test_mode=True, start_worker=False))
        self.addCleanup(self.client.close)
        self.core.put('model_profile', H3_PROFILE_IDS[LOCAL_H3_MODEL], darl_h3_profile(), 'TEST ONLY')

    def compile(self, clip, model, suffix, continuation=None):
        return self.core.compile_h3('TEST-ONLY-' + suffix, 'brief:' + clip, H3_PROFILE_IDS[model],
                                    parameters={'resolution': '480P', 'num_inference_steps': 20,
                                                'turbo': False, 'watermark': False}, continuation=continuation)

    def prepare_continuation(self):
        if not self.core.selection('C1'):
            facts = self.core.get('brief', 'brief:A')['payload']['state_in']['facts']
            for clip, upstream in [('A', None), ('B', 'A'), ('C1', 'B')]:
                if upstream:
                    self.core.rebase_brief_state(clip, upstream)
                task = self.compile(clip, LOCAL_H3_MODEL, 'upstream-' + clip)
                job_id, take_id = 'TEST-ONLY-job-' + clip, 'TEST-ONLY-take-' + clip
                self.core.create_job(job_id, task['id'])
                self.core.job_event(job_id, 'running')
                self.core.job_event(job_id, 'succeeded')
                self.core.record_take(take_id, job_id, 'test-only://' + clip, test_only=True)
                self.core.select_take(clip, take_id, 'TEST ONLY human')
                self.core.observe('TEST-ONLY-observed-' + clip, take_id, facts, 'TEST ONLY human')
                self.core.confirm_state(clip, 'TEST-ONLY-observed-' + clip, 'TEST ONLY human')
            self.core.rebase_brief_state('C2', 'C1')
            self.core.create_stable_tail('TEST-ONLY-tail', 'C1', 'TEST-ONLY-take-C1',
                                         'https://example.invalid/TEST-ONLY-tail.mp4', {'stable': True})
        return self.core.continuation_source('C1', 'TEST-ONLY-tail')

    def special_task(self, mode, model=CLOUD_H3_MODEL, old_profile=False):
        profile = darl_h3_profile() if old_profile else darl_h3_profile(execution_model=model)
        if old_profile:
            profile.update({'model_id': model, 'execution_model': model})
        self.core.put('model_profile', H3_PROFILE_IDS[model], profile, 'TEST ONLY profile')
        if mode == 'VIDEO_CONTINUATION':
            continuation = self.prepare_continuation()
            return self.compile('C2', model, mode + model, continuation)
        brief = self.core.get('brief', 'brief:A')
        self.core.put('asset_version', 'TEST-ONLY-frame-asset', {'uri': 'https://example.invalid/TEST-ONLY-frame.png'}, 'TEST ONLY')
        reference = self.core.put('reference_binding', 'TEST-ONLY-frame-reference', {
            'asset_id': 'TEST-ONLY-frame-asset', 'asset_version': 1, 'uri': 'https://example.invalid/TEST-ONLY-frame.png',
            'role': 'first_frame', 'media_type': 'image'}, 'TEST ONLY')
        self.core.save_brief('A', {**brief['payload'], 'handoff': mode, 'references': [reference['id']]}, 'TEST ONLY')
        return self.compile('A', model, mode + model)

    def assert_rejected(self, task, code, retry_of=None):
        before = copy.deepcopy(task)
        profile = self.core.get('model_profile', task['model_profile']['id'], task['model_profile']['version'])
        result = self.core.preflight(task['id'], retry_of=retry_of)
        self.assertFalse(result.ready)
        self.assertIn(code, {reason['code'] for reason in result.reasons})
        self.assertEqual(self.core.task(task['id']), before)
        self.assertEqual(self.core.get('model_profile', profile['id'], profile['version']), profile)
        self.assertEqual(before['task_mode'], self.core.task(task['id'])['task_mode'])
        with self.assertRaisesRegex(DomainError, code):
            self.core.create_job('TEST-ONLY-rejected-' + task['id'], task['id'], retry_of=retry_of)
        opener = Mock()
        with self.assertRaisesRegex(DomainError, code):
            DarlH3Adapter(key='TEST-ONLY', opener=opener).submit(task, 'TEST-ONLY-rejected')
        opener.assert_not_called()

    def historical_failed_job(self, task):
        with patch('film_core.core.h3_execution_capability_reasons', return_value=[]):
            self.assertTrue(self.core.preflight(task['id']).ready)
            job = self.core.create_job('TEST-ONLY-old-' + task['id'], task['id'],
                                       cost_estimate={'provider': 'darl', 'execution_model': CLOUD_H3_MODEL})
        self.core.job_event(job['id'], 'failed', {'provider': 'darl', 'execution_model': CLOUD_H3_MODEL,
                                                'error_category': 'NETWORK_ERROR'})
        return self.core.job(job['id'])

    def test_cloud_profile_never_promotes_special_temporal_capabilities_from_basic_success(self):
        for runtime_verified in (False, True):
            cloud = darl_h3_profile(runtime_verified, CLOUD_H3_MODEL)
            self.assertNotIn('VIDEO_CONTINUATION', cloud['supported_modes'])
            self.assertNotIn('KEYFRAME_CONSTRAINED', cloud['supported_modes'])
            self.assertFalse(cloud['temporal_controls']['verified'])
            self.assertFalse(cloud['temporal_controls']['video_continuation'])
            self.assertFalse(cloud['temporal_controls']['first_frame'])
            self.assertFalse(cloud['temporal_controls']['last_frame'])
            self.assertIsNone(cloud['temporal_controls']['source'])
            self.assertEqual(cloud['media_capability']['counts']['first_frame'], 0)
            self.assertEqual(cloud['media_capability']['counts']['last_frame'], 0)

    def test_self_hosted_existing_special_temporal_contract_is_unchanged(self):
        local = darl_h3_profile()
        self.assertEqual(local['supported_modes'], ['INDEPENDENT', 'MULTI_SHOT_ONE_PASS',
            'STATE_CONTINUE_NEW_VIEW', 'VISUAL_ANCHOR', 'VIDEO_CONTINUATION', 'KEYFRAME_CONSTRAINED'])
        self.assertEqual(local['temporal_controls'], {'verified': True, 'first_frame': True,
            'last_frame': True, 'video_continuation': True, 'source': local['duration_envelope']['source']})
        self.assertEqual(local['media_capability']['counts']['first_frame'], 1)
        self.assertEqual(local['media_capability']['counts']['last_frame'], 1)

    def test_cloud_video_continuation_is_refused_even_with_valid_upstream_state_and_tail(self):
        task = self.special_task('VIDEO_CONTINUATION')
        self.assert_rejected(task, 'VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED')

    def test_cloud_keyframe_task_is_refused_even_with_first_frame_reference(self):
        task = self.special_task('KEYFRAME_CONSTRAINED')
        self.assert_rejected(task, 'KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED')

    def test_old_persisted_cloud_continuation_profile_and_task_cannot_bypass_guard(self):
        task = self.special_task('VIDEO_CONTINUATION', old_profile=True)
        original = self.historical_failed_job(task)
        self.assertTrue(task['model_profile_snapshot']['temporal_controls']['verified'])
        self.assert_rejected(task, 'VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED', original['id'])
        self.assertEqual(self.core.job(original['id']), original)
        with patch('apps.api.main.DarlH3Adapter') as adapter:
            response = self.client.post('/api/projects/station-film/clips/C2/generate', params={'retry_of': original['id']})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED', response.text)
        adapter.assert_not_called()
        self.assertEqual(self.core.job(original['id']), original)

    def test_old_persisted_cloud_keyframe_retry_remains_blocked_after_new_profile_version(self):
        task = self.special_task('KEYFRAME_CONSTRAINED', old_profile=True)
        original = self.historical_failed_job(task)
        self.core.put('model_profile', H3_PROFILE_IDS[CLOUD_H3_MODEL],
                      darl_h3_profile(execution_model=CLOUD_H3_MODEL), 'TEST ONLY safer latest profile')
        self.assert_rejected(task, 'KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED', original['id'])
        with patch('apps.api.main.DarlH3Adapter') as adapter:
            response = self.client.post('/api/admin/jobs/' + original['id'] + '/technical-retry',
                                        json={'request_id': 'TEST-ONLY-old-keyframe'})
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED', response.text)
        adapter.assert_not_called()
        self.assertEqual(self.core.job(original['id']), original)

    def test_old_cloud_task_without_execution_model_field_is_still_refused(self):
        task = self.special_task('KEYFRAME_CONSTRAINED', old_profile=True)
        task.pop('execution_model')
        self.core.db.execute('UPDATE compiled_tasks SET payload=? WHERE id=?', (json.dumps(task), task['id']))
        self.core.db.commit()
        self.assert_rejected(task, 'KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED')

    def test_new_cloud_generation_cannot_use_old_permissive_profile(self):
        task = self.special_task('VIDEO_CONTINUATION', old_profile=True)
        brief = self.core.get('brief', 'brief:C2')
        profile = self.core.get('model_profile', H3_PROFILE_IDS[CLOUD_H3_MODEL])
        jobs_before = self.core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0]
        with patch('apps.api.main.DarlH3Adapter') as adapter:
            response = self.client.post('/api/projects/station-film/clips/C2/generate')
        self.assertEqual(response.status_code, 400, response.text)
        self.assertIn('VIDEO_CONTINUATION_UNVERIFIED_OR_UNSUPPORTED', response.text)
        adapter.assert_not_called()
        self.assertEqual(self.core.db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], jobs_before)
        self.assertEqual(self.core.task(task['id']), task)
        self.assertEqual(self.core.get('brief', 'brief:C2'), brief)
        self.assertEqual(self.core.get('model_profile', profile['id'], profile['version']), profile)

    def test_cloud_multishot_clip_a_remains_preflight_ready_and_brief_independent(self):
        brief = self.core.get('brief', 'brief:A')
        for model in (LOCAL_H3_MODEL, CLOUD_H3_MODEL):
            self.core.put('model_profile', H3_PROFILE_IDS[model], darl_h3_profile(execution_model=model), 'TEST ONLY')
            task = self.compile('A', model, 'multishot-' + model)
            self.assertTrue(self.core.preflight(task['id']).ready)
            self.assertEqual(task['task_mode'], 'MULTI_SHOT_ONE_PASS')
            self.assertEqual(task['source_brief'], {'id': 'brief:A', 'version': 1})
            self.assertEqual(DarlH3Adapter(key='TEST-ONLY').build_request(task)['model'], model)
        self.assertEqual(self.core.get('brief', 'brief:A'), brief)

    def test_self_hosted_continuation_with_valid_tail_remains_preflight_ready(self):
        task = self.special_task('VIDEO_CONTINUATION', model=LOCAL_H3_MODEL)
        self.assertTrue(self.core.preflight(task['id']).ready)
        body = DarlH3Adapter(key='TEST-ONLY').build_request(task)
        self.assertEqual(body['model'], LOCAL_H3_MODEL)
        self.assertEqual(body['content'][-1]['role'], 'reference_video')

    def test_self_hosted_keyframe_contract_remains_preflight_ready(self):
        task = self.special_task('KEYFRAME_CONSTRAINED', model=LOCAL_H3_MODEL)
        self.assertTrue(self.core.preflight(task['id']).ready)
        body = DarlH3Adapter(key='TEST-ONLY').build_request(task)
        self.assertEqual(body['ratio'], 'adaptive')
        self.assertEqual(body['content'][-1]['role'], 'first_frame')

    def test_first_frame_input_cannot_bypass_cloud_guard_with_basic_task_mode(self):
        task = self.special_task('MULTI_SHOT_ONE_PASS', old_profile=True)
        self.assert_rejected(task, 'KEYFRAME_CONSTRAINED_UNVERIFIED_OR_UNSUPPORTED')

    def test_runtime_does_not_resume_old_cloud_special_task_or_mutate_job(self):
        task = self.special_task('VIDEO_CONTINUATION', old_profile=True)
        with patch('film_core.core.h3_execution_capability_reasons', return_value=[]):
            job = self.core.create_job('TEST-ONLY-old-running-special', task['id'],
                                       cost_estimate={'provider': 'darl', 'execution_model': CLOUD_H3_MODEL})
        self.core.job_event(job['id'], 'running', {'provider': 'darl', 'provider_task_id': 'TEST-ONLY-old-task'})
        original = self.core.job(job['id'])
        factory = Mock()
        worker = JobWorker(self.path, self.media, test_mode=True, adapter_factory=factory)
        worker.recover()
        worker.tick()
        factory.assert_not_called()
        self.assertEqual(self.core.job(job['id']), original)
        self.assertEqual(self.core.db.execute('SELECT COUNT(*) FROM job_runtime WHERE job_id=?', (job['id'],)).fetchone()[0], 0)


class Darl404ClassificationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'studio.sqlite'
        seed(Core(str(self.path), test_mode=True), production=True).close()
        environment = patch.dict(os.environ, {'DARL_API_KEY': 'TEST-ONLY', 'H3_SERVER_ON': '0'})
        environment.start()
        self.addCleanup(environment.stop)
        self.client = TestClient(create_app(self.path, Path(temporary.name) / 'media', test_mode=True, start_worker=False))
        self.addCleanup(self.client.close)

    def core(self):
        core = Core(str(self.path), test_mode=True)
        self.addCleanup(core.close)
        return core

    def failure_adapter(self, code='fail_to_fetch_task'):
        requests = []
        def opener(request, timeout):
            requests.append(request)
            detail = {'message': 'TEST ONLY execution route unavailable'}
            if code:
                detail['code'] = code
            raise HTTPError(request.full_url, 404, 'TEST ONLY Not Found', {}, io.BytesIO(json.dumps(detail).encode()))
        return DarlH3Adapter(key='TEST-ONLY', opener=opener), requests

    def submit(self, **parameters):
        return self.client.post('/api/projects/station-film/clips/A/generate', params=parameters)

    def assert_404_preserved(self, response, model, code):
        self.assertEqual(response.status_code, 503, response.text)
        job = self.core().job(response.json()['detail']['job_id'])
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['metadata']['error_category'], code)
        self.assertEqual(job['metadata']['provider_error']['code'], code)
        self.assertEqual(job['metadata']['provider_error']['http_status'], 404)
        self.assertEqual(job['metadata']['provider_error']['message'], 'TEST ONLY execution route unavailable')
        self.assertEqual(job['snapshot']['task']['execution_model'], model)
        self.assertEqual(job['metadata']['provider'], 'darl')
        return job

    def test_cloud_specific_404_preserves_provider_category_without_self_hosted_message(self):
        adapter, requests = self.failure_adapter()
        brief = self.core().get('brief', 'brief:A')
        with patch('apps.api.main.DarlH3Adapter', return_value=adapter):
            response = self.submit()
        self.assertEqual(response.json()['detail']['code'], 'fail_to_fetch_task')
        self.assertEqual(response.json()['detail']['message'], '视频服务提交失败。')
        self.assertNotIn('服务器当前未启动', response.text)
        self.assert_404_preserved(response, CLOUD_H3_MODEL, 'fail_to_fetch_task')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].full_url, 'https://api.darl.cn/v1/videos')
        self.assertEqual(json.loads(requests[0].data)['model'], CLOUD_H3_MODEL)
        self.assertEqual(self.core().get('brief', 'brief:A'), brief)

    def test_cloud_generic_http_404_retains_http_category(self):
        adapter, requests = self.failure_adapter(code=None)
        with patch('apps.api.main.DarlH3Adapter', return_value=adapter):
            response = self.submit()
        self.assertEqual(response.json()['detail']['code'], 'HTTP_404')
        self.assertNotIn('服务器当前未启动', response.text)
        self.assert_404_preserved(response, CLOUD_H3_MODEL, 'HTTP_404')
        self.assertEqual(len(requests), 1)

    def test_self_hosted_offline_404_keeps_existing_unavailable_classification(self):
        adapter, requests = self.failure_adapter()
        with patch.dict(os.environ, {'H3_SERVER_ON': '1'}), patch('apps.api.main.DarlH3Adapter', return_value=adapter):
            response = self.submit()
        self.assertEqual(response.json()['detail']['code'], 'PROVIDER_UNAVAILABLE')
        self.assertEqual(response.json()['detail']['message'], '自建 H3 视频服务器当前未启动。')
        self.assert_404_preserved(response, LOCAL_H3_MODEL, 'fail_to_fetch_task')
        self.assertEqual(len(requests), 1)
        self.assertEqual(json.loads(requests[0].data)['model'], LOCAL_H3_MODEL)

    def test_cloud_404_technical_retry_retains_task_and_model_when_self_hosted_becomes_available(self):
        adapter, requests = self.failure_adapter()
        with patch('apps.api.main.DarlH3Adapter', return_value=adapter):
            failed = self.submit()
            original = self.core().job(failed.json()['detail']['job_id'])
            with patch.dict(os.environ, {'H3_SERVER_ON': '1'}):
                response = self.client.post('/api/admin/jobs/' + original['id'] + '/technical-retry',
                                            json={'request_id': 'TEST-ONLY-cloud-404-retry'})
        retry = self.assert_404_preserved(response, CLOUD_H3_MODEL, 'fail_to_fetch_task')
        self.assertEqual(response.json()['detail']['code'], 'fail_to_fetch_task')
        self.assertEqual(retry['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(retry['task_id'], original['task_id'])
        self.assertEqual(retry['snapshot']['retry_of'], original['id'])
        self.assertEqual(retry['snapshot']['cost_estimate']['attempt_kind'], 'technical_retry')
        self.assertEqual(self.core().job(original['id']), original)
        self.assertEqual(len(requests), 2)
        self.assertTrue(all(json.loads(request.data)['model'] == CLOUD_H3_MODEL for request in requests))


if __name__ == '__main__':
    unittest.main()
