from core.api.memme_admin_handler import MemMeAdminHandler


def test_admin_handler_uses_local_environment_when_server_config_omits_memory(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("MEMME_API_KEY", "test-key")
    monkeypatch.setenv("MEMME_QUEUE_PATH", str(tmp_path / "retry.sqlite3"))
    monkeypatch.delenv("MEMME_BASE_URL", raising=False)

    handler = MemMeAdminHandler({})

    assert handler.provider is not None
    assert handler.provider.use_memme is True
    assert handler.provider.base_url == "http://127.0.0.1:8080"
    assert handler.provider.queue_path == (tmp_path / "retry.sqlite3").resolve()


def test_admin_handler_stays_disabled_without_a_service_key(monkeypatch):
    monkeypatch.delenv("MEMME_API_KEY", raising=False)

    handler = MemMeAdminHandler({})

    assert handler.provider is None
