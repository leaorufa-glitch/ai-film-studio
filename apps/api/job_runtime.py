"""Restartable local H3 polling worker. Never resubmits an unknown provider task."""
from __future__ import annotations

import hashlib
import json
import os
import logging
import subprocess
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from film_core import Core, DomainError
from film_core.darl_h3 import DarlH3Adapter, ProviderError

log=logging.getLogger('film_studio.job_runtime')


def utcnow():
    return datetime.now(timezone.utc)


class JobWorker:
    def __init__(self, db_path, media_root, *, test_mode=False, adapter_factory=DarlH3Adapter,
                 poll_seconds=180, max_transient=3, max_download=2):
        self.db_path=str(db_path)
        self.media_root=Path(media_root)
        self.test_mode=test_mode
        self.adapter_factory=adapter_factory
        self.poll_seconds=max(0,poll_seconds) if test_mode else max(180,poll_seconds)
        self.max_transient=max(1,max_transient)
        self.max_download=max(1,max_download)
        self.worker_id=uuid.uuid4().hex
        self.stop_event=threading.Event()
        self.thread=None

    def _core(self):
        return Core(self.db_path,test_mode=self.test_mode)

    def _schedule(self, polls):
        seconds=min(900,self.poll_seconds * (2 ** min(polls,3)))
        return (utcnow()+timedelta(seconds=seconds)).isoformat()

    def recover(self):
        c=self._core()
        try:
            c.db.execute('DELETE FROM active_generation WHERE job_id NOT IN (SELECT id FROM jobs)')
            c.db.execute('DELETE FROM generation_requests WHERE job_id IS NULL AND created_at<datetime("now","-10 minutes")')
            jobs=[c.job(r['id']) for r in c.db.execute('SELECT id FROM jobs ORDER BY created_at')]
            for job in jobs:
                jid=job['id']
                if job['status']=='running':
                    provider_id=job['metadata'].get('provider_task_id')
                    if not provider_id:
                        c.job_event(jid,'failed',{'error_category':'TASK_ID_MISSING','message':'Provider task id was not recorded'})
                        c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
                        continue
                    event=c.db.execute('SELECT created_at FROM job_events WHERE job_id=? ORDER BY id DESC LIMIT 1',(jid,)).fetchone()
                    try:resume_at=max(utcnow(),datetime.fromisoformat(event['created_at'])+timedelta(seconds=self.poll_seconds))
                    except (TypeError,ValueError):resume_at=utcnow()+timedelta(seconds=self.poll_seconds)
                    c.db.execute('INSERT OR IGNORE INTO job_runtime(job_id,provider_task_id,next_poll_at,submitted_at) VALUES (?,?,?,?)',
                                 (jid,provider_id,resume_at.isoformat(),job['created_at']))
                elif job['status']=='queued':
                    c.job_event(jid,'failed',{'error_category':'SUBMISSION_UNKNOWN','message':'Submit was interrupted before task id; no automatic resubmit'})
                    c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
                elif job['status']=='succeeded':
                    self._finish_take(c,job)
                    c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
                elif job['status'] in {'failed','cancelled'}:
                    c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
            c.db.commit()
        finally:c.close()

    def _finish_take(self,c,job):
        jid=job['id'];media_id=job['metadata'].get('media_id')
        if not media_id or c.db.execute('SELECT 1 FROM takes WHERE job_id=?',(jid,)).fetchone():return
        media=c.media(media_id)
        if not Path(media['local_path']).is_file():return
        c.record_take('take-'+jid,jid,media['local_path'],{'recovered':True},media_id=media_id,
                      test_only=self.test_mode)

    def _claim(self,c,jid):
        now=utcnow().isoformat();lease=(utcnow()+timedelta(seconds=120)).isoformat()
        result=c.db.execute('UPDATE job_runtime SET lease_owner=?,lease_until=? WHERE job_id=? AND (lease_until IS NULL OR lease_until<?)',
                            (self.worker_id,lease,jid,now))
        c.db.commit()
        return result.rowcount==1

    def tick(self):
        c=self._core()
        try:
            due=c.db.execute('SELECT job_id FROM job_runtime WHERE next_poll_at<=? AND (lease_until IS NULL OR lease_until<?) ORDER BY next_poll_at LIMIT 3',
                             (utcnow().isoformat(),utcnow().isoformat())).fetchall()
            for row in due:
                jid=row['job_id']
                if self._claim(c,jid):
                    try:self._poll_one(c,jid)
                    finally:
                        c.db.execute('UPDATE job_runtime SET lease_owner=NULL,lease_until=NULL WHERE job_id=? AND lease_owner=?',(jid,self.worker_id))
                        c.db.commit()
        finally:c.close()

    def _fail(self,c,jid,category,message):
        job=c.job(jid)
        if job['status']=='running':c.job_event(jid,'failed',{'error_category':category,'message':message[:300]})
        c.db.execute('UPDATE job_runtime SET completed_at=?,last_error_category=?,last_error=?,next_poll_at=NULL WHERE job_id=?',
                     (utcnow().isoformat(),category,message[:300],jid))
        c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
        c.db.commit()
        log.warning(json.dumps({'event':'job_failed','job_id':jid,'category':category,'message':message[:120]},ensure_ascii=False))

    def _poll_one(self,c,jid):
        job=c.job(jid)
        if job['status']!='running':
            c.db.execute('UPDATE job_runtime SET next_poll_at=NULL WHERE job_id=?',(jid,));c.db.commit();return
        runtime=c.db.execute('SELECT * FROM job_runtime WHERE job_id=?',(jid,)).fetchone()
        enabled=c.db.execute("SELECT value FROM system_config WHERE key='h3_enabled'").fetchone()
        if not self.test_mode and (os.getenv('H3_SERVER_ON')!='1' or enabled and enabled['value']=='false'):
            c.db.execute('UPDATE job_runtime SET next_poll_at=?,last_error_category=? WHERE job_id=?',
                         (self._schedule(0),'PROVIDER_OFFLINE',jid));c.db.commit();return
        provider_id=runtime['provider_task_id']
        try:
            poll_started=time.monotonic()
            response=self.adapter_factory().poll(provider_id)
        except ProviderError as exc:
            count=runtime['transient_count']+1
            if exc.transient and count<=self.max_transient:
                c.db.execute('UPDATE job_runtime SET transient_count=?,next_poll_at=?,last_error_category=?,last_error=? WHERE job_id=?',
                             (count,self._schedule(count),exc.code,str(exc)[:300],jid));c.db.commit();return
            self._fail(c,jid,exc.code,'视频服务状态查询失败。');return
        c.db.execute('UPDATE job_runtime SET poll_latency_ms=?,last_polled_at=? WHERE job_id=?',
                     (round((time.monotonic()-poll_started)*1000),utcnow().isoformat(),jid))
        c.db.commit()
        if response['status']=='failed':
            self._fail(c,jid,'PROVIDER_FAILED','视频服务报告生成失败。');return
        if response['status']!='succeeded':
            polls=runtime['poll_count']+1
            c.db.execute('UPDATE job_runtime SET poll_count=?,transient_count=0,next_poll_at=?,last_polled_at=? WHERE job_id=?',
                         (polls,self._schedule(polls),utcnow().isoformat(),jid));c.db.commit();return
        self._download_success(c,job,response,runtime)

    def _download_success(self,c,job,response,runtime):
        jid=job['id'];task=job['snapshot']['task'];provider_id=runtime['provider_task_id']
        self.media_root.mkdir(parents=True,exist_ok=True)
        destination=self.media_root/('take-'+jid+'.mp4')
        try:
            download_started=time.monotonic()
            info=self.adapter_factory().download(provider_id,destination)
            target=Path(info['local_path']).resolve()
            if not target.is_file() or not target.is_relative_to(self.media_root.resolve()):
                raise DomainError('download outside managed media root')
            width=height=None
            try:
                probe=subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=width,height','-of','json',str(target)],
                                     capture_output=True,text=True,check=True,timeout=15)
                stream=json.loads(probe.stdout).get('streams',[{}])[0]
                width,height=stream.get('width'),stream.get('height')
            except (OSError,subprocess.SubprocessError,ValueError,IndexError):pass
            media_id='media-'+jid
            if not c.db.execute('SELECT 1 FROM media_records WHERE id=?',(media_id,)).fetchone():
                c.register_media(media_id,info['local_path'],info['sha256'],info['size_bytes'],info['mime'],
                                 duration=info.get('duration'),metadata={**info.get('metadata',{}),
                                 'kind':'video_take','source':'provider','provider':'darl',
                                 'project_id':self._project_for_clip(c,task['clip_id']),
                                 'clip_id':task['clip_id'],'job_id':jid,'width':width,'height':height,
                                 'test_only':self.test_mode})
            c.job_event(jid,'succeeded',{'provider_task_id':provider_id,'media_id':media_id,
                                        'provider_status':'succeeded'})
            c.record_take('take-'+jid,jid,str(target),{'provider_task_id':provider_id},
                          test_only=self.test_mode,media_id=media_id)
            c.db.execute('UPDATE job_runtime SET completed_at=?,next_poll_at=NULL,last_error_category=NULL,download_latency_ms=? WHERE job_id=?',
                         (utcnow().isoformat(),round((time.monotonic()-download_started)*1000),jid))
            c.db.execute('DELETE FROM active_generation WHERE job_id=?',(jid,))
            c.db.commit()
            log.info(json.dumps({'event':'job_succeeded','job_id':jid,'media_id':media_id},ensure_ascii=False))
        except (ProviderError,DomainError,OSError,subprocess.SubprocessError,ValueError) as exc:
            attempts=runtime['download_attempts']+1
            if attempts>=self.max_download:
                self._fail(c,jid,'MEDIA_DOWNLOAD_FAILED','视频已生成，但媒体下载或校验失败；任务记录已保留。')
            else:
                c.db.execute('UPDATE job_runtime SET download_attempts=?,next_poll_at=?,last_error_category=?,last_error=? WHERE job_id=?',
                             (attempts,self._schedule(attempts),'MEDIA_DOWNLOAD_RETRY',str(exc)[:300],jid))
                c.db.commit()

    @staticmethod
    def _project_for_clip(c,clip_id):
        clip=c.get('clip',clip_id)
        scene=c.get('scene',clip['payload']['scene_id'])
        episode=c.get('episode',scene['payload']['episode_id'])
        return episode['payload']['project_id']

    def start(self):
        if self.thread:return
        self.recover()
        def loop():
            while not self.stop_event.wait(10):
                try:self.tick()
                except Exception as exc:
                    log.error(json.dumps({'event':'worker_tick_error','category':type(exc).__name__},ensure_ascii=False))
        self.thread=threading.Thread(target=loop,name='h3-job-worker',daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        if self.thread:self.thread.join(timeout=2)
