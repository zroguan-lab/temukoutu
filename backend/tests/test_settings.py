import json
import subprocess
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient

from backend.app.main import create_app
from backend.app import settings

FAKE_KEY = "fake-settings-secret-never-a-real-key"


def test_suite_has_no_real_model_network():
    with pytest.raises(AssertionError, match="mock/ASGI transport"):
        httpx.Client().get("https://example.invalid/no-request-will-be-sent")


@pytest.fixture(autouse=True)
def clean_runtime(monkeypatch):
    monkeypatch.delenv("PRINT_EXTRACTOR_CLOUD_ENABLED", raising=False)
    monkeypatch.delenv("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", raising=False)


def test_local_save_private_permissions_and_secret_repr(tmp_path):
    path = tmp_path / "owned" / "print-extractor.local.json"
    config = settings.CloudSettings(True, FAKE_KEY, "workspace-1")
    settings.write_settings(path, config)
    assert settings.read_settings(path) == config
    if settings.sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
        assert path.parent.stat().st_mode & 0o777 == 0o700
    assert FAKE_KEY not in repr(config) and FAKE_KEY not in json.dumps(config.public())
    assert not list(path.parent.glob(".settings-*"))
    assert subprocess.run(["git", "check-ignore", "--no-index", "print-extractor.local.json"], capture_output=True).returncode == 0


def test_save_then_restart_and_disable_without_key_echo(tmp_path, caplog):
    path = tmp_path / "config" / "print-extractor.local.json"
    def app(): return TestClient(create_app(tmp_path/"tasks", config_path=path), base_url="http://127.0.0.1:7860")
    with app() as c:
        assert not c.get("/api/settings").json()["key_configured"]
        response = c.put("/api/settings", json={"api_key": FAKE_KEY, "enabled": True})
        assert response.status_code == 200 and response.json()["key_configured"]
        assert FAKE_KEY not in response.text
        assert c.get("/api/providers").json()["cloud"]["enabled"]
    with app() as c:
        assert c.get("/api/settings").json()["enabled"]
        assert FAKE_KEY not in c.get("/api/settings").text
        assert c.put("/api/settings", json={"enabled":False}).status_code == 200
        assert not c.get("/api/providers").json()["cloud"]["enabled"]
        assert c.put("/api/settings", json={"enabled":True}).status_code == 200
    assert FAKE_KEY not in caplog.text


def test_validation_never_echoes_secret_and_bad_save_does_not_replace(tmp_path, caplog):
    path = tmp_path/"owned"/"print-extractor.local.json"
    c = TestClient(create_app(tmp_path/"tasks",config_path=path),base_url="http://127.0.0.1:7860")
    for body in [{"api_key":[FAKE_KEY]}, {"api_key":FAKE_KEY,"workspace_id":"https://evil.example"},
                 {"api_key":FAKE_KEY*200}, {"enabled":True}]:
        response=c.put("/api/settings",json=body)
        assert response.status_code==422 and FAKE_KEY not in response.text
    assert not path.exists() and FAKE_KEY not in caplog.text


def test_permissions_or_invalid_configuration_fall_back_to_local(tmp_path):
    path=tmp_path/"print-extractor.local.json"
    path.write_text('{"api_key":"'+FAKE_KEY+'"}');path.chmod(0o644)
    c=TestClient(create_app(tmp_path/"tasks",config_path=path),base_url="http://127.0.0.1:7860")
    response=c.get('/api/providers')
    assert not response.json()['cloud']['enabled'] and FAKE_KEY not in response.text
    assert c.get('/api/settings').json()['error']
    # User can replace a broken local configuration by entering a new key locally.
    assert c.put('/api/settings',json={'api_key':FAKE_KEY}).status_code==200
    if settings.sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600


@pytest.mark.parametrize('platform,variable,base',[('win32','LOCALAPPDATA','/profiles/AppData/Local'),('linux','XDG_CONFIG_HOME','/profiles/config')])
def test_platform_config_is_user_scoped(platform,variable,base,monkeypatch):
    monkeypatch.delenv('PRINT_EXTRACTOR_CONFIG_PATH',raising=False)
    monkeypatch.setattr(settings.sys,'platform',platform)
    monkeypatch.setenv(variable,base)
    assert settings.user_config_path()==Path(base)/'PrintExtractorAI'/'print-extractor.local.json'


def test_windows_acl_uses_current_sid_and_system_before_writing(tmp_path):
    calls=[]
    def run(args,**kwargs):
        calls.append(args)
        return subprocess.CompletedProcess(args,0,stdout='"test user","S-1-5-21-123-456-789-1001"')
    settings.secure_windows_directory(tmp_path,run)
    assert calls[1][2]=='/reset'
    assert '/inheritancelevel:r' in calls[2]
    assert '*S-1-5-21-123-456-789-1001:(OI)(CI)F' in calls[2]
    assert '*S-1-5-18:(OI)(CI)F' in calls[2]
    assert not any(FAKE_KEY in str(call) for call in calls)
