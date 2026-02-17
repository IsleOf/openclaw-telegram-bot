#!/usr/bin/env python3
import json, subprocess, os, re, time, sys
from http.server import HTTPServer, BaseHTTPRequestHandler

CONFIG = {
    "port": 4097,
    "host": "127.0.0.1",
    "default_backend": "opencode",
    "backends": {
        "opencode": {
            "type": "cli",
            "command": "opencode run",
            "timeout": 60,
            "models": {
                "opencode/kimi-k2.5-free": "kimi-k2.5-free",
                "opencode/minimax-m2.5-free": "minimax-m2.5-free",
            },
        }
    },
}


def clean(text):
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    return "\n".join(
        [
            l
            for l in text.split("\n")
            if l.strip() and not l.strip().startswith(">") and "build" not in l.lower()
        ]
    ).strip()


def extract(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join([x.get("text", "") for x in content if isinstance(x, dict)])
    return str(content)


def run(backend, model, prompt):
    cmd = backend["command"].split() + ["-m", model, prompt]
    env = os.environ.copy()
    env["PATH"] = "/home/ubuntu/.opencode/bin:" + env.get("PATH", "")
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=backend.get("timeout", 30),
            env=env,
            cwd="/home/ubuntu",
        )
        return clean(r.stdout + r.stderr) or "No response"
    except Exception as e:
        return f"Error: {e}"


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            models = []
            for b_name, cfg in CONFIG["backends"].items():
                for m_id in cfg.get("models", {}).keys():
                    models.append({"id": m_id, "object": "model"})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"object": "list", "data": models}).encode())
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "status": "CLI Router",
                        "backends": list(CONFIG["backends"].keys()),
                    }
                ).encode()
            )

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            l = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(l))
            m_id = d.get("model", "")
            msgs = d.get("messages", [])
            prompt = ""
            for msg in reversed(msgs):
                if msg.get("role") == "user":
                    prompt = extract(msg.get("content", ""))
                    break
            backend_name = CONFIG["default_backend"]
            backend = CONFIG["backends"][backend_name]
            model = backend.get("models", {}).get(m_id, m_id)
            out = run(backend, model, prompt)
            ts = int(time.time())
            resp = {
                "id": f"c{ts}",
                "object": "chat.completion",
                "created": ts,
                "model": m_id,
                "choices": [
                    {
                        "index": 0,
                        "message": {"role": "assistant", "content": out},
                        "finish_reason": "stop",
                    }
                ],
            }
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(resp).encode())
        else:
            self.send_response(404)
            self.end_headers()


print(f"[ROUTER] Starting on {CONFIG['host']}:{CONFIG['port']}", flush=True)
HTTPServer((CONFIG["host"], CONFIG["port"]), H).serve_forever()
