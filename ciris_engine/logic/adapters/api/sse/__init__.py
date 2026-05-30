"""SSE helpers for the CIRIS API adapter.

Generic, route-agnostic utilities for wrapping arbitrary async-iterator
event sources in FastAPI ``StreamingResponse`` Server-Sent Event
streams. Today this package hosts the federation event bridge; future
SSE surfaces (e.g. tool-streaming, durable-handle ack streaming) can
reuse the same machinery.
"""
