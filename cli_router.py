#!/usr/bin/env python3
"""
CLI Router - Unified OpenAI-compatible API for coding CLI tools
Supports: OpenCode, Kilocode, Claude Code
"""

import json
import subprocess
import os
import re
import time
import sys
import argparse
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Dict, List, Optional, Tuple
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("cli-router")

# Configuration
DEFAULT_CONFIG = {
    "port": 4097,
    "host": "127.0.0.1",
    "backends": {
        "opencode": {
            "type": "cli",
            "command": "opencode run",
            "timeout": 60,
            "models": {
                "opencode/kimi-k2.5-free": "opencode/kimi-k2.5-free",
                "opencode/minimax-m2.5-free": "opencode/minimax-m2.5-free",
            },
        },
        "kilocode": {
            "type": "cli",
            "command": "kilocode run",
            "timeout": 60,
            "models": {"kilocode/default": "default"},
        },
        "claude": {
            "type": "cli",
            "command": "claude --dangerously-skip-permissions",
            "timeout": 120,
            "models": {"claude/sonnet": "default"},
        },
    },
}


class CLIRouter:
    """Main router class"""

    def __init__(self, config: Dict):
        self.config = config
        self.host = config.get("host", "127.0.0.1")
        self.port = config.get("port", 4097)

    def clean_output(self, text: str) -> str:
        """Clean CLI output"""
        # Remove ANSI escape codes
        text = re.sub(r"\x1b\[[0-9;]*m", "", text)
        # Remove build messages and prompts
        lines = []
        for line in text.split("\n"):
            line = line.strip()
            if line and not line.startswith(">") and "build" not in line.lower():
                lines.append(line)
        return "\n".join(lines).strip()

    def extract_text(self, content) -> str:
        """Extract text from OpenAI format content"""
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

    def get_backend_for_model(self, model_id: str) -> Tuple[str, Dict]:
        """Determine which backend to use based on model ID"""
        # Check for prefix match
        for backend_name, backend_config in self.config["backends"].items():
            if model_id.startswith(f"{backend_name}/"):
                return backend_name, backend_config
            if model_id in backend_config.get("models", {}):
                return backend_name, backend_config

        # Default to first backend
        first_backend = list(self.config["backends"].keys())[0]
        return first_backend, self.config["backends"][first_backend]

    def run_cli_command(self, backend_config: Dict, model: str, prompt: str) -> str:
        """Execute CLI command"""
        cmd_parts = backend_config["command"].split()

        # Add model flag
        if model and model != "default":
            cmd_parts.extend(["-m", model])

        # Add prompt
        cmd_parts.append(prompt)

        # Setup environment
        env = os.environ.copy()
        env["PATH"] = "/home/ubuntu/.opencode/bin:" + env.get("PATH", "")

        try:
            logger.info(f"Executing: {' '.join(cmd_parts[:6])}...")
            result = subprocess.run(
                cmd_parts,
                capture_output=True,
                text=True,
                timeout=backend_config.get("timeout", 60),
                env=env,
                cwd="/home/ubuntu",
            )
            output = result.stdout + result.stderr
            cleaned = self.clean_output(output)
            logger.info(f"Response: {cleaned[:100]}...")
            return cleaned if cleaned else "No response from model"
        except subprocess.TimeoutExpired:
            logger.error("Command timeout")
            return "Error: Request timeout"
        except Exception as e:
            logger.error(f"Command error: {e}")
            return f"Error: {str(e)}"

    def create_request_handler(self):
        """Create HTTP request handler"""
        router = self

        class RequestHandler(BaseHTTPRequestHandler):
            def log_message(self, format, *args):
                """Custom logging"""
                logger.info(f"{self.address_string()} - {format % args}")

            def send_json_response(self, data: Dict, status: int = 200):
                """Send JSON response"""
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_OPTIONS(self):
                """Handle CORS preflight"""
                self.send_response(200)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                self.end_headers()

            def do_GET(self):
                """Handle GET requests"""
                if self.path == "/v1/models":
                    # Return all models
                    models = []
                    for backend_name, config in router.config["backends"].items():
                        for model_id in config.get("models", {}).keys():
                            models.append(
                                {
                                    "id": model_id,
                                    "object": "model",
                                    "owned_by": backend_name,
                                }
                            )

                    self.send_json_response({"object": "list", "data": models})

                elif self.path == "/health":
                    self.send_json_response(
                        {
                            "status": "healthy",
                            "router": "CLI Router",
                            "version": "1.0.0",
                            "backends": list(router.config["backends"].keys()),
                        }
                    )
                else:
                    self.send_json_response(
                        {
                            "status": "CLI Router",
                            "endpoints": [
                                "/v1/models",
                                "/v1/chat/completions",
                                "/health",
                            ],
                        }
                    )

            def do_POST(self):
                """Handle POST requests"""
                if self.path == "/v1/chat/completions":
                    # Parse request body
                    content_length = int(self.headers.get("Content-Length", 0))
                    if content_length == 0:
                        self.send_json_response({"error": "Empty body"}, 400)
                        return

                    try:
                        body = self.rfile.read(content_length)
                        request_data = json.loads(body)
                    except json.JSONDecodeError:
                        self.send_json_response({"error": "Invalid JSON"}, 400)
                        return

                    model_id = request_data.get("model", "")
                    messages = request_data.get("messages", [])
                    stream = request_data.get("stream", False)

                    # Extract user prompt
                    prompt = ""
                    for msg in reversed(messages):
                        if msg.get("role") == "user":
                            prompt = router.extract_text(msg.get("content", ""))
                            break

                    if not prompt:
                        self.send_json_response({"error": "No user message found"}, 400)
                        return

                    # Determine backend
                    backend_name, backend_config = router.get_backend_for_model(
                        model_id
                    )
                    backend_model = backend_config.get("models", {}).get(
                        model_id, model_id
                    )

                    logger.info(f"Request: backend={backend_name}, model={model_id}")

                    # Execute based on backend type
                    if backend_config["type"] == "cli":
                        response_text = router.run_cli_command(
                            backend_config, backend_model, prompt
                        )
                    else:
                        response_text = "Backend type not implemented"

                    # Build OpenAI-compatible response
                    timestamp = int(time.time())
                    response = {
                        "id": f"chatcmpl-{timestamp}",
                        "object": "chat.completion",
                        "created": timestamp,
                        "model": model_id,
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": response_text,  # STRING format for openai-completions
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": len(prompt.split()),
                            "completion_tokens": len(response_text.split()),
                            "total_tokens": len(prompt.split())
                            + len(response_text.split()),
                        },
                    }

                    self.send_json_response(response)

                else:
                    self.send_json_response({"error": "Not found"}, 404)

        return RequestHandler

    def start(self):
        """Start the router server"""
        handler = self.create_request_handler()
        server = HTTPServer((self.host, self.port), handler)

        logger.info(f"CLI Router starting on {self.host}:{self.port}")
        logger.info(f"Backends: {list(self.config['backends'].keys())}")
        logger.info("Router ready - waiting for requests")

        try:
            server.serve_forever()
        except KeyboardInterrupt:
            logger.info("Shutting down...")
            server.shutdown()


def main():
    parser = argparse.ArgumentParser(description="CLI Router for OpenClaw")
    parser.add_argument("--port", type=int, default=4097, help="Port to listen on")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind to")
    parser.add_argument("--config", help="Path to config file")
    args = parser.parse_args()

    # Load config
    config = DEFAULT_CONFIG.copy()
    config["port"] = args.port
    config["host"] = args.host

    if args.config and os.path.exists(args.config):
        with open(args.config, "r") as f:
            user_config = json.load(f)
            config.update(user_config)

    # Start router
    router = CLIRouter(config)
    router.start()


if __name__ == "__main__":
    main()
