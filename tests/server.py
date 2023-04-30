import json

import uvicorn
from fastapi import Request, FastAPI
from pydantic import BaseModel
from src.mybootstrap_core_itskovichanton.logger import LoggerService
from src.mybootstrap_ioc_itskovichanton.ioc import bean

from controller import TestController, TestController2
from src.mybootstrap_mvc_fastapi_itskovichanton import utils
from src.mybootstrap_mvc_fastapi_itskovichanton.middleware_logging import HTTPLoggingMiddleware, HTTPLogLineCompiler


class CompactHTTPLogLineCompiler(HTTPLogLineCompiler):

    def _preprocess_param_value(self, k: str, v):
        k = k.upper()
        if "BLOB" in k or "BASE64" in k:
            return "<bytes>"
        return v

    async def get_log_line(self, request, req_body, response_body, response, elapsed_time_ms):
        session_token = utils.tuple_to_dict(request.headers.items()).get("sessionToken")
        request_params = dict(request.query_params)
        if request.method == "POST":
            try:
                f = await request.form()
                request_params.update(f.items())
            except:
                ...
        request_params = {k: self._preprocess_param_value(k, v) for k, v in request_params.items()}
        if "json" in response.headers["content-type"]:
            r = json.loads(response_body)
            if type(r) == dict:
                r = {k: self._preprocess_param_value(k, v) for k, v in r.items()}
                response_body = json.dumps(r)
        return {
            "sessionToken": session_token,
            "method": request.method, "url": request.url, "request-params": request_params,
            "response": response_body, "response_code": response.status_code}


@bean(port=("server.port", int, 8000))
class TestServer:
    test_controller: TestController
    test_controller2: TestController2
    logger_service: LoggerService

    def start(self):
        fast_api = FastAPI(title='Test', debug=False)
        fast_api.add_middleware(HTTPLoggingMiddleware,
                                # log_line_compiler=CompactHTTPLogLineCompiler(),
                                encoding="utf-8",
                                logger=self.logger_service.get_file_logger("http"))

        @fast_api.get("/search1/{table}")
        async def m1(table: str, request: Request, q: str = None, limit: int = 0, count: int = 100):
            return await self.test_controller.test(table, request, q, limit, count)

        @fast_api.post("/search10/{table}")
        async def m1(table: str, request: Request):
            params = dict(request.query_params)
            if request.method == "POST":
                try:
                    f = await request.form()
                    params.update(f.items())
                except:
                    ...
            return params

        @fast_api.post("/search3/{table}")
        async def m1(table: str, request: Request, p: SearchParams):
            return await self.test_controller.test(table, request, p.q, p.limit, p.count)

        @fast_api.get("/search2/{table}")
        async def m2(table: str, request: Request, q: str, limit: int = 0, count: int = 100):
            return await self.test_controller2.test(table, request, q, limit, count)

        @fast_api.get("/search3/{table}")
        async def m3(table: str, request: Request, q: str, limit: int = 0, count: int = 100):
            return await self.test_controller2.test2(table, request, q, limit, count)

        uvicorn.run(fast_api, port=self.port)


class SearchParams(BaseModel):
    q: str = None
    limit: int = 0
    count: int = 100
