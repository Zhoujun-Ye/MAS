"""Maintain a permission-restricted reverse SSH socket to this Mac's Clash."""

import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import plistlib
import shlex
import shutil
import signal
import select
import socket
import stat
import subprocess
import sys
import time

SERVER='zhoujunye@10.123.4.30'
REMOTE_SOCKET='/home/zhoujunye/.cache/mas-web/clash.sock'
REMOTE_DNS_SOCKET='/home/zhoujunye/.cache/mas-web/dns.sock'
LABEL='io.mas.web-tunnel'
STATE=Path.home()/'.cache/mas-web'
PLIST=Path.home()/'Library/LaunchAgents'/f'{LABEL}.plist'
SSH='/usr/bin/ssh'

# The remote session must expire even when this Mac sleeps or disappears.
WATCHDOG = '''
import os,select,sys
timeout=float(sys.argv[1])
while select.select([0],[],[],timeout)[0]:
 if not os.read(0,4096):break
 os.write(1,b'heartbeat\\n')
'''

PREPARE = '''
import os,socket,stat,sys
from pathlib import Path
paths=[Path(value) for value in sys.argv[1:]]; root=Path.home()/'.cache/mas-web'
if not paths or len(set(paths))!=len(paths) or any(p.parent!=root or p.name not in {'clash.sock','dns.sock'} for p in paths):raise ValueError('Unexpected tunnel path')
root.mkdir(mode=0o700,exist_ok=True)
s=root.lstat()
if not stat.S_ISDIR(s.st_mode) or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=0o700:
 raise ValueError('Tunnel directory must be owned and mode 0700')
stale=[]
for p in paths:
 try:s=p.lstat()
 except FileNotFoundError:s=None
 if s:
  if not stat.S_ISSOCK(s.st_mode) or s.st_uid!=os.getuid():raise ValueError('Unowned or non-socket endpoint')
  c=socket.socket(socket.AF_UNIX);c.settimeout(1)
  try:c.connect(str(p))
  except ConnectionRefusedError:stale.append(p)
  else:raise ValueError('Tunnel endpoint is already live')
  finally:c.close()
for p in stale:p.unlink()
'''


def local_state():
    STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
    value=STATE.lstat()
    if not stat.S_ISDIR(value.st_mode) or value.st_uid!=os.getuid() or stat.S_IMODE(value.st_mode)!=0o700:
        raise ValueError('Local tunnel directory must be owned and mode 0700')


def ssh_command():
    return [SSH,'-T','-M','-S',str(STATE/'control'),'-o','BatchMode=yes',
        '-o','ConnectTimeout=10','-o','ExitOnForwardFailure=yes',
        '-o','ControlPersist=no',
        '-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3',
        '-o','StreamLocalBindMask=0177','-R',REMOTE_SOCKET+':127.0.0.1:7897',
        '-R',REMOTE_DNS_SOCKET+':'+str(STATE/'dns.sock'),SERVER,
        'python3 -c '+shlex.quote(WATCHDOG)+' 60']


def serve():
    local_state()
    helper = (STATE/'dns_transport.py' if Path(__file__).name=='runner.py' else
              Path(__file__).resolve().parents[2]/'harness/runtime_support/dns_transport.py')
    spec=importlib.util.spec_from_file_location('mas_dns_transport',helper)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with module.bridge(STATE/'dns.sock'):
        return serve_ssh()


def lifecycle(event, **fields):
    print(json.dumps(dict(time=datetime.now(timezone.utc).isoformat(),event=event,**fields)),flush=True)


def heartbeat(child, timeout=10):
    """An alive multiplexing master does not establish a live primary session."""
    child.stdin.write(b'\n');child.stdin.flush()
    if not select.select([child.stdout],[],[],timeout)[0]:
        raise TimeoutError('Tunnel heartbeat acknowledgment timed out')
    if os.read(child.stdout.fileno(),64)!=b'heartbeat\n':
        raise ConnectionError('Tunnel heartbeat session closed')


def stop_child(child):
    if child.poll() is None:
        child.terminate()
        try:child.wait(timeout=2)
        except subprocess.TimeoutExpired:child.kill();child.wait(timeout=2)


