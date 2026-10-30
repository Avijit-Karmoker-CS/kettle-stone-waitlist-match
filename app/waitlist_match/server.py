"""A tiny web server that only listens on this computer (127.0.0.1).

The window Tanya sees is a page served from here. Nothing is reachable from
the network and nothing is sent anywhere (feature 28).
"""
import datetime as dt
import json
import os
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .desk import Desk
from .files import FileProblem

UI = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", "index.html")


def _json(obj):
    def default(o):
        if isinstance(o, (dt.date, dt.datetime, dt.time)):
            return o.isoformat()
        if isinstance(o, set):
            return sorted(o)
        return str(o)
    return json.dumps(obj, default=default).encode("utf-8")


class App:
    def __init__(self, desk: Desk, idle_minutes=0):
        self.desk = desk
        self.last_seen = time.time()
        self.idle_minutes = idle_minutes

    def route(self, method, path, query, body):
        d = self.desk
        if path == "/api/ping":
            return {"ok": True}
        if path == "/api/version":
            return {"v": d.version()}
        if path == "/api/status":
            return {"check": d.self_check(), "addons": d.addons(), "now": d.now().isoformat(sep=" ")}
        if path == "/api/therapists":
            s, c = d.load()
            return {"therapists": list(s.therapists), "default_length": s.default_length,
                    "today": d.today().isoformat(), "now": d.now().strftime("%Y-%m-%dT%H:%M")}
        if path == "/api/match" and method == "POST":
            return d.match(body)
        if path == "/api/morning":
            return d.morning()
        if path == "/api/offer" and method == "POST":
            d.set_offer(body["opening"], body["pid"], body.get("name", ""), body["status"])
            s, c = d.load()
            op = d.opening_from(c, {"therapist": body["therapist"], "date": body["date"],
                                    "start": body["start"], "length": body["length"],
                                    "cancelled_at": body.get("cancelled_at") or None,
                                    "kind": "late cancel"})
            if body.get("notice") is not None:
                op.notice_hours = float(body["notice"])
            res = c.match(op)
            return d.present(s, c, res)
        if path == "/api/lists":
            return d.lists()
        if path == "/api/lookup":
            return {"found": d.lookup(query.get("phone", [""])[0], query.get("name", [""])[0])}
        if path == "/api/add" and method == "POST":
            return d.add_to_waitlist(body.get("name"), body.get("phone", ""), body.get("note", ""))
        if path == "/api/summary":
            return d.summary(query.get("month", [None])[0])
        if path == "/api/noshow":
            return d.noshow_risk()
        if path == "/api/addons":
            return d.addons()
        if path == "/api/unlock" and method == "POST":
            return d.unlock(body.get("code", ""))
        if path == "/api/preview" and method == "POST":
            return d.preview_text(body["opening"], body["pid"])
        if path == "/api/file-openings":
            s, c = d.load()
            out = []
            for op in c.file_openings:
                res = c.match(op)
                d.log_run(op, res, "openings file")
                out.append(d.present(s, c, res))
            return {"file": os.path.basename(c.openings_path) if c.openings_path else None, "openings": out,
                    "warnings": [w for w in c.warnings if w.startswith("More than one")] + c.problems}
        raise FileProblem("Unknown request.")


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def _send(self, code, data, ctype="application/json"):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            try:
                self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError):
                pass  # the window was closed mid-reply

        def _handle(self, method):
            app.last_seen = time.time()
            u = urlparse(self.path)
            if u.path in ("/", "/index.html"):
                with open(UI, "rb") as fh:
                    return self._send(200, fh.read(), "text/html; charset=utf-8")
            if not u.path.startswith("/api/"):
                return self._send(404, b"Not found", "text/plain")
            # Only accept requests from this computer's own page.
            origin = self.headers.get("Origin")
            if origin and not origin.startswith(("http://127.0.0.1", "http://localhost")):
                return self._send(403, _json({"error": "Not allowed."}))
            body = {}
            if method == "POST":
                n = int(self.headers.get("Content-Length") or 0)
                try:
                    body = json.loads(self.rfile.read(n) or b"{}")
                except ValueError:
                    return self._send(400, _json({"error": "Bad request."}))
            try:
                out = app.route(method, u.path, parse_qs(u.query), body)
                self._send(200, _json(out))
            except FileProblem as exc:
                self._send(200, _json({"error": str(exc)}))
            except Exception as exc:
                log = os.path.join(app.desk.logs, "errors.txt")
                with open(log, "a", encoding="utf-8") as fh:
                    fh.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {u.path}\n{traceback.format_exc()}\n")
                self._send(200, _json({"error": f"Something went wrong ({exc.__class__.__name__}). "
                                                 "It was written to Data/logs/errors.txt for Julie."}))

        def do_GET(self):
            self._handle("GET")

        def do_POST(self):
            self._handle("POST")

    return Handler


def serve(desk, port=0, idle_minutes=0, ready=None):
    app = App(desk, idle_minutes)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), make_handler(app))
    httpd.daemon_threads = True
    if ready:
        ready(httpd.server_address[1])
    if idle_minutes:
        def watch():
            while True:
                time.sleep(30)
                if time.time() - app.last_seen > idle_minutes * 60:
                    desk.cleanup()
                    httpd.shutdown()
                    return
        threading.Thread(target=watch, daemon=True).start()
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
        desk.cleanup()
