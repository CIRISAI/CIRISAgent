#!/usr/bin/env python3
"""Raw TCP test to see exactly what Home Assistant sends after info."""
import json
import socket


def main():
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("0.0.0.0", 10302))  # noqa: S104 - Test server needs to accept connections
    sock.listen(1)

    print("Listening on port 10302...")

    while True:
        conn, addr = sock.accept()
        print(f"\nConnection from {addr}")

        try:
            # Read first message
            data = b""
            while b"\n" not in data:
                chunk = conn.recv(1024)
                if not chunk:
                    break
                data += chunk

            if data:
                msg = json.loads(data.decode().strip())
                print(f"Received: {msg}")

                if msg.get("type") == "describe":
                    # Send info response
                    info = {
                        "type": "info",
                        "data": {
                            "asr": [
                                {
                                    "name": "test",
                                    "installed": True,
                                    "description": "Test",
                                    "models": [
                                        {"name": "test", "installed": True, "description": "Test", "languages": ["en"]}
                                    ],
                                }
                            ]
                        },
                    }
                    response = json.dumps(info) + "\n"
                    conn.send(response.encode())
                    print(f"Sent: {response.strip()}")

                    # Wait for next message
                    print("Waiting for next message...")
                    data = b""
                    while b"\n" not in data:
                        chunk = conn.recv(1024)
                        if not chunk:
                            print("Connection closed by client")
                            break
                        data += chunk

                    if data:
                        msg = json.loads(data.decode().strip())
                        print(f"Next message: {msg}")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            conn.close()


if __name__ == "__main__":
    main()
