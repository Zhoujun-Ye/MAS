"""Campus SSH interface selection without real network or route changes."""

from types import SimpleNamespace

import pytest

from scripts.server import vpn_connect


VPN = 'utun4: flags=8051<UP,POINTOPOINT,RUNNING> mtu 1400\n\tinet 10.21.8.16 --> 10.21.8.16 netmask 0xff000000\n'
CLASH = 'utun1024: flags=8051<UP,POINTOPOINT,RUNNING> mtu 1500\n\tinet 198.18.0.1 --> 198.18.0.1 netmask 0xfffffffc\n'


@pytest.mark.parametrize('route', ['interface: utun4','interface: utun1024','interface: en0',''])
def test_unique_campus_vpn_survives_clash_route_override(route):
    assert vpn_connect.select_interface(route, VPN+CLASH)==('utun4','10.21.8.16')


def test_multiple_vpns_require_an_unambiguous_routed_interface():
    other=VPN.replace('utun4','utun5').replace('10.21.8.16','10.22.1.2')
    assert vpn_connect.select_interface('interface: utun5', VPN+other)==('utun5','10.22.1.2')
    with pytest.raises(ValueError, match='ambiguous'):
        vpn_connect.select_interface('interface: utun1024',VPN+other+CLASH)


@pytest.mark.parametrize('interfaces', [CLASH, VPN.replace('<UP,','<'), VPN.replace('utun4','en0'), ''])
def test_missing_or_inactive_campus_vpn_fails_closed(interfaces):
    with pytest.raises(ValueError):vpn_connect.select_interface('',interfaces)


def test_proxy_binds_interface_and_source_without_modifying_routes(monkeypatch):
    calls=[]
    monkeypatch.setattr(vpn_connect.subprocess,'run',lambda command,**kw:
        calls.append(command) or SimpleNamespace(stdout='interface: utun1024'))
    monkeypatch.setattr(vpn_connect.subprocess,'check_output',lambda command,**kw:
        calls.append(command) or VPN+CLASH)
    monkeypatch.setattr(vpn_connect.os,'execv',lambda program,args:calls.append((program,args)))
    vpn_connect.main([vpn_connect.HOST,'22'])
    assert calls==[['/sbin/route','-n','get',vpn_connect.HOST],['/sbin/ifconfig','-a'],
        ('/usr/bin/nc',['nc','-b','utun4','-s','10.21.8.16','-G','10',vpn_connect.HOST,'22'])]


@pytest.mark.parametrize('args', [[],['example.org','22'],[vpn_connect.HOST,'80']])
def test_proxy_rejects_other_destinations_before_inspection(args,monkeypatch):
    monkeypatch.setattr(vpn_connect.subprocess,'run',lambda *a,**kw:pytest.fail('No inspection'))
    with pytest.raises(ValueError):vpn_connect.main(args)
