import pytest

from test_manual_download import _import_with_stubs


@pytest.fixture(scope="session")
def api_module():
    # Imported once per session: the module registers Prometheus metrics at import time.
    with pytest.MonkeyPatch.context() as mp:
        (api,) = _import_with_stubs(mp, "app.api.lidar")
    return api
