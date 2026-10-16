"""User-owned local settings. Secrets never belong in task data or API responses."""
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path


class SettingsError(ValueError):
    pass


@dataclass(frozen=True)
class CloudSettings:
    enabled: bool = False
    api_key: str = field(default="", repr=False)
    workspace_id: str = ""

    def public(self):
        return {"enabled": self.enabled, "key_configured": bool(self.api_key),
                "workspace_id": self.workspace_id, "provider": "qwen-image"}


def user_config_path():
    override = os.environ.get("PRINT_EXTRACTOR_CONFIG_PATH")
    if override:
        path = Path(override)
        if not path.is_absolute():
            raise SettingsError("本地配置路径必须为绝对路径")
        return path
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "PrintExtractorAI" / "print-extractor.local.json"


def validate_settings(enabled, api_key, workspace_id=""):
    if (not isinstance(enabled, bool) or not isinstance(api_key, str)
            or not isinstance(workspace_id, str)):
        raise SettingsError("本地 AI 配置格式无效")
    key = api_key.strip()
    if len(key) > 4096 or (enabled and not key):
        raise SettingsError("请在本机输入有效的百炼 API Key")
    if workspace_id and not re.fullmatch(r"[A-Za-z0-9-]{1,80}", workspace_id):
        raise SettingsError("北京业务空间 ID 格式无效")
    return CloudSettings(enabled, key, workspace_id)


def read_settings(path):
    path = Path(path)
    if not path.exists():
        return CloudSettings()
    try:
        if sys.platform != "win32" and path.stat().st_mode & 0o077:
            raise SettingsError("本地 AI 配置权限过宽，请将文件权限设为仅本人可读写后重试")
        with path.open("rb") as source:
            data = source.read(65537)
        if len(data) > 65536:
            raise SettingsError("本地 AI 配置文件无效，请重新配置")
        payload = json.loads(data)
        if payload["version"] != 1 or payload["provider"] != "qwen-image":
            raise SettingsError("本地 AI 配置版本或服务商不受支持")
        return validate_settings(payload["enabled"], payload["api_key"], payload.get("workspace_id", ""))
    except SettingsError:
        raise
    except (OSError, ValueError, TypeError, KeyError):
        raise SettingsError("无法读取本地 AI 配置，请在设置中重新保存") from None


def runtime_settings(path):
    # Keep explicit process variables compatible; never discover other app keys.
    enabled = os.environ.get("PRINT_EXTRACTOR_CLOUD_ENABLED")
    if enabled == "0":
        return CloudSettings()
    key = os.environ.get("PRINT_EXTRACTOR_DASHSCOPE_API_KEY", "")
    if enabled == "1" and key:
        return validate_settings(True, key, os.environ.get("PRINT_EXTRACTOR_DASHSCOPE_WORKSPACE", ""))
    return read_settings(path)


def secure_windows_directory(path, run=subprocess.run):
    identity = run(["whoami", "/user", "/fo", "csv", "/nh"], capture_output=True,
                   text=True, encoding="utf-8", errors="replace", check=True)
    match = re.search(r"S-1-(?:\d+-)+\d+", identity.stdout)
    if not match:
        raise SettingsError("无法确认当前 Windows 用户，未保存 Key")
    run(["icacls", str(path), "/reset", "/Q"], capture_output=True, check=True)
    run(["icacls", str(path), "/inheritancelevel:r", "/grant:r",
         f"*{match.group()}:(OI)(CI)F", "*S-1-5-18:(OI)(CI)F", "/Q"],
        capture_output=True, check=True)


def write_settings(path, settings):
    path = Path(path)
    settings = validate_settings(settings.enabled, settings.api_key, settings.workspace_id)
    temp = None
    try:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        if sys.platform == "win32":
            secure_windows_directory(path.parent)
        else:
            path.parent.chmod(0o700)
        payload = {"version": 1, "provider": "qwen-image", "enabled": settings.enabled,
                   "api_key": settings.api_key, "workspace_id": settings.workspace_id}
        descriptor, name = tempfile.mkstemp(prefix=".settings-", dir=path.parent)
        temp = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    except SettingsError:
        raise
    except (OSError, subprocess.SubprocessError):
        raise SettingsError("无法安全保存本地 AI 配置，未启用新的 Key") from None
    finally:
        if temp is not None:
            temp.unlink(missing_ok=True)
