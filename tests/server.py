import uvicorn
from fastapi import Request, FastAPI
from pydantic import BaseModel
from src.mybootstrap_core_itskovichanton.logger import LoggerService
from src.mybootstrap_ioc_itskovichanton.ioc import bean

from src.mybootstrap_mvc_fastapi_itskovichanton.middleware_logging import HTTPLoggingMiddleware
from controller import TestController, TestController2


@bean(no_polymorph=True, port=("server.port", int, 8000))
class TestServer:
    test_controller: TestController
    test_controller2: TestController2
    logger_service: LoggerService

    def start(self):
        fast_api = FastAPI(title='Test', debug=False)
        fast_api.add_middleware(HTTPLoggingMiddleware,
                                encoding="utf-8",
                                logger=self.logger_service.get_file_logger("http"))

        @fast_api.get("/search1/{table}")
        async def m1(table: str, request: Request, q: str = None, limit: int = 0, count: int = 100):
            return await self.test_controller.test(table, request, q, limit, count)

        @fast_api.post("/search10/{table}")
        async def m1(table: str, request: Request, p: SearchParams):
            return {"name": "anton"}

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
