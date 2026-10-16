import json
import subprocess
from pathlib import Path

import pytest
from scripts.post_install import post_install


@pytest.mark.parametrize('platform',['darwin','linux'])
def test_non_windows_never_runs_commands_or_writes_desktop(tmp_path,platform):
    def forbidden(*args,**kwargs): raise AssertionError('No desktop or COM operations off Windows')
    assert post_install(tmp_path,platform=platform,run=forbidden)=={'status':'skipped','reason':'not_windows'}
    assert not list(tmp_path.iterdir())


def test_windows_shortcut_command_preserves_unicode_and_spaces(tmp_path):
    root=tmp_path/'中文 项目 with spaces'
    for name in ['start.bat','scripts/create_shortcut.ps1','.venv/Scripts/python.exe','frontend/dist/index.html']:
        target=root/name;target.parent.mkdir(parents=True,exist_ok=True);target.touch()
    calls=[]
    def run(args,**kwargs):
        calls.append((args,kwargs))
        return subprocess.CompletedProcess(args,0,stdout=json.dumps({'status':'created','path':'desktop/Print Extractor AI.lnk'}))
    assert post_install(root,platform='win32',run=run)['status']=='created'
    args,kwargs=calls[0]
    assert args[-1]==str(root.resolve()) and args[-2]=='-ProjectRoot'
    assert str(root/'scripts/create_shortcut.ps1') in args and 'shell' not in kwargs


def test_missing_installation_cannot_create_a_broken_entry(tmp_path):
    with pytest.raises(ValueError,match='完成依赖安装'): post_install(tmp_path,platform='win32')


def test_windows_scripts_have_platform_guard_local_target_and_startup_mutex():
    root=Path(__file__).resolve().parents[2]
    shortcut=(root/'scripts/create_shortcut.ps1').read_text()
    assert shortcut.index("$env:OS -ne 'Windows_NT'")<shortcut.index('New-Object -ComObject')
    assert "$shortcut.TargetPath = $target" in shortcut and "$shortcut.WorkingDirectory = $root" in shortcut
    assert 'DesktopDirectory' in shortcut and "'start.bat'" in shortcut
    startup=(root/'scripts/start.ps1').read_text()
    assert startup.index('WaitOne(30000)')<startup.index('if (Test-App)')
    assert 'ReleaseMutex()' in startup and 'Application startup is already in progress' in startup
    assert 'Port 7860 is occupied by another application' in startup
