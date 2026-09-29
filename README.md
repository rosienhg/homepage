# homepage

A zero-dependency LAN landing page for this Mac, served on **port 80**: open **http://<hostname>.local/** from any device on the network to see every service running here, with a link to each.

- **Declared services** come from `services.json`: name, port, optional path, description and icon. They always show, with a red dot when they're down.
- **Auto-discovered services** are anything else listening on a non-loopback TCP port. Each port is probed over HTTP/HTTPS and labelled from the page `<title>` or a list of well-known ports (Ollama, LM Studio, ComfyUI, Gradio, Jupyter…). Non-HTTP ports are listed separately.
- Links use the hostname you visited (`<hostname>.local`, an IP, …), so they work from any client.
- The page reloads every 30 s, and results are cached for 15 s. JSON is available at `/api/services`, and there's a health check at `/healthz`.

It uses only the standard library and runs on the system `/usr/bin/python3`.

## Install

```bash
~/Developer/homepage/scripts/install.sh     # LaunchAgent local.homepage on :80
~/Developer/homepage/scripts/uninstall.sh
```

No root is needed: since 10.14, macOS lets unprivileged processes bind ports below 1024 on all interfaces. Logs go to `~/Library/Logs/homepage.log`.

For development: `python3 server.py --port 8081`.

## services.json

```json
{
  "title": "mymac",
  "services": [
    {"name": "macdash", "port": 8765, "description": "System dashboard", "icon": "📊"},
    {"name": "Ollama", "port": 11434, "path": "/api/tags", "icon": "🦙"},
    {"name": "Router", "url": "http://192.168.1.1", "icon": "📡"}
  ],
  "ignore_ports": [5000, 7000],
  "ignore_processes": ["ControlCenter", "rapportd"]
}
```

Service fields: `name`, `port` or `url`, `path` (appended to the link), `probe_path` (health check path, default `/`), `scheme`, `description` and `icon`. Edits take effect within 15 s, with no restart needed.

Discovery uses `lsof` as the current user, so it only sees listeners owned by that user. Add root-owned services, such as system sshd, to `services.json` if you want them listed.
