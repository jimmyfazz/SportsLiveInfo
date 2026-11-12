"""Exercise the real HTTP handler even when the runner forbids socket binding.

Loopback remains the default where available. Only a PermissionError on bind
selects the in-memory transport; other server errors must still fail tests.
"""
import http.client
import io
import threading
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from types import SimpleNamespace

from sportsliveinfo.engine import Engine
from sportsliveinfo.server import UI


class _Connection:
    def __init__(self, request):
        self.request = io.BytesIO(request)
        self.output = io.BytesIO()

    def makefile(self, *args, **kwargs):
        return self.request

    def sendall(self, data):
        self.output.write(data)


class IngressTestClient:
    def __init__(self, store, csrf, *, memory=False):
        self.worker = None
        self.server = SimpleNamespace(store=store, engine=Engine(store), csrf=csrf)
        self.base = "http://127.0.0.1/"
        self.transport = "memory"
        if memory:
            return
        try:
            server = ThreadingHTTPServer(("127.0.0.1", 0), UI, bind_and_activate=False)
            try:
                server.server_bind()
                server.server_activate()
            except Exception:
                server.server_close()
                raise
        except PermissionError:
            return
        server.store, server.engine, server.csrf = store, self.server.engine, csrf
        self.server = server
        self.transport = "loopback"
        self.base = "http://127.0.0.1:%d/" % server.server_address[1]
        self.worker = threading.Thread(target=server.serve_forever, daemon=True)
        self.worker.start()

    def close(self):
        if self.worker:
            self.server.shutdown()
            self.server.server_close()
            self.worker.join(timeout=3)

    def open(self, request, timeout=3):
        if self.transport == "loopback":
            return urllib.request.urlopen(request, timeout=timeout)
        request = request if isinstance(request, urllib.request.Request) else urllib.request.Request(request)
        for _ in range(10):
            url = urllib.parse.urlsplit(request.full_url)
            if (url.scheme, url.netloc) != ("http", "127.0.0.1"):
                raise ValueError("In-memory test client only accepts its own loopback origin")
            path = urllib.parse.urlunsplit(("", "", url.path or "/", url.query, ""))
            body = request.data or b""
            headers = dict(request.header_items())
            headers["Host"] = url.netloc
            headers["Content-Length"] = str(len(body))
            raw = (request.get_method() + " " + path + " HTTP/1.0\r\n" +
                   "".join(k + ": " + v + "\r\n" for k, v in headers.items()) + "\r\n").encode("ascii") + body
            connection = _Connection(raw)
            UI(connection, ("127.0.0.1", 0), self.server)
            response = http.client.HTTPResponse(_Connection(connection.output.getvalue()))
            response.begin()
            if response.status in (301, 302, 303):
                location = response.headers["Location"]
                response.close()
                request = urllib.request.Request(urllib.parse.urljoin(request.full_url, location))
                continue
            if response.status >= 400:
                raise urllib.error.HTTPError(request.full_url, response.status, response.reason,
                                             response.headers, response)
            return response
        raise RuntimeError("Too many test HTTP redirects")
