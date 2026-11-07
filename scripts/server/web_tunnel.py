"""Maintain a permission-restricted reverse SSH socket to this Mac's Clash."""

import argparse
import fcntl
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import socket
import stat
import subprocess
import sys

SERVER='zhoujunye@10.123.4.30'
REMOTE_SOCKET='/home/zhoujunye/.cache/mas-web/clash.sock'
LABEL='io.mas.web-tunnel'
STATE=Path.home()/'.cache/mas-web'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
SSH='/usr/bin/ssh'

PREPARE = '''
import os,socket,stat,sys
from pathlib import Path
p=Path(sys.argv[1]); root=Path.home()/'.cache/mas-web'
if p.parent!=root or p.name!='clash.sock':raise ValueError('Unexpected tunnel path')
root.mkdir(mode=0o700,exist_ok=True)
s=root.lstat()
if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700:
 raise ValueError('Tunnel directory must be owned and mode 0700')
try:s=p.lstat()
except FileNotFoundError:s=None
if s:
 if not stat.S_ISSOCK(s.st_mode) or s.st_uid!=os.getuid():raise ValueError('Unowned or non-socket endpoint')
 c=socket.socket(socket.AF_UNIX);c.settimeout(1)
 try:c.connect(str(p))
 except ConnectionRefusedError:p.unlink()
 else:raise ValueError('Tunnel endpoint is already live')
 finally:c.close()
'''


def local_state():
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    value=STATE.lstat()
    if not stat.S_ISDIR(value.st_mode) or value.st_uid!=os.getuid() or stat.S_IMODE(value.st_mode)!=0o700:
        raise ValueError('Local tunnel directory must be owned and mode 0700')


def ssh_command():
    return [SSH,'-NT','-M','-S',str(STATE/'control'),'-o','BatchMode=yes',
        '-o','ConnectTimeout=10','-o','ExitOnForwardFailure=yes',
        '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
        '-o','StreamLocalBindMask=0177','-R',REMOTE_SOCKET+':127.0.0.1:7897',SERVER]


def serve():
    local_state()
    with (STATE/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with socket.create_connection(('127.0.0.1',7897),timeout=2):pass
        subprocess.run([SSH,'-o','BatchMode=yes','-o','ConnectTimeout=10',SERVER,
            'python3 - '+shlex.quote(REMOTE_SOCKET)],input=PREPARE,text=True,check=True,timeout=20)
        child=subprocess.Popen(ssh_command())
        def terminate(number,frame):
            child.terminate()
            raise SystemExit(0)
        old=signal.signal(signal.SIGTERM,terminate)
        try:return child.wait()
        finally:
            signal.signal(signal.SIGTERM,old)
            if child.poll() is None:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()


def launch_args():
    return [sys.executable,str(STATE/'runner.py'),'serve']


def check_plist():
    if PLIST.is_symlink():raise ValueError('Refuse symlinked launch agent')
    if PLIST.exists():
        with PLIST.open('rb') as stream:current=plistlib.load(stream)
        previous=[sys.executable,str(Path(__file__).resolve()),'serve']
        if current.get('Label')!=LABEL or current.get('ProgramArguments') not in (launch_args(),previous):
            raise ValueError('Existing launch agent belongs to another source location')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','status','stop','serve'))
    args=parser.parse_args(argv)
    if args.action=='serve':return serve()
    if sys.platform!='darwin':raise ValueError('Install/status/stop run on the local Mac')
    local_state();check_plist()
    service=f'gui/{os.getuid()}/{LABEL}'
    if args.action=='install':
        if PLIST.exists():subprocess.run(['launchctl','bootout',service],capture_output=True,timeout=10)
        runner=STATE/'runner.py'
        if runner.is_symlink():raise ValueError('Refuse symlinked installed runner')
        shutil.copyfile(Path(__file__).resolve(),runner);runner.chmod(0o700)
        PLIST.parent.mkdir(parents=True,exist_ok=True)
        temporary=PLIST.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            plistlib.dump(dict(Label=LABEL,ProgramArguments=launch_args(),RunAtLoad=True,KeepAlive=True,
                ThrottleInterval=15,StandardOutPath=str(STATE/'stdout.log'),
                StandardErrorPath=str(STATE/'stderr.log')),stream)
        temporary.chmod(0o600);temporary.replace(PLIST)
        subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(PLIST)],check=True,timeout=15)
    elif args.action=='stop':
        subprocess.run(['launchctl','bootout',service],check=True,timeout=15)
        print('Stopped tunnel for this login session; installed agent remains for next login')
        return 0
    loaded=subprocess.run(['launchctl','print',service],capture_output=True,timeout=10).returncode==0
    master=subprocess.run([SSH,'-S',str(STATE/'control'),'-O','check',SERVER],capture_output=True,timeout=10).returncode==0
    print(json.dumps(dict(installed=PLIST.exists(),loaded=loaded,ssh_master_alive=master,
                         local_proxy='127.0.0.1:7897',remote_socket=REMOTE_SOCKET)))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        raise SystemExit(1)
