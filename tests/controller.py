from dataclasses import dataclass
from datetime import date
from typing import Any, Protocol

from fastapi import Request
from src.mybootstrap_core_itskovichanton import validation
from src.mybootstrap_ioc_itskovichanton.ioc import bean
from src.mybootstrap_ioc_itskovichanton.utils import default_dataclass_field
from src.mybootstrap_mvc_itskovichanton.pipeline import Action
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter

from src.mybootstrap_mvc_fastapi_itskovichanton.presenters import XMLResultPresenterImpl, JSONResultPresenterImpl
from src.mybootstrap_mvc_fastapi_itskovichanton.utils import get_call_from_request


@dataclass
class Feed:
    title: str
    content: str


class ExtApi(Protocol):

    def read_feed(self, q: str, limit: int = 10) -> list[Feed]:
        pass


@bean
class ExtApiImpl(ExtApi):

    def read_feed(self, q: str, limit: int = 10) -> list[Feed]:
        return [Feed(title=f"Title {i}", content=f"{q}") for i in range(1, limit)]


@bean
class SearchFeedAction(Action):
    ext_api: ExtApi

    def run(self, args: Any = None, prev_result: Any = None) -> Any:
        validation.check_not_empty("query", args.query, "Пустой запрос")
        if args.limit == 10:
            return {'answer': args.limit / 0}  # just for tests
        if args.limit == 11:
            return f"Today is {date.today()}, query={args.query}, ip={args.ip}"
        return self.ext_api.read_feed("args.query", limit=10)


@bean
class TestAction(Action):

    def run(self, args: Any = None, prev_result: Any = None) -> Any:
        return {"a": 100}


@bean
class TestController:
    default_result_presenter: ResultPresenter = default_dataclass_field(JSONResultPresenterImpl())
    search_feed_action: SearchFeedAction

    async def test(self, table: str, request: Request, q: str, limit: int = 0, count: int = 100):
        p = get_call_from_request(request)
        p.query = q
        p.limit = limit
        p.count = count
        p.table = table
        return await self.run(self.search_feed_action, call=p)


@bean
class TestController2:
    default_result_presenter: ResultPresenter = default_dataclass_field(XMLResultPresenterImpl())
    search_feed_action: SearchFeedAction
    test_action: TestAction

    async def test(self, table: str, request: Request, q: str, limit: int = 0, count: int = 100):
        call = get_call_from_request(request)
        return await self.run(self.search_feed_action, call)

    async def test2(self, table: str, request: Request, q: str, limit: int = 0, count: int = 100):
        call = get_call_from_request(request)
        call.query = q
        call.limit = limit
        call.count = count
        call.table = table
        return await self.run(self.test_action, call)
