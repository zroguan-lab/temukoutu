"""Create the Windows desktop entry after installation; other systems are untouched."""
import json
import subprocess
import sys
from pathlib import Path


def post_install(root=None, *, platform=None, run=subprocess.run):
    if (platform or sys.platform) != "win32":
        return {"status": "skipped", "reason": "not_windows"}
    root = Path(root or Path(__file__).resolve().parents[1]).resolve()
    for relative in ["start.bat", "scripts/create_shortcut.ps1", ".venv/Scripts/python.exe", "frontend/dist/index.html"]:
        if not (root / relative).is_file():
            raise ValueError("请先完成依赖安装和前端构建，再创建桌面入口")
    result = run(["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                  str(root / "scripts/create_shortcut.ps1"), "-ProjectRoot", str(root)],
                 capture_output=True, text=True, encoding="utf-8", errors="replace", check=True)
    return json.loads(result.stdout.strip())


if __name__ == "__main__":
    try:
        print(json.dumps(post_install(), ensure_ascii=False))
    except (ValueError, OSError, subprocess.SubprocessError):
        print("依赖可能已安装，但桌面入口创建失败；请重新运行 scripts/post_install.py", file=sys.stderr)
        raise SystemExit(1)
