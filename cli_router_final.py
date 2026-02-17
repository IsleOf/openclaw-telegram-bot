#!/usr/bin/env python3
"""
CLI Router with Format Conversion
Converts OpenCode CLI output to OpenAI-compatible format for OpenClaw
"""

import json
import subprocess
import os
import re
import time
from http.server import HTTPServer, BaseHTTPRequestHandler


def clean_output(text):
    """Clean ANSI codes and build messages from CLI output"""
    text = re.sub(r"\x1b\[[0-9;]*m", "", text)
    lines = []
    for line in text.split("\n"):
        line = line.strip()
        if line and not line.startswith(">") and "build" not in line.lower():
            lines.append(line)
    return "\n".join(lines).strip()


def extract_text(content):
    """Extract text from OpenAI format (handles string or array)"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(part.get("text", "") or part.get("content", ""))
        return " ".join(parts)
    return str(content)


def convert_to_openclaw_format(text_response):
    """
    Convert plain text to OpenClaw expected format
    OpenClaw expects: [{"type": "text", "text": "response"}]
    """
    return [{"type": "text", "text": text_response}]


class RouterHandler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
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
            self.wfile.write(
                json.dumps({"status": "CLI Router with Format Conversion"}).encode()
            )

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            try:
                content_length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(content_length))

                model = body.get("model", "opencode/kimi-k2.5-free")
                messages = body.get("messages", [])

                prompt = ""
                for msg in reversed(messages):
                    if msg.get("role") == "user":
                        prompt = extract_text(msg.get("content", ""))
                        break

                if not prompt:
                    self.send_error(400, "No user message")
                    return

                env = os.environ.copy()
                env["PATH"] = "/home/ubuntu/.opencode/bin:" + env.get("PATH", "")

                try:
                    result = subprocess.run(
                        ["opencode", "run", "-m", model, prompt],
                        capture_output=True,
                        text=True,
                        timeout=30,
                        env=env,
                        cwd="/home/ubuntu",
                    )
                    raw_output = result.stdout + result.stderr
                    cleaned = clean_output(raw_output) or "No response"
                except Exception as e:
                    cleaned = f"Error: {str(e)}"

                formatted_content = convert_to_openclaw_format(cleaned)

                timestamp = int(time.time())
                response = {
                    "id": f"chatcmpl-{timestamp}",
                    "object": "chat.completion",
                    "created": timestamp,
                    "model": model,
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": formatted_content,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": len(prompt.split()),
                        "completion_tokens": len(cleaned.split()),
                        "total_tokens": len(prompt.split()) + len(cleaned.split()),
                    },
                }

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(response).encode())

            except Exception as e:
                self.send_error(500, str(e))
        else:
            self.send_error(404)


print("[ROUTER] Starting CLI Router with Format Conversion on 127.0.0.1:4097")
HTTPServer(("127.0.0.1", 4097), RouterHandler).serve_forever()
