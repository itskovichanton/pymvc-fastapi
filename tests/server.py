import uvicorn
from fastapi import Request, FastAPI
from src.mybootstrap_ioc_itskovichanton.ioc import bean
from starlette_context import middleware, plugins

from tests.controller import TestController, TestController2

fast_api = FastAPI(title='CustomLogger', debug=False)
# fast_api.add_middleware(
#     middleware.ContextMiddleware,
#     plugins=(plugins.ForwardedForPlugin()),
# )


@bean(port=("server.port", int, 8000))
class TestServer:
    test_controller: TestController
    test_controller2: TestController2

    def start(self):
        uvicorn.run(fast_api, port=self.port)


srv: TestServer


@fast_api.get("/search1/{table}")
async def m1(table: str, request: Request, q: str = None, limit: int = 0, count: int = 100):
    return await srv.test_controller.test(table, request, q, limit, count)


@fast_api.get("/search2/{table}")
async def m2(table: str, request: Request, q: str, limit: int = 0, count: int = 100):
    return await srv.test_controller2.test(table, request, q, limit, count)


@fast_api.get("/search3/{table}")
async def m3(table: str, request: Request, q: str, limit: int = 0, count: int = 100):
    return await srv.test_controller2.test2(table, request, q, limit, count)
