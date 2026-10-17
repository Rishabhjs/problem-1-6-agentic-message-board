"""Stdlib HTTP API + static UI + SSE stream. No third-party dependencies."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "static")


def _list(qs, key):
    return [x for v in qs.get(key, []) for x in v.split(",") if x]


def make_handler(store):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj, code=200):
            body = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            return json.loads(self.rfile.read(n) or b"{}")

        def _feed(self, qs):
            one = lambda k, d=None: (qs.get(k) or [d])[0]
            return store.feed(q=one("q"), agents=_list(qs, "agent"), exclude=_list(qs, "mute"),
                              tags=_list(qs, "tag"), since=float(one("since", 0) or 0) or None,
                              after_id=int(one("after", 0) or 0) or None,
                              order=one("order", "new"), limit=one("limit", 50))

        def do_GET(self):
            u = urlparse(self.path)
            qs = parse_qs(u.query)
            if u.path == "/health":
                return self._json({"ok": True})
            if u.path == "/agents":
                return self._json(store.agents())
            if u.path == "/posts":
                return self._json(self._feed(qs))
            if u.path == "/views":
                return self._json(store.views())
            if u.path == "/stream":
                return self._stream(qs)
            if u.path in ("/", "/index.html"):
                with open(os.path.join(STATIC, "index.html"), "rb") as f:
                    body = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                return self.wfile.write(body)
            self._json({"error": "not found"}, 404)

        def do_POST(self):
            u = urlparse(self.path)
            try:
                d = self._body()
                if u.path == "/posts":
                    if not d.get("agent") or not d.get("text"):
                        return self._json({"error": "agent and text required"}, 400)
                    return self._json({"id": store.add_post(d["agent"], d["text"], d.get("tags", []),
                                                            d.get("reply_to"))}, 201)
                if u.path == "/agents":
                    if not d.get("name"):
                        return self._json({"error": "name required"}, 400)
                    store.upsert_agent(d)
                    return self._json({"ok": True}, 201)
                if u.path == "/views":
                    if not d.get("name"):
                        return self._json({"error": "name required"}, 400)
                    store.save_view(d["name"], d.get("spec", {}))
                    return self._json({"ok": True}, 201)
            except (ValueError, TypeError) as e:
                return self._json({"error": str(e)}, 400)
            self._json({"error": "not found"}, 404)

        def _stream(self, qs):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            last = int(qs.get("after", [0])[0] or 0)
            if not last:
                cur = store.feed(limit=1)
                last = cur[0]["id"] if cur else 0
            try:
                while True:
                    for p in reversed(store.feed(after_id=last, limit=100, agents=_list(qs, "agent"),
                                                 exclude=_list(qs, "mute"), tags=_list(qs, "tag"),
                                                 q=(qs.get("q") or [None])[0])):
                        self.wfile.write(("data: %s\n\n" % json.dumps(p)).encode())
                    top = store.feed(limit=1)
                    last = top[0]["id"] if top else last
                    self.wfile.write(b": ping\n\n")
                    self.wfile.flush()
                    time.sleep(1)
            except (BrokenPipeError, ConnectionResetError):
                pass

    return H


def serve(store, host, port, background=False):
    srv = ThreadingHTTPServer((host, port), make_handler(store))
    srv.daemon_threads = True
    if background:
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        return srv
    srv.serve_forever()
