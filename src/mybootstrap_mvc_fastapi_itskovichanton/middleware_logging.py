import typing
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


class HTTPLoggingMiddleware(BaseHTTPMiddleware):

    def __init__(self, app: ASGIApp, logger: Logger,
                 dispatch: typing.Optional[DispatchFunction] = None,
                 encoding: str = "utf-8"):
        super().__init__(app, dispatch)
        self.logger = logger
        self.encoding = encoding

    async def dispatch(self, request: Request,
                       call_next: Callable[[Request], Awaitable[StreamingResponse]]) -> Response:

        request_body_bytes = await request.body()
        request_with_body = RequestWithBody(request.scope, request_body_bytes)

        response = await call_next(request_with_body)
        response_content_bytes, response_headers, response_status = await self._get_response_params(response)

        try:
            req_body = request_body_bytes.decode(self.encoding)
        except:
            req_body = "<request>"

        response_body = response_content_bytes.decode(self.encoding)

        self.logger.info({"response_headers": utils.tuple_to_dict(response.headers.items()),
                          "request_headers": utils.tuple_to_dict(request.headers.items()),
                          "method": request.method, "url": request.url, "request-body": req_body,
                          "response": response_body, "response_code": response.status_code})

        return Response(response_content_bytes, response_status, response_headers)

    async def _get_response_params(self, response: StreamingResponse) -> Tuple[bytes, Dict[str, str], int]:
        """Getting the response parameters of a response and create a new response."""
        response_byte_chunks: List[bytes] = []
        response_status: List[int] = []
        response_headers: List[Dict[str, str]] = []

        async def send(message: Message) -> None:
            if message["type"] == "http.response.start":
                response_status.append(message["status"])
                response_headers.append(
                    {k.decode(self.encoding): v.decode(self.encoding) for k, v in message["headers"]})
            else:
                response_byte_chunks.append(message["body"])

        await response.stream_response(send)
        content = b"".join(response_byte_chunks)
        return content, response_headers[0], response_status[0]
