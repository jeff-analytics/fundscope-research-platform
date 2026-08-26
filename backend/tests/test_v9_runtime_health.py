from unittest.mock import patch

import main


def test_process_health_is_lightweight():
    with patch.object(main.services, "health", side_effect=RuntimeError("heavy data health must not run")):
        resp = main.health()
    assert resp.status_code == 200
    body = resp.body.decode("utf-8")
    assert '"ok":true' in body
    assert '"version":"9.2.2"' in body
    assert '"service":"api"' in body
