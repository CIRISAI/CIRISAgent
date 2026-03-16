#!/usr/bin/env python3
"""
Simple telemetry receiver for testing export destinations.

Listens on localhost:9999 and logs all incoming requests.
Supports OTLP, Prometheus, and Graphite formats.

Usage:
    python tools/test_telemetry_receiver.py

Then configure in the app:
    Name: Local Test
    Endpoint: http://<your-local-ip>:9999
    Format: OTLP (or any)
    Signals: Metrics
    Auth: None
"""

import json
import logging
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(message)s", datefmt="%H:%M:%S")
logger = logging.getLogger(__name__)

# ANSI colors
GREEN = "\033[92m"
BLUE = "\033[94m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
RESET = "\033[0m"


class TelemetryReceiver(BaseHTTPRequestHandler):
    """HTTP handler that accepts and logs telemetry data."""

    def log_message(self, format, *args):
        """Override to use our logger."""
        pass  # Suppress default logging

    def _send_response(self, status=200, body=None):
        """Send HTTP response."""
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, HEAD, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.end_headers()
        if body:
            self.wfile.write(json.dumps(body).encode())

    def do_OPTIONS(self):
        """Handle CORS preflight."""
        self._send_response(200)

    def do_HEAD(self):
        """Handle HEAD requests (used for connectivity test)."""
        logger.info(f"{GREEN}HEAD{RESET} {self.path} - Connectivity test")
        self._send_response(200)

    def do_GET(self):
        """Handle GET requests."""
        logger.info(f"{BLUE}GET{RESET} {self.path}")

        # Log headers
        auth = self.headers.get("Authorization", "None")
        logger.info(f"  Auth: {auth[:30]}..." if len(auth) > 30 else f"  Auth: {auth}")

        self._send_response(200, {"status": "ok", "message": "Telemetry receiver ready"})

    def do_POST(self):
        """Handle POST requests (OTLP data)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length) if content_length > 0 else b""

        # Determine format from path
        path = self.path.lower()
        if "otlp" in path or "v1/metrics" in path or "v1/traces" in path or "v1/logs" in path:
            format_type = "OTLP"
        elif "prometheus" in path:
            format_type = "Prometheus"
        elif "graphite" in path:
            format_type = "Graphite"
        else:
            format_type = "Unknown"

        logger.info(f"{YELLOW}POST{RESET} {self.path} ({format_type})")

        # Log headers
        auth = self.headers.get("Authorization", "None")
        content_type = self.headers.get("Content-Type", "None")
        logger.info(f"  Content-Type: {content_type}")
        logger.info(f"  Auth: {auth[:30]}..." if len(auth) > 30 else f"  Auth: {auth}")
        logger.info(f"  Body size: {len(body)} bytes")

        # Try to parse and display body
        if body:
            try:
                if b"{" in body[:10]:  # JSON
                    data = json.loads(body)
                    logger.info(f"  {CYAN}JSON Data:{RESET}")
                    # Pretty print first 500 chars
                    pretty = json.dumps(data, indent=2)[:500]
                    for line in pretty.split("\n")[:15]:
                        logger.info(f"    {line}")
                    if len(pretty) >= 500:
                        logger.info("    ...")
                else:
                    # Plain text (Prometheus/Graphite)
                    text = body.decode("utf-8", errors="replace")[:500]
                    logger.info(f"  {CYAN}Text Data:{RESET}")
                    for line in text.split("\n")[:10]:
                        logger.info(f"    {line}")
            except Exception as e:
                logger.info(f"  Body (raw): {body[:200]}...")

        self._send_response(200, {"status": "ok", "received": len(body), "timestamp": datetime.now().isoformat()})


def main():
    port = 9999
    server = HTTPServer(("0.0.0.0", port), TelemetryReceiver)

    # Get local IP for display
    import socket

    hostname = socket.gethostname()
    try:
        local_ip = socket.gethostbyname(hostname)
    except:
        local_ip = "localhost"

    print(
        f"""
{GREEN}╔══════════════════════════════════════════════════════════════╗
║           Telemetry Test Receiver Started                     ║
╚══════════════════════════════════════════════════════════════╝{RESET}

Listening on: {CYAN}http://0.0.0.0:{port}{RESET}

{YELLOW}Configure in CIRIS Mobile App:{RESET}
┌──────────────────────────────────────────────────────────────┐
│  Name:      Local Test                                       │
│  Endpoint:  http://{local_ip}:{port}                          │
│  Format:    OTLP (recommended)                               │
│  Signals:   Metrics (or any)                                 │
│  Auth:      None                                             │
│  Interval:  60 seconds                                       │
└──────────────────────────────────────────────────────────────┘

{BLUE}Supported endpoints:{RESET}
  • POST /v1/metrics  (OTLP metrics)
  • POST /v1/traces   (OTLP traces)
  • POST /v1/logs     (OTLP logs)
  • POST /metrics     (Prometheus)
  • POST /graphite    (Graphite)
  • HEAD /            (connectivity test)

Press Ctrl+C to stop.
"""
    )

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Shutting down...{RESET}")
        server.shutdown()


if __name__ == "__main__":
    main()
