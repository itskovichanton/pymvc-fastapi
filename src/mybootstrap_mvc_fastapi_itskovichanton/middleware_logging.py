import time
import typing
from asyncio import new_event_loop, set_event_loop
from concurrent.futures import ThreadPoolExecutor
from logging import Logger
from typing import Callable, Awaitable, Tuple, Dict, List

from starlette.middleware.base import BaseHTTPMiddleware, DispatchFunction
from starlette.requests import Request
from starlette.responses import Response, StreamingResponse
from starlette.types import Scope, Message, ASGIApp

from src.mybootstrap_mvc_fastapi_itskovichanton import utils


class RequestWithBody(Request):
    """Creation of new request with body"""

    def __init__(self, scope: Scope, body: bytes) -> None:
        super().__init__(scope, self._receive)
        self._body = body
        self._body_returned = False

    async def _receive(self) -> Message:
        if self._body_returned:
            return {"type": "http.disconnect"}
        else:
            self._body_returned = True
            return {"type": "http.request", "body": self._body, "more_body": False}


class HTTPLogLineCompiler:

    async def get_log_line(self, request, req_body, response_body, response, elapsed_time_ms):
        return {"response_headers": utils.tuple_to_dict(response.headers.items()),
                "request_headers": utils.tuple_to_dict(request.headers.items()),
                "method": request.method, "url": request.url, "request-body": req_body,
                "response": response_body, "response_code": response.status_code, "elapsed_ms": elapsed_time_ms}


class HTTPLoggingMiddleware(BaseHTTPMiddleware):

    def __init__(self, app: ASGIApp, logger: Logger,
                 dispatch: typing.Optional[DispatchFunction] = None,
                 encoding: str = "utf-8",
                 async_mode: bool = True,
                 log_line_compiler: HTTPLogLineCompiler = HTTPLogLineCompiler()):
        super().__init__(app, dispatch)
        self._logger = logger
        self._encoding = encoding
        self._async_mode = async_mode
        if not log_line_compiler:
            log_line_compiler = HTTPLogLineCompiler()
        self._log_line_compiler = log_line_compiler
        if async_mode:
            self._pool = ThreadPoolExecutor()
        self._loop = new_event_loop()
        set_event_loop(self._loop)

    async def dispatch(self, request: Request,
                       call_next: Callable[[Request], Awaitable[StreamingResponse]]) -> Response:

        start_time = int(round(time.time() * 1000))
        request_body_bytes = await request.body()
        request_with_body = RequestWithBody(request.scope, request_body_bytes)

        response = await call_next(request_with_body)

        self._log_response(request_body_bytes, response, request, int(round(time.time() * 1000) - start_time))

        return response

    async def _get_response_params(self, response: StreamingResponse) -> Tuple[bytes, Dict[str, str], int]:
        """Getting the response parameters of a response and create a new response."""
        response_byte_chunks: List[bytes] = []
        response_status: List[int] = []
        response_headers: List[Dict[str, str]] = []

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_status.append(message["status"])
                response_headers.append(
                    {k.decode(self._encoding): v.decode(self._encoding) for k, v in message["headers"]})
            else:
                response_byte_chunks.append(message["body"])

        await response.stream_response(send)
        content = b"".join(response_byte_chunks)
        return content, response_headers[0], response_status[0]

    def _log_response(self, request_body_bytes, response, request, elapsed_time_ms):
        log_future = self._async_log_response(request_body_bytes, response, request, elapsed_time_ms)
        if self._pool:
            return self._pool.submit(self._loop.run_until_complete, log_future)
        self._loop.run_until_complete(log_future)

    async def _async_log_response(self, request_body_bytes, response, request, elapsed_time_ms):
        response_content_bytes, response_headers, response_status = await self._get_response_params(response)

        try:
            req_body = request_body_bytes.decode(self._encoding)
        except:
            req_body = "<request>"

        response_body = response_content_bytes.decode(self._encoding)

        log_dict = await self._log_line_compiler.get_log_line(request, req_body, response_body, response,
                                                              elapsed_time_ms)
        if log_dict is not None:
            self._logger.info(log_dict)
