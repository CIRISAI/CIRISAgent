__version__ = "3.10.5"

from typing import TYPE_CHECKING, Tuple

from . import hdrs as hdrs
from .client import (
    BaseConnector,
    ClientConnectionError,
    ClientConnectorCertificateError,
    ClientConnectorError,
    ClientConnectorSSLError,
    ClientError,
    ClientHttpProxyError,
    ClientOSError,
    ClientPayloadError,
    ClientProxyConnectionError,
    ClientRequest,
    ClientResponse,
    ClientResponseError,
    ClientSession,
    ClientSSLError,
    ClientTimeout,
    ClientWebSocketResponse,
    ConnectionTimeoutError,
    ContentTypeError,
    Fingerprint,
    InvalidURL,
    InvalidUrlClientError,
    InvalidUrlRedirectClientError,
    NamedPipeConnector,
    NonHttpUrlClientError,
    NonHttpUrlRedirectClientError,
    RedirectClientError,
    RequestInfo,
    ServerConnectionError,
    ServerDisconnectedError,
    ServerFingerprintMismatch,
    ServerTimeoutError,
    SocketTimeoutError,
    TCPConnector,
    TooManyRedirects,
    UnixConnector,
    WSServerHandshakeError,
    request,
)
from .cookiejar import CookieJar as CookieJar
from .cookiejar import DummyCookieJar as DummyCookieJar
from .formdata import FormData as FormData
from .helpers import BasicAuth, ChainMapProxy, ETag
from .http import HttpVersion as HttpVersion
from .http import HttpVersion10 as HttpVersion10
from .http import HttpVersion11 as HttpVersion11
from .http import WebSocketError as WebSocketError
from .http import WSCloseCode as WSCloseCode
from .http import WSMessage as WSMessage
from .http import WSMsgType as WSMsgType
from .multipart import BadContentDispositionHeader as BadContentDispositionHeader
from .multipart import BadContentDispositionParam as BadContentDispositionParam
from .multipart import BodyPartReader as BodyPartReader
from .multipart import MultipartReader as MultipartReader
from .multipart import MultipartWriter as MultipartWriter
from .multipart import content_disposition_filename as content_disposition_filename
from .multipart import parse_content_disposition as parse_content_disposition
from .payload import PAYLOAD_REGISTRY as PAYLOAD_REGISTRY
from .payload import AsyncIterablePayload as AsyncIterablePayload
from .payload import BufferedReaderPayload as BufferedReaderPayload
from .payload import BytesIOPayload as BytesIOPayload
from .payload import BytesPayload as BytesPayload
from .payload import IOBasePayload as IOBasePayload
from .payload import JsonPayload as JsonPayload
from .payload import Payload as Payload
from .payload import StringIOPayload as StringIOPayload
from .payload import StringPayload as StringPayload
from .payload import TextIOPayload as TextIOPayload
from .payload import get_payload as get_payload
from .payload import payload_type as payload_type
from .payload_streamer import streamer as streamer
from .resolver import AsyncResolver as AsyncResolver
from .resolver import DefaultResolver as DefaultResolver
from .resolver import ThreadedResolver as ThreadedResolver
from .streams import EMPTY_PAYLOAD as EMPTY_PAYLOAD
from .streams import DataQueue as DataQueue
from .streams import EofStream as EofStream
from .streams import FlowControlDataQueue as FlowControlDataQueue
from .streams import StreamReader as StreamReader
from .tracing import TraceConfig as TraceConfig
from .tracing import TraceConnectionCreateEndParams as TraceConnectionCreateEndParams
from .tracing import TraceConnectionCreateStartParams as TraceConnectionCreateStartParams
from .tracing import TraceConnectionQueuedEndParams as TraceConnectionQueuedEndParams
from .tracing import TraceConnectionQueuedStartParams as TraceConnectionQueuedStartParams
from .tracing import TraceConnectionReuseconnParams as TraceConnectionReuseconnParams
from .tracing import TraceDnsCacheHitParams as TraceDnsCacheHitParams
from .tracing import TraceDnsCacheMissParams as TraceDnsCacheMissParams
from .tracing import TraceDnsResolveHostEndParams as TraceDnsResolveHostEndParams
from .tracing import TraceDnsResolveHostStartParams as TraceDnsResolveHostStartParams
from .tracing import TraceRequestChunkSentParams as TraceRequestChunkSentParams
from .tracing import TraceRequestEndParams as TraceRequestEndParams
from .tracing import TraceRequestExceptionParams as TraceRequestExceptionParams
from .tracing import TraceRequestRedirectParams as TraceRequestRedirectParams
from .tracing import TraceRequestStartParams as TraceRequestStartParams
from .tracing import TraceResponseChunkReceivedParams as TraceResponseChunkReceivedParams

