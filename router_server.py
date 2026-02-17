#!/usr/bin/env python3
import json, subprocess, os, re, time, sys
from http.server import HTTPServer, BaseHTTPRequestHandler


def clean(t):
    t = re.sub(r"\x1b\[[0-9;]*m", "", t)
    return "\n".join(
        [
            l
            for l in t.split("\n")
            if l.strip() and not l.strip().startswith(">") and "build" not in l.lower()
        ]
    ).strip()


def extract(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join([x.get("text", "") for x in c if isinstance(x, dict)])
    return str(c)


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(
                json.dumps(
                    {
                        "object": "list",
                        "data": [{"id": "opencode/kimi-k2.5-free", "object": "model"}],
                    }
                ).encode()
            )
        else:
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"status": "Router"}).encode())

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            l = int(self.headers.get("Content-Length", 0))
            d = json.loads(self.rfile.read(l))
            m = d.get("model", "opencode/kimi-k2.5-free")
            msgs = d.get("messages", [])
            prompt = ""
            for msg in reversed(msgs):
                if msg.get("role") == "user":
                    prompt = extract(msg.get("content", ""))
                    break
            env = os.environ.copy()
            env["PATH"] = "/home/ubuntu/.opencode/bin:" + env.get("PATH", "")
            print(
                f"[ROUTER] model={m} prompt={prompt[:50]}...",
                flush=True,
                file=sys.stderr,
            )
            try:
                r = subprocess.run(
                    ["opencode", "run", "-m", m, prompt],
                    capture_output=True,
                    text=True,
                    timeout=30,
                    env=env,
                    cwd="/home/ubuntu",
                )
                out = clean(r.stdout + r.stderr)
                print(f"[ROUTER] response={out[:100]}...", flush=True, file=sys.stderr)
            except Exception as e:
                out = f"Error: {e}"
            ts = int(time.time())
            resp = {
                "id": f"c{ts}",
                "object": "chat.completion",
                "created": ts,
                "model": m,
                "choices": [
                    {
                        "index": 0,
                        "message": {
                            "role": "assistant",
                            "content": out if out else "No response",
                        },
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


print("[ROUTER] Starting on 4097...", flush=True, file=sys.stderr)
HTTPServer(("127.0.0.1", 4097), H).serve_forever()
