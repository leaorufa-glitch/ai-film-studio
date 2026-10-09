"""Darl-only routing contracts. Every submission and upstream response is TEST ONLY."""
import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient

from apps.api.job_runtime import JobWorker
from apps.api.main import create_app
from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError
from film_core.fixture import seed
from film_core.h3_profile import CLOUD_H3_MODEL, LOCAL_H3_MODEL, H3_PROFILE_IDS, darl_h3_profile
from scripts.h3_slice import submit_one, sync_one


class DarlModelContractTests(unittest.TestCase):
    def setUp(self):
        self.core = seed(Core(test_mode=True), production=True)
        self.addCleanup(self.core.close)

    def task(self, model):
        self.core.put('model_profile', H3_PROFILE_IDS[model],
                      darl_h3_profile(execution_model=model), 'TEST ONLY', 'documented')
        return self.core.compile_h3('TEST-ONLY-' + model, 'brief:A', H3_PROFILE_IDS[model],
                                    parameters={'resolution': '480P', 'num_inference_steps': 20,
                                                'turbo': False, 'watermark': False})

    def assert_model_submission(self, model):
        requests = []
        def opener(request, timeout):
            requests.append(request)
            return io.BytesIO(b'{"id":"TEST-ONLY-task","status":"queued"}')
        task = self.task(model)
        response = DarlH3Adapter(key='TEST-ONLY', opener=opener).submit(task, 'TEST-ONLY-job')
        self.assertEqual(response['id'], 'TEST-ONLY-task')
        self.assertEqual(len(requests), 1)
        self.assertEqual(requests[0].full_url, 'https://api.darl.cn/v1/videos')
        self.assertEqual(requests[0].method, 'POST')
        body = json.loads(requests[0].data)
        self.assertEqual(body['model'], model)
        self.assertEqual(body['duration'], 10)
        self.assertEqual(body['ratio'], '16:9')
        self.assertEqual(body['resolution'], '480P')
        self.assertEqual(body['num_inference_steps'], 20)
        self.assertEqual(task['execution_model'], model)
        self.assertEqual(task['provider'], 'darl')

    def test_self_hosted_model_uses_darl_videos(self):
        self.assert_model_submission(LOCAL_H3_MODEL)

    def test_cloud_model_uses_same_darl_videos(self):
        self.assert_model_submission(CLOUD_H3_MODEL)

    def test_model_mismatch_is_rejected_without_submission(self):
        task = self.task(LOCAL_H3_MODEL)
        task['execution_model'] = CLOUD_H3_MODEL
        opener = Mock()
        with self.assertRaisesRegex(DomainError, 'no silent substitution'):
            DarlH3Adapter(key='TEST-ONLY', opener=opener).submit(task, 'TEST-ONLY-job')
        opener.assert_not_called()

    def test_darl_task_without_new_routing_fields_is_compatible(self):
        task = self.task(LOCAL_H3_MODEL)
        task.pop('execution_model')
        task.pop('provider')
        self.assertEqual(DarlH3Adapter(key='TEST-ONLY').build_request(task)['model'], LOCAL_H3_MODEL)


class DarlRoutingTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.path = Path(temporary.name) / 'studio.sqlite'
        self.media = Path(temporary.name) / 'media'
        seed(Core(str(self.path), test_mode=True), production=True).close()
        environment = patch.dict(os.environ, {'DARL_API_KEY': 'TEST-ONLY', 'H3_SERVER_ON': '1'})
        environment.start()
        self.addCleanup(environment.stop)
        adapter_patch = patch('apps.api.main.DarlH3Adapter')
        self.adapter = adapter_patch.start().return_value
        self.addCleanup(adapter_patch.stop)
        self.adapter.build_request.return_value = {}
        self.adapter.submit.return_value = {'id': 'TEST-ONLY-task', 'status': 'queued'}
        self.client = TestClient(create_app(self.path, self.media, test_mode=True, start_worker=False))
        self.addCleanup(self.client.close)

    def core(self):
        core = Core(str(self.path), test_mode=True)
        self.addCleanup(core.close)
        return core

    def submit(self, **parameters):
        return self.client.post('/api/projects/station-film/clips/A/generate', params=parameters)

    def fail_job(self):
        self.adapter.submit.side_effect = ProviderError('NETWORK_ERROR', 'TEST ONLY', transient=True)
        response = self.submit()
        self.assertEqual(response.status_code, 503, response.text)
        self.adapter.submit.side_effect = None
        return self.core().job(response.json()['detail']['job_id'])

    def assert_new_route(self, model):
        core = self.core()
        brief = core.get('brief', 'brief:A')
        response = self.submit()
        self.assertEqual(response.status_code, 200, response.text)
        job = response.json()['job']
        task = job['snapshot']['task']
        self.assertEqual(task['execution_model'], model)
        self.assertEqual(task['target_model'], model)
        self.assertEqual(task['provider'], 'darl')
        self.assertEqual(core.task(job['task_id']), task)
        self.assertEqual(job['snapshot']['cost_estimate']['execution_model'], model)
        self.assertEqual(job['snapshot']['cost_estimate']['provider'], 'darl')
        self.assertEqual(job['metadata']['execution_model'], model)
        self.assertEqual(job['metadata']['provider'], 'darl')
        self.assertEqual(core.get('brief', 'brief:A'), brief)
        self.assertEqual(self.adapter.submit.call_args.args[0], task)

    def test_available_self_hosted_selects_local_model(self):
        self.assert_new_route(LOCAL_H3_MODEL)

    def test_unavailable_self_hosted_selects_cloud_model(self):
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            self.assert_new_route(CLOUD_H3_MODEL)

    def test_missing_availability_flag_selects_cloud_model(self):
        with patch.dict(os.environ):
            os.environ.pop('H3_SERVER_ON', None)
            self.assert_new_route(CLOUD_H3_MODEL)

    def test_local_retry_is_rejected_when_local_model_is_offline(self):
        original = self.fail_job()
        self.adapter.submit.reset_mock()
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            for endpoint in ('creator', 'admin'):
                response = self.submit(retry_of=original['id']) if endpoint == 'creator' else self.client.post(
                    '/api/admin/jobs/' + original['id'] + '/technical-retry', json={'request_id': 'TEST-ONLY-retry'})
                self.assertEqual(response.status_code, 503, response.text)
                self.assertEqual(response.json()['detail']['code'], 'EXECUTION_MODEL_UNAVAILABLE')
        self.adapter.submit.assert_not_called()
        self.assertEqual(self.core().job(original['id']), original)
        self.assertEqual(self.core().db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)

    def test_cloud_retry_stays_cloud_after_self_hosted_becomes_available(self):
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            original = self.fail_job()
        response = self.submit(retry_of=original['id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['snapshot']['task'], original['snapshot']['task'])
        self.assertEqual(self.adapter.submit.call_args.args[0]['execution_model'], CLOUD_H3_MODEL)

    def test_old_darl_task_without_routing_fields_retains_original_parameters(self):
        core = self.core()
        profile = darl_h3_profile()
        profile.pop('provider')
        profile.pop('execution_model')
        core.put('model_profile', 'h3-darl', profile, 'TEST ONLY historical Darl')
        task = core.compile_h3('TEST-ONLY-old-darl-task', 'brief:A', 'h3-darl',
                               parameters={'resolution': '768P', 'num_inference_steps': 10,
                                           'turbo': False, 'watermark': False})
        task.pop('execution_model')
        core.db.execute('UPDATE compiled_tasks SET payload=? WHERE id=?', (json.dumps(task), task['id']))
        core.db.commit()
        core.create_job('TEST-ONLY-old-darl-job', task['id'])
        core.job_event('TEST-ONLY-old-darl-job', 'failed', {'error_category': 'NETWORK_ERROR'})
        original = core.job('TEST-ONLY-old-darl-job')
        response = self.submit(retry_of=original['id'])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()['job']['snapshot']['task'], task)
        self.assertEqual(response.json()['job']['snapshot']['cost_estimate']['execution_model'], LOCAL_H3_MODEL)
        self.assertEqual(response.json()['job']['snapshot']['cost_estimate']['resolution'], '768P')
        self.assertEqual(self.adapter.submit.call_args.args[0], task)
        self.assertEqual(core.job(original['id']), original)

    def test_model_switch_requires_new_creative_execution_and_preserves_brief(self):
        original = self.fail_job()
        core = self.core()
        brief = core.get('brief', 'brief:A')
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            response = self.submit(creative_reason='TEST ONLY execution model switch')
        self.assertEqual(response.status_code, 200, response.text)
        new_job = response.json()['job']
        self.assertNotEqual(new_job['task_id'], original['task_id'])
        self.assertIsNone(new_job['snapshot']['retry_of'])
        self.assertEqual(new_job['snapshot']['cost_estimate']['attempt_kind'], 'creative_regenerate')
        self.assertEqual(new_job['snapshot']['task']['execution_model'], CLOUD_H3_MODEL)
        self.assertEqual(new_job['snapshot']['task']['source_brief'], original['snapshot']['task']['source_brief'])
        self.assertEqual(new_job['snapshot']['task']['semantic_hash'], original['snapshot']['task']['semantic_hash'])
        self.assertEqual(core.get('brief', 'brief:A'), brief)
        self.assertEqual(core.job(original['id']), original)

    def legacy_job(self, status='failed'):
        core = self.core()
        legacy = CLOUD_H3_MODEL.partition('-')[0]
        profile_id = 'h3-' + legacy
        core.put('model_profile', profile_id, {**darl_h3_profile(), 'provider': legacy}, 'TEST ONLY legacy')
        task = core.compile_h3('TEST-ONLY-legacy-task', 'brief:A', profile_id,
                               parameters={'resolution': '480P', 'num_inference_steps': 20,
                                           'turbo': False, 'watermark': False})
        core.create_job('TEST-ONLY-legacy-job', task['id'], cost_estimate={'provider': legacy})
        core.job_event('TEST-ONLY-legacy-job', status, {'provider': legacy, 'provider_task_id': 'TEST-ONLY-old-task',
                                                     'error_category': 'NETWORK_ERROR'})
        return core.job('TEST-ONLY-legacy-job')

    def test_legacy_direct_job_cannot_retry_and_remains_unchanged(self):
        original = self.legacy_job()
        for endpoint in ('creator', 'admin'):
            response = self.submit(retry_of=original['id']) if endpoint == 'creator' else self.client.post(
                '/api/admin/jobs/' + original['id'] + '/technical-retry', json={'request_id': 'TEST-ONLY-legacy'})
            self.assertEqual(response.status_code, 400, response.text)
            self.assertEqual(response.json()['detail'], 'LEGACY_PROVIDER_UNSUPPORTED')
        self.adapter.submit.assert_not_called()
        self.assertEqual(self.core().job(original['id']), original)
        row = self.client.get('/api/admin/jobs').json()[0]
        self.assertTrue(row['legacy_provider'])
        self.assertEqual(row['provider'], original['metadata']['provider'])
        self.assertNotIn('h3-' + original['metadata']['provider'],
                         [row['id'] for row in self.client.get('/api/admin/profiles').json()])

    def test_api_rejects_retired_and_unknown_providers(self):
        for provider in (CLOUD_H3_MODEL.partition('-')[0], 'unknown-provider'):
            response = self.submit(provider=provider)
            self.assertEqual(response.status_code, 400, response.text)
        self.adapter.submit.assert_not_called()
        self.assertEqual(self.core().db.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 0)

    def test_legacy_profile_without_provider_metadata_is_still_rejected(self):
        original = self.legacy_job()
        core = self.core()
        snapshot = original['snapshot']
        snapshot['task'].pop('provider')
        snapshot['cost_estimate'].pop('provider')
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.execute('UPDATE compiled_tasks SET payload=? WHERE id=?', (json.dumps(snapshot['task']), original['task_id']))
        core.db.execute("UPDATE job_events SET metadata=? WHERE job_id=? AND status='failed'",
                        (json.dumps({'error_category': 'NETWORK_ERROR'}), original['id']))
        core.db.commit()
        response = self.submit(retry_of=original['id'])
        self.assertEqual(response.status_code, 400, response.text)
        self.assertEqual(response.json()['detail'], 'LEGACY_PROVIDER_UNSUPPORTED')
        self.adapter.submit.assert_not_called()

    def test_conflicting_execution_model_provenance_is_rejected(self):
        original = self.fail_job()
        core = self.core()
        snapshot = original['snapshot']
        snapshot['cost_estimate']['execution_model'] = CLOUD_H3_MODEL
        core.db.execute('UPDATE jobs SET snapshot=? WHERE id=?', (json.dumps(snapshot), original['id']))
        core.db.commit()
        self.adapter.submit.reset_mock()
        response = self.submit(retry_of=original['id'])
        self.assertEqual(response.status_code, 400, response.text)
        self.adapter.submit.assert_not_called()

    def test_retired_environment_and_config_do_not_affect_routing(self):
        legacy = CLOUD_H3_MODEL.partition('-')[0]
        before = self.client.get('/api/providers').json()
        with patch.dict(os.environ, {legacy.upper() + '_API_KEY': 'TEST-ONLY', legacy.upper() + '_WEBAPP_ID': '12345'}):
            self.assertEqual(self.client.get('/api/providers').json(), before)
            with patch.dict(os.environ, {'DARL_API_KEY': ''}):
                self.assertEqual(self.client.get('/api/providers').json()['h3'], '未配置')
        core = self.core()
        key = legacy + '_enabled'
        core.db.execute('INSERT INTO system_config(key,value) VALUES (?,?)', (key, 'false'))
        core.db.commit()
        self.assertNotIn(key, self.client.get('/api/admin/config').json())
        self.assertEqual(self.client.post('/api/admin/config', json={'key': key, 'value': 'true'}).status_code, 400)
        self.assertEqual(core.db.execute('SELECT value FROM system_config WHERE key=?', (key,)).fetchone()[0], 'false')
        self.assertEqual(self.client.get('/api/providers').json(), before)

    def test_admin_has_only_one_video_provider_with_two_models(self):
        providers = self.client.get('/api/admin/providers').json()
        self.assertEqual([row['name'] for row in providers], ['Darl LLM', 'Darl Image', 'Darl H3'])
        video = providers[-1]
        self.assertEqual(video['base_url'], 'https://api.darl.cn')
        self.assertEqual([row['id'] for row in video['execution_models']], [LOCAL_H3_MODEL, CLOUD_H3_MODEL])

    def make_due(self, job):
        core = self.core()
        core.db.execute("UPDATE job_runtime SET next_poll_at='2000-01-01T00:00:00+00:00' WHERE job_id=?", (job['id'],))
        core.db.commit()

    def test_runtime_polls_cloud_through_darl_when_self_hosted_is_offline(self):
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            response = self.submit()
            job = response.json()['job']
            self.make_due(job)
            factory = Mock()
            factory.return_value.poll.return_value = {'id': 'TEST-ONLY-task', 'status': 'queued'}
            worker = JobWorker(self.path, self.media, adapter_factory=factory)
            worker.tick()
        factory.return_value.poll.assert_called_once_with('TEST-ONLY-task')
        self.assertEqual(self.core().job(job['id'])['snapshot'], job['snapshot'])

    def test_runtime_does_not_poll_or_switch_frozen_local_model_when_offline(self):
        job = self.submit().json()['job']
        self.make_due(job)
        factory = Mock()
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}):
            JobWorker(self.path, self.media, adapter_factory=factory).tick()
        factory.assert_not_called()
        self.assertEqual(self.core().job(job['id']), job)

    def test_runtime_does_not_resume_or_poll_legacy_tasks(self):
        job = self.legacy_job(status='running')
        core = self.core()
        provider = job['metadata']['provider']
        core.db.execute("INSERT INTO job_runtime(job_id,provider,provider_task_id,next_poll_at) VALUES (?,?,?,'2000-01-01T00:00:00+00:00')",
                        (job['id'], provider, 'TEST-ONLY-old-task'))
        core.db.commit()
        before = dict(core.db.execute('SELECT * FROM job_runtime WHERE job_id=?', (job['id'],)).fetchone())
        factory = Mock()
        worker = JobWorker(self.path, self.media, adapter_factory=factory)
        worker.recover()
        worker.tick()
        factory.assert_not_called()
        self.assertEqual(core.job(job['id']), job)
        self.assertEqual(dict(core.db.execute('SELECT * FROM job_runtime WHERE job_id=?', (job['id'],)).fetchone()), before)
        self.assertEqual(core.db.execute('SELECT COUNT(*) FROM takes').fetchone()[0], 0)

    def test_cli_new_execution_uses_same_cloud_route_and_snapshot(self):
        self.adapter.build_request.side_effect = DarlH3Adapter(key='TEST-ONLY').build_request
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}), patch('scripts.h3_slice.core_open', return_value=self.core()), redirect_stdout(io.StringIO()):
            submit_one('A', self.adapter)
        task = self.adapter.submit.call_args.args[0]
        self.assertEqual(task['execution_model'], CLOUD_H3_MODEL)
        self.assertEqual(task['provider'], 'darl')
        core = self.core()
        job = core.job(core.db.execute('SELECT id FROM jobs').fetchone()[0])
        self.assertEqual(job['snapshot']['task'], task)
        self.assertEqual(job['snapshot']['cost_estimate']['execution_model'], CLOUD_H3_MODEL)

    def test_cli_retry_reuses_original_task_instead_of_recompiling_latest_brief(self):
        original = self.fail_job()
        core = self.core()
        brief = core.get('brief', 'brief:A')
        revised = core.save_brief('A', {**brief['payload'], 'purpose': 'TEST ONLY changed latest Brief'})
        self.adapter.build_request.side_effect = DarlH3Adapter(key='TEST-ONLY').build_request
        with patch('scripts.h3_slice.core_open', return_value=core), patch('film_core.core.Core.compile_h3', side_effect=AssertionError('retry must reuse original task')), redirect_stdout(io.StringIO()):
            submit_one('A', self.adapter, technical_retry_of=original['id'], backend_repaired=True)
        self.assertEqual(self.adapter.submit.call_args.args[0], original['snapshot']['task'])
        core = self.core()
        self.assertEqual(core.get('brief', 'brief:A'), revised)
        retry = core.job(core.db.execute('SELECT id FROM jobs WHERE id!=?', (original['id'],)).fetchone()[0])
        self.assertEqual(retry['task_id'], original['task_id'])
        self.assertEqual(retry['snapshot']['task'], original['snapshot']['task'])

    def test_cli_does_not_query_legacy_provider_task(self):
        job = self.legacy_job(status='running')
        with patch('scripts.h3_slice.core_open', return_value=self.core()), self.assertRaisesRegex(DomainError, 'LEGACY_PROVIDER_UNSUPPORTED'):
            sync_one(job['id'], self.adapter)
        self.adapter.poll.assert_not_called()
        self.assertEqual(self.core().job(job['id']), job)

    def test_cli_local_retry_is_rejected_instead_of_switching_to_cloud(self):
        original = self.fail_job()
        self.adapter.submit.reset_mock()
        with patch.dict(os.environ, {'H3_SERVER_ON': '0'}), patch('scripts.h3_slice.core_open', return_value=self.core()), self.assertRaisesRegex(DomainError, 'EXECUTION_MODEL_UNAVAILABLE'):
            submit_one('A', self.adapter, technical_retry_of=original['id'], backend_repaired=True)
        self.adapter.submit.assert_not_called()
        self.assertEqual(self.core().job(original['id']), original)

    def test_current_tree_contains_no_direct_provider_implementation_or_ui(self):
        root = Path(__file__).resolve().parents[1]
        legacy = CLOUD_H3_MODEL.partition('-')[0]
        paths = [root / 'README.md']
        for directory in ('apps/api', 'apps/web/src', 'apps/web/tests', 'film_core', 'tests', 'scripts', 'docs'):
            paths.extend(path for path in (root / directory).rglob('*') if path.suffix in {'.py', '.ts', '.tsx', '.md', '.txt'})
        for path in paths:
            with self.subTest(path=str(path.relative_to(root))):
                text = path.read_text().lower().replace(CLOUD_H3_MODEL, '')
                self.assertNotIn(legacy, text)


if __name__ == '__main__':
    unittest.main()