if TYPE_CHECKING:
    # At runtime these are lazy-loaded at the bottom of the file.
    from .worker import GunicornUVLoopWebWorker as GunicornUVLoopWebWorker
    from .worker import GunicornWebWorker as GunicornWebWorker

__all__: Tuple[str, ...] = (
    "hdrs",
    # client
    "BaseConnector",
    "ClientConnectionError",
    "ClientConnectorCertificateError",
    "ClientConnectorError",
    "ClientConnectorSSLError",
    "ClientError",
    "ClientHttpProxyError",
    "ClientOSError",
    "ClientPayloadError",
    "ClientProxyConnectionError",
    "ClientResponse",
    "ClientRequest",
    "ClientResponseError",
    "ClientSSLError",
    "ClientSession",
    "ClientTimeout",
    "ClientWebSocketResponse",
    "ConnectionTimeoutError",
    "ContentTypeError",
    "Fingerprint",
    "InvalidURL",
    "InvalidUrlClientError",
    "InvalidUrlRedirectClientError",
    "NonHttpUrlClientError",
    "NonHttpUrlRedirectClientError",
    "RedirectClientError",
    "RequestInfo",
    "ServerConnectionError",
    "ServerDisconnectedError",
    "ServerFingerprintMismatch",
    "ServerTimeoutError",
    "SocketTimeoutError",
    "TCPConnector",
    "TooManyRedirects",
    "UnixConnector",
    "NamedPipeConnector",
    "WSServerHandshakeError",
    "request",
    # cookiejar
    "CookieJar",
    "DummyCookieJar",
    # formdata
    "FormData",
    # helpers
    "BasicAuth",
    "ChainMapProxy",
    "ETag",
    # http
    "HttpVersion",
    "HttpVersion10",
    "HttpVersion11",
    "WSMsgType",
    "WSCloseCode",
    "WSMessage",
    "WebSocketError",
    # multipart
    "BadContentDispositionHeader",
    "BadContentDispositionParam",
    "BodyPartReader",
    "MultipartReader",
    "MultipartWriter",
    "content_disposition_filename",
    "parse_content_disposition",
    # payload
    "AsyncIterablePayload",
    "BufferedReaderPayload",
    "BytesIOPayload",
    "BytesPayload",
    "IOBasePayload",
    "JsonPayload",
    "PAYLOAD_REGISTRY",
    "Payload",
    "StringIOPayload",
    "StringPayload",
    "TextIOPayload",
    "get_payload",
    "payload_type",
    # payload_streamer
    "streamer",
    # resolver
    "AsyncResolver",
    "DefaultResolver",
    "ThreadedResolver",
    # streams
    "DataQueue",
    "EMPTY_PAYLOAD",
    "EofStream",
    "FlowControlDataQueue",
    "StreamReader",
    # tracing
    "TraceConfig",
    "TraceConnectionCreateEndParams",
    "TraceConnectionCreateStartParams",
    "TraceConnectionQueuedEndParams",
    "TraceConnectionQueuedStartParams",
    "TraceConnectionReuseconnParams",
    "TraceDnsCacheHitParams",
    "TraceDnsCacheMissParams",
    "TraceDnsResolveHostEndParams",
    "TraceDnsResolveHostStartParams",
    "TraceRequestChunkSentParams",
    "TraceRequestEndParams",
    "TraceRequestExceptionParams",
    "TraceRequestRedirectParams",
    "TraceRequestStartParams",
    "TraceResponseChunkReceivedParams",
    # workers (imported lazily with __getattr__)
    "GunicornUVLoopWebWorker",
    "GunicornWebWorker",
)


def __dir__() -> Tuple[str, ...]:
    return __all__ + ("__author__", "__doc__")


def __getattr__(name: str) -> object:
    global GunicornUVLoopWebWorker, GunicornWebWorker

    # Importing gunicorn takes a long time (>100ms), so only import if actually needed.
    if name in ("GunicornUVLoopWebWorker", "GunicornWebWorker"):
        try:
            from .worker import GunicornUVLoopWebWorker as guv
            from .worker import GunicornWebWorker as gw
        except ImportError:
            return None

        GunicornUVLoopWebWorker = guv  # type: ignore[misc]
        GunicornWebWorker = gw  # type: ignore[misc]
        return guv if name == "GunicornUVLoopWebWorker" else gw

    raise AttributeError(f"module {__name__} has no attribute {name}")
