import json
import logging
import queue
import threading
import time
import uuid
from datetime import datetime
from . import db, audit

logger=logging.getLogger("fundscope.tasks")


class TaskCancelled(Exception):
    pass


class TaskContext:
    def __init__(self, task_id):
        self.task_id = task_id
        self._lock = threading.Lock()
        self._last_state = None
        self._last_message = None
        self._last_write = 0.0

    def cancelled(self):
        return db.is_cancel_requested(self.task_id)

    def paused(self):
        return db.is_pause_requested(self.task_id)

    def _state(self, status, message='', force=False):
        now_mono = time.monotonic()
        with self._lock:
            changed = status != self._last_state or message != self._last_message
            if not force and not changed and now_mono - self._last_write < 1.0:
                return
            db.update_task_run(self.task_id, status=status, message=message)
            self._last_state = status
            self._last_message = message
            self._last_write = now_mono

    def checkpoint(self):
        if self.cancelled():
            raise TaskCancelled()
        was_paused = False
        while self.paused():
            was_paused = True
            self._state('paused', '已暂停')
            time.sleep(0.25)
            if self.cancelled():
                raise TaskCancelled()
        if was_paused:
            self._state('running', '进行中', force=True)
        if self.cancelled():
            raise TaskCancelled()

    def runtime_state(self, status, message=''):
        self.checkpoint()
        self._state(status, message)

    def progress(self, current, total, message=''):
        self.checkpoint()
        pct = 0 if not total else round(max(0, min(1, float(current) / float(total))) * 100, 1)
        db.update_task_run(
            self.task_id,
            status='running',
            progress=pct,
            current=int(float(current)),
            total=int(float(total)),
            message=message or '进行中',
        )
        with self._lock:
            self._last_state = 'running'
            self._last_message = message or '进行中'
            self._last_write = time.monotonic()


_QUEUE = queue.Queue()
_STARTED = False
_LOCK = threading.Lock()


def _runner_loop():
    while True:
        task_id, task_type, fn = _QUEUE.get()
        try:
            ctx = TaskContext(task_id)
            db.update_task_run(
                task_id,
                status='running',
                queue_position=0,
                started_at=datetime.now().isoformat(timespec='seconds'),
                message='进行中',
            )
            ctx.checkpoint()
            result = fn(ctx)
            ctx.checkpoint()
            db.update_task_run(
                task_id,
                status='success',
                progress=100,
                message='完成',
                finished_at=datetime.now().isoformat(timespec='seconds'),
                result_json=json.dumps(result, ensure_ascii=False, default=str),
            )
            audit.log('task.success','task',task_id,{'task_type':task_type})
            if task_type in {'holdings','market','incremental'}:
                try:
                    from . import workspace
                    workspace.evaluate_monitors('local')
                except Exception as exc:
                    logger.warning('monitor_evaluation_failed task_id=%s error=%s',task_id,exc)
        except TaskCancelled:
            audit.log('task.cancelled','task',task_id,{'task_type':task_type})
            db.update_task_run(
                task_id,
                status='cancelled',
                message='已取消',
                finished_at=datetime.now().isoformat(timespec='seconds'),
            )
        except Exception as exc:
            audit.log('task.error','task',task_id,{'task_type':task_type,'error':repr(exc)[:500]})
            db.update_task_run(
                task_id,
                status='error',
                message='失败',
                error=repr(exc)[:3000],
                finished_at=datetime.now().isoformat(timespec='seconds'),
            )
        finally:
            _QUEUE.task_done()
            _refresh_queue_positions()


def ensure_workers(n=1):
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        for i in range(max(1, int(n))):
            threading.Thread(
                target=_runner_loop,
                daemon=True,
                name=f'fundscope-task-worker-{i + 1}',
            ).start()
        _STARTED = True


def _refresh_queue_positions():
    try:
        queued = db.read_sql("SELECT task_id FROM task_runs WHERE status='queued' ORDER BY created_at")
        for i, tid in enumerate(queued.task_id.astype(str).tolist(), 1):
            db.update_task_run(tid, queue_position=i)
    except Exception as exc:
        logger.warning('task_queue_reindex_failed error=%s',exc)


def start_task(task_type, fn):
    ensure_workers()
    task_id = uuid.uuid4().hex[:12]
    pos = _QUEUE.qsize() + 1
    db.create_task_run(task_id, task_type, pos)
    audit.log('task.start','task',task_id,{'task_type':task_type,'queue_position':pos})
    _QUEUE.put((task_id, task_type, fn))
    _refresh_queue_positions()
    return db.get_task_run(task_id)
