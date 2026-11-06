"""Harness container byte transport to a host Unix socket; no provider key."""

from pathlib import Path
import select
import socket
import socketserver


class Bridge(socketserver.BaseRequestHandler):
    def handle(self):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as upstream:
            upstream.connect("/host-gateway.sock")
            sockets = [self.request, upstream]
            while True:
                ready, _, _ = select.select(sockets, [], [], 200)
                if not ready:
                    return
                for source in ready:
                    data = source.recv(65536)
                    if not data:
                        return
                    target = upstream if source is self.request else self.request
                    target.sendall(data)


if __name__ == "__main__":
    with socketserver.ThreadingTCPServer(("127.0.0.1", 8765), Bridge) as server:
        server.daemon_threads = True
        Path("/native/gateway-ready").touch()
        server.serve_forever()
