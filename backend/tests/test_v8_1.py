import tempfile
import threading
import time
from pathlib import Path

import pytest

from app import collection_policy, db, providers, tasks


def test_collection_profiles_are_endpoint_specific():
    assert collection_policy.workers_for('holdings','safe') == 2
    assert collection_policy.workers_for('holdings','standard') == 4
    assert collection_policy.workers_for('holdings','fast') == 6
    assert collection_policy.workers_for('security_master','standard') == 8
    assert collection_policy.workers_for('market','standard') == 3


def test_eastmoney_514_is_rate_limit():
    err = "API Error: FundArchivesDatas request failed: 514 Server Error: Frequency Capped"
    assert providers._is_rate_limited(err) is True
    assert providers._is_rate_limited('429 Too Many Requests') is True
    assert providers._is_rate_limited("KeyError('序号')") is False


def test_task_pause_resume_and_cancel_flags():
    tmp=tempfile.TemporaryDirectory();old=db.DB_PATH
    try:
        db.DB_PATH=Path(tmp.name)/'task.db';db.ensure_schema()
        db.create_task_run('pausecase','holdings',0)
        db.update_task_run('pausecase',status='running')
        ctx=tasks.TaskContext('pausecase')
        assert db.request_pause('pausecase') is True
        finished=[]
        def waiter():
            ctx.checkpoint();finished.append(True)
        t=threading.Thread(target=waiter,daemon=True);t.start()
        deadline=time.time()+2
        while time.time()<deadline:
            row=db.get_task_run('pausecase')
            if row and row['status']=='paused':break
            time.sleep(.03)
        assert db.get_task_run('pausecase')['status']=='paused'
        assert not finished
        assert db.request_resume('pausecase') is True
        t.join(timeout=2)
        assert finished == [True]

        db.create_task_run('cancelcase','holdings',0)
        db.update_task_run('cancelcase',status='running')
        db.request_cancel('cancelcase')
        with pytest.raises(tasks.TaskCancelled):
            tasks.TaskContext('cancelcase').checkpoint()
    finally:
        db.DB_PATH=old;tmp.cleanup()


def test_rate_limit_arms_shared_cooldown():
    th=providers.AdaptiveThrottle(4,'holdings')
    before=time.monotonic()
    limited=th.feedback(False,'514 Server Error: Frequency Capped')
    assert limited is True
    assert th.cooldown_until >= before + 19
    assert th.delay >= .25
