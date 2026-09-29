#!/usr/bin/env python3
"""LAN homepage: lists every web service running on this Mac.

Stdlib only (runs on the system /usr/bin/python3). Combines the services
declared in services.json with ones auto-discovered from listening TCP ports,
probes each one, and renders a page of links using whatever hostname the
visitor used (e.g. mymac.local), so links work from any device.
"""

import argparse
import concurrent.futures
import html
import http.client
import json
import os
import re
import socket
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parent
CONFIG = Path(os.environ.get("HOMEPAGE_CONFIG", ROOT / "services.json"))
CACHE_TTL = 15

# Well-known ports -> friendly names for auto-discovered services.
KNOWN_PORTS = {
    11434: ("Ollama", "🦙"), 8080: ("HTTP (8080)", "🌐"), 1234: ("LM Studio", "🧠"),
    3000: ("Web app (3000)", "🌐"), 5173: ("Vite dev server", "⚡"), 8000: ("HTTP (8000)", "🌐"),
    8888: ("Jupyter", "📓"), 9090: ("Prometheus", "📈"), 3001: ("Web app (3001)", "🌐"),
    7860: ("Gradio", "🎛️"), 8188: ("ComfyUI", "🎨"), 5432: ("PostgreSQL", "🐘"), 6379: ("Redis", "🧱"),
    22: ("SSH", "🔑"), 5900: ("Screen Sharing (VNC)", "🖥️"), 445: ("SMB file sharing", "📁"),
}
TITLE_RE = re.compile(rb"<title[^>]*>(.*?)</title>", re.I | re.S)


def load_config() -> dict:
    try:
        return json.loads(CONFIG.read_text())
    except FileNotFoundError:
        return {}
    except ValueError as e:
        return {"error": f"services.json: {e}"}