def serve_ssh():
    local_state()
    with (STATE/'owner.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with socket.create_connection(('127.0.0.1',7897),timeout=2):pass
        subprocess.run([SSH,'-o','BatchMode=yes','-o','ConnectTimeout=10',SERVER,
            'python3 - '+shlex.quote(REMOTE_SOCKET)+' '+shlex.quote(REMOTE_DNS_SOCKET)],input=PREPARE,text=True,check=True,timeout=20)
        child=subprocess.Popen(ssh_command(),stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        lifecycle('ssh_started',pid=child.pid)
        def terminate(number,frame):
            child.terminate()
            raise SystemExit(0)
        old=signal.signal(signal.SIGTERM,terminate)
        try:
            first=True
            while child.poll() is None:
                try:
                    heartbeat(child,timeout=20 if first else 10)
                except OSError:
                    lifecycle('heartbeat_failed')
                    return 1
                if first:
                    lifecycle('heartbeat_ready')
                    first=False
                try:return child.wait(timeout=15)
                except subprocess.TimeoutExpired:pass
            return child.returncode
        finally:
            signal.signal(signal.SIGTERM,old)
            stop_child(child)
            lifecycle('ssh_stopped',returncode=child.returncode)
            try:child.stdin.close()
            except BrokenPipeError:pass
            child.stdout.close()


def launch_args():
    return [sys.executable,str(STATE/'runner.py'),'serve']


def check_plist():
    if PLIST.is_symlink():raise ValueError('Refuse symlinked launch agent')
    if PLIST.exists():
        with PLIST.open('rb') as stream:current=plistlib.load(stream)
        previous=[sys.executable,str(Path(__file__).resolve()),'serve']
        if current.get('Label')!=LABEL or current.get('ProgramArguments') not in (launch_args(),previous):
            raise ValueError('Existing launch agent belongs to another source location')


def bootstrap_service(service):
    # launchd can briefly reject bootstrap while a successful bootout finishes.
    deadline=time.monotonic()+10
    attempts=0
    while True:
        attempts+=1
        result=subprocess.run(['launchctl','bootstrap',f'gui/{os.getuid()}',str(PLIST)],
                              capture_output=True,timeout=15)
        if result.returncode==0:return attempts
        if (result.returncode!=5 or time.monotonic()>=deadline
                or subprocess.run(['launchctl','print',service],capture_output=True,timeout=10).returncode==0):
            result.check_returncode()
        time.sleep(0.2)


def unload_service(service):
    def loaded():
        return subprocess.run(['launchctl','print',service],capture_output=True,timeout=2).returncode==0
    if not loaded():return
    result=subprocess.run(['launchctl','bootout',service],capture_output=True,timeout=10)
    deadline=time.monotonic()+10
    while loaded():
        if result.returncode:result.check_returncode()
        if time.monotonic()>=deadline:raise TimeoutError('Previous tunnel registration did not unload')
        time.sleep(0.2)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=('install','status','stop','serve'))
    args=parser.parse_args(argv)
    if args.action=='serve':return serve()
    if sys.platform!='darwin':raise ValueError('Install/status/stop run on the local Mac')
    local_state();check_plist()
    service=f'gui/{os.getuid()}/{LABEL}'
    bootstrap_attempts=None
    if args.action=='install':
        if PLIST.exists():unload_service(service)
        runner=STATE/'runner.py'
        if runner.is_symlink():raise ValueError('Refuse symlinked installed runner')
        helper=STATE/'vpn_connect.py'
        if helper.is_symlink():raise ValueError('Refuse symlinked VPN helper')
        shutil.copyfile(Path(__file__).with_name('vpn_connect.py'),helper);helper.chmod(0o700)
        dns=STATE/'dns_transport.py'
        if dns.is_symlink():raise ValueError('Refuse symlinked DNS bridge')
        shutil.copyfile(Path(__file__).resolve().parents[2]/'harness/runtime_support/dns_transport.py',dns);dns.chmod(0o700)
        shutil.copyfile(Path(__file__).resolve(),runner);runner.chmod(0o700)
        PLIST.parent.mkdir(parents=True,exist_ok=True)
        temporary=PLIST.with_suffix('.tmp')
        with temporary.open('wb') as stream:
            plistlib.dump(dict(Label=LABEL,ProgramArguments=launch_args(),RunAtLoad=True,KeepAlive=True,
                ThrottleInterval=15,StandardOutPath=str(STATE/'stdout.log'),
                StandardErrorPath=str(STATE/'stderr.log')),stream)
        temporary.chmod(0o600);temporary.replace(PLIST)
        bootstrap_attempts=bootstrap_service(service)
    elif args.action=='stop':
        subprocess.run(['launchctl','bootout',service],check=True,timeout=15)
        print('Stopped tunnel for this login session; installed agent remains for next login')
        return 0
    loaded=subprocess.run(['launchctl','print',service],capture_output=True,timeout=10).returncode==0
    master=subprocess.run([SSH,'-S',str(STATE/'control'),'-O','check',SERVER],capture_output=True,timeout=10).returncode==0
    print(json.dumps(dict(installed=PLIST.exists(),loaded=loaded,ssh_master_alive=master,
                         bootstrap_attempts=bootstrap_attempts,
                         local_proxy='127.0.0.1:7897',remote_socket=REMOTE_SOCKET,
                         remote_dns_socket=REMOTE_DNS_SOCKET)))
    return 0


if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as error:
        lifecycle('service_failed',error_type=type(error).__name__)
        print(type(error).__name__+': '+str(error),file=sys.stderr)
        raise SystemExit(1)
