"""Bind campus SSH to its VPN interface without changing host routing."""

import ipaddress
import os
import re
import subprocess
import sys


HOST = '10.123.4.30'


def select_interface(route, interfaces):
    preferred = next((line.split(':', 1)[1].strip() for line in route.splitlines()
                      if line.strip().startswith('interface:')), None)
    candidates = []
    interface = None
    for line in interfaces.splitlines():
        match = re.match(r'^(utun\d+):', line)
        if line and not line[0].isspace():
            interface = match.group(1) if match and '<UP,' in line else None
        fields = line.split()
        if interface and len(fields) > 1 and fields[0] == 'inet':
            try:address = ipaddress.IPv4Address(fields[1])
            except ipaddress.AddressValueError:continue
            if address in ipaddress.IPv4Network('10.0.0.0/8'):
                candidates.append((interface, str(address)))
    candidates = list(dict.fromkeys(candidates))
    routed = [item for item in candidates if item[0] == preferred]
    if len(routed) == 1:
        return routed[0]
    if len(candidates) == 1:
        return candidates[0]
    raise ValueError('Campus VPN interface unavailable or ambiguous; reconnect EasyConnect')


def main(argv=None):
    args = sys.argv[1:] if argv is None else argv
    if args != [HOST, '22']:
        raise ValueError('Unsupported campus SSH destination')
    route = subprocess.run(['/sbin/route', '-n', 'get', HOST], capture_output=True,
                           text=True, timeout=5, check=False)
    interfaces = subprocess.check_output(['/sbin/ifconfig', '-a'], text=True, timeout=5)
    interface, source = select_interface(route.stdout, interfaces)
    os.execv('/usr/bin/nc', ['nc', '-b', interface, '-s', source, '-G', '10', HOST, '22'])


if __name__ == '__main__':
    try:main()
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(str(error) if isinstance(error, ValueError) else 'Campus VPN inspection failed', file=sys.stderr)
        raise SystemExit(1)