def listening() -> dict:
    """port -> process name for TCP listeners reachable from the network (not loopback-only)."""
    try:
        out = subprocess.run(["/usr/sbin/lsof", "-nP", "-iTCP", "-sTCP:LISTEN", "-F", "cn"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return {}
    ports, cmd = {}, None
    for line in out.splitlines():
        if line.startswith("c"):
            cmd = line[1:]
        elif line.startswith("n"):
            addr = line[1:]
            host, _, port = addr.rpartition(":")
            if not port.isdigit() or host in ("127.0.0.1", "[::1]", "localhost"):
                continue
            ports.setdefault(int(port), cmd)
    return ports


def probe(port: int, path: str = "/") -> dict:
    """Try HTTP (then HTTPS) on localhost; return up/http/title/latency."""
    for scheme, conn_cls in (("http", http.client.HTTPConnection), ("https", http.client.HTTPSConnection)):
        start = time.time()
        try:
            kwargs = {"timeout": 1.5}
            if scheme == "https":
                import ssl
                kwargs["context"] = ssl._create_unverified_context()
            conn = conn_cls("127.0.0.1", port, **kwargs)
            conn.request("GET", path or "/", headers={"User-Agent": "homepage-probe", "Accept": "text/html,*/*"})
            resp = conn.getresponse()
            body = resp.read(65536) if resp.getheader("content-encoding") in (None, "identity") else b""
            conn.close()
            m = TITLE_RE.search(body)
            title = html.unescape(m.group(1).decode(errors="replace").strip()) if m else None
            return {"up": True, "http": True, "scheme": scheme, "status": resp.status,
                    "title": title, "ms": round((time.time() - start) * 1000)}
        except (http.client.HTTPException, ssl_errors()):
            continue  # something listens but it isn't this protocol
        except OSError:
            break
    # Not HTTP; is the port open at all?
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return {"up": True, "http": False}
    except OSError:
        return {"up": False, "http": False}


def ssl_errors():
    import ssl
    return ssl.SSLError


_cache = {"t": 0, "data": None}
_lock = threading.Lock()


def collect() -> dict:
    with _lock:
        if _cache["data"] and time.time() - _cache["t"] < CACHE_TTL:
            return _cache["data"]
    cfg = load_config()
    ignore_ports = set(cfg.get("ignore_ports", []))
    ignore_procs = set(cfg.get("ignore_processes", []))
    listeners = listening()

    services = []
    declared_ports = set()
    for s in cfg.get("services", []):
        s = dict(s)
        s["declared"] = True
        if s.get("port"):
            declared_ports.add(s["port"])
        s["process"] = listeners.get(s.get("port"))
        services.append(s)
    for port, proc in sorted(listeners.items()):
        if port in declared_ports or port in ignore_ports or proc in ignore_procs or port == SELF_PORT:
            continue
        name, icon = KNOWN_PORTS.get(port, (None, None))
        services.append({"name": name or proc or f"Port {port}", "port": port, "icon": icon or "🔌",
                         "process": proc, "declared": False})

    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = {pool.submit(probe, s["port"], s.get("probe_path", "/")): s for s in services if s.get("port")}
        for fut, s in futures.items():
            s.update(fut.result())
    for s in services:
        if not s.get("port"):  # external URL entries
            s.update({"up": None, "http": True})
    data = {"title": cfg.get("title") or socket.gethostname().split(".")[0], "error": cfg.get("error"),
            "services": services, "generated": time.time()}
    with _lock:
        _cache.update(t=time.time(), data=data)
    return data


# ------------------------------------------------------------------ rendering

PAGE = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'><rect x='1' y='2' width='14' height='10' rx='2' fill='%232a78d6'/><rect x='5' y='13' width='6' height='1.5' rx='.75' fill='%232a78d6'/></svg>">
<style>
:root {{ color-scheme: light; --page:#f9f9f7; --surface:#fcfcfb; --surface-2:#f3f2ef; --ink:#0b0b0b; --ink-2:#52514e; --muted:#898781;
  --border:rgba(11,11,11,.10); --accent:#2a78d6; --good:#0ca30c; --critical:#d03b3b; }}
@media (prefers-color-scheme: dark) {{ :root {{ color-scheme: dark; --page:#0d0d0d; --surface:#1a1a19; --surface-2:#232321; --ink:#fff;
  --ink-2:#c3c2b7; --border:rgba(255,255,255,.10); --accent:#3987e5; }} }}
* {{ box-sizing: border-box; }}
body {{ margin:0; background:var(--page); color:var(--ink); font:14px/1.45 system-ui,-apple-system,"Segoe UI",sans-serif; }}
main {{ max-width:1100px; margin:0 auto; padding:40px 16px; }}
header {{ display:flex; align-items:baseline; justify-content:space-between; gap:12px; flex-wrap:wrap; margin-bottom:24px; }}
h1 {{ margin:0; font-size:26px; }}
h2 {{ font-size:12px; text-transform:uppercase; letter-spacing:.05em; color:var(--ink-2); margin:28px 0 10px; font-weight:600; }}
.muted {{ color:var(--muted); font-size:12px; }}
.grid {{ display:grid; grid-template-columns:repeat(auto-fill,minmax(250px,1fr)); gap:12px; }}
a.card, div.card {{ display:flex; gap:12px; padding:14px 16px; background:var(--surface); border:1px solid var(--border); border-radius:10px;
  color:inherit; text-decoration:none; min-width:0; transition:border-color .15s, transform .15s; }}
a.card:hover {{ border-color:var(--accent); transform:translateY(-1px); }}
.icon {{ font-size:24px; line-height:1; flex:none; width:32px; text-align:center; }}
.body {{ min-width:0; flex:1; }}
.name {{ font-weight:600; display:flex; align-items:center; gap:6px; }}
.dot {{ width:8px; height:8px; border-radius:50%; background:var(--muted); flex:none; }}
.dot.up {{ background:var(--good); }} .dot.down {{ background:var(--critical); }}
.desc {{ color:var(--ink-2); font-size:13px; margin-top:2px; }}
.meta {{ color:var(--muted); font-size:12px; margin-top:4px; font-family:ui-monospace,Menlo,monospace; overflow-wrap:anywhere; }}
.down-card {{ opacity:.6; }}
.error {{ color:var(--critical); }}
</style></head>
<body><main>
<header><h1>{title}</h1><span class="muted">{host} · refreshed {when}</span></header>
{error}
{sections}
<p class="muted" style="margin-top:32px">Services come from <code>services.json</code> plus anything listening on the network. JSON at <a href="/api/services">/api/services</a>.</p>
</main>
<script>setTimeout(() => location.reload(), 30000)</script>
</body></html>"""


def card(s: dict, host: str) -> str:
    e = html.escape
    url = s.get("url")
    if not url and s.get("port") and s.get("http"):
        url = f"{s.get('scheme', 'http')}://{host}:{s['port']}{s.get('path', '')}"
    state = "up" if s.get("up") else "down" if s.get("up") is False else ""
    meta = []
    if s.get("port"):
        meta.append(f":{s['port']}")
    if s.get("process"):
        meta.append(s["process"])
    if s.get("status"):
        meta.append(f"HTTP {s['status']}")
    if s.get("ms") is not None:
        meta.append(f"{s['ms']} ms")
    if s.get("up") is False:
        meta.append("not running")
    desc = s.get("description") or (s.get("title") if s.get("title") and s.get("title") != s.get("name") else "")
    inner = (f'<div class="icon">{e(s.get("icon") or "🌐")}</div><div class="body">'
             f'<div class="name"><span class="dot {state}"></span>{e(s["name"])}</div>'
             + (f'<div class="desc">{e(desc)}</div>' if desc else "")
             + f'<div class="meta">{e(" · ".join(meta))}</div></div>')
    cls = "card" + (" down-card" if s.get("up") is False else "")
    if url and s.get("up") is not False:
        return f'<a class="{cls}" href="{e(url)}">{inner}</a>'
    return f'<div class="{cls}">{inner}</div>'


def render(host: str) -> str:
    data = collect()
    web = [s for s in data["services"] if s.get("http") or (s.get("declared") and s.get("up") is False)]
    other = [s for s in data["services"] if s not in web]
    sections = []
    for title, items in (("Web services", web), ("Other open ports", other)):
        if items:
            items.sort(key=lambda s: (not s.get("declared"), s.get("up") is False, s["name"].lower()))
            sections.append(f"<h2>{title}</h2><div class=\"grid\">{''.join(card(s, host) for s in items)}</div>")
    return PAGE.format(
        title=html.escape(data["title"]), host=html.escape(host),
        when=time.strftime("%H:%M:%S", time.localtime(data["generated"])),
        error=f'<p class="error">{html.escape(data["error"])}</p>' if data.get("error") else "",
        sections="".join(sections) or "<p>No services found.</p>",
    )


class Handler(BaseHTTPRequestHandler):
    server_version = "homepage"

    def _host(self) -> str:
        host = self.headers.get("Host") or socket.gethostname()
        return urlsplit("//" + host).hostname or host

    def _send(self, code: int, body: bytes, ctype: str):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == "/":
            self._send(200, render(self._host()).encode(), "text/html; charset=utf-8")
        elif path == "/api/services":
            self._send(200, json.dumps(collect(), indent=2).encode(), "application/json")
        elif path == "/healthz":
            self._send(200, b"ok\n", "text/plain")
        else:
            self._send(404, b"not found\n", "text/plain")

    do_HEAD = do_GET

    def log_message(self, fmt, *args):
        pass


SELF_PORT = 80


def main():
    global SELF_PORT
    ap = argparse.ArgumentParser(description="LAN homepage listing local services")
    ap.add_argument("--host", default=os.environ.get("HOMEPAGE_HOST", "0.0.0.0"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("HOMEPAGE_PORT", "80")))
    args = ap.parse_args()
    SELF_PORT = args.port
    ThreadingHTTPServer.allow_reuse_address = True
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"homepage listening on http://{args.host}:{args.port}", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
