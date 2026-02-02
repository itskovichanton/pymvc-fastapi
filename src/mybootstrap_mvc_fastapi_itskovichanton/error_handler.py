from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from src.mybootstrap_ioc_itskovichanton.ioc import bean
from src.mybootstrap_ioc_itskovichanton.utils import default_dataclass_field
from src.mybootstrap_mvc_fastapi_itskovichanton.presenters import JSONResultPresenterImpl
from src.mybootstrap_mvc_itskovichanton.exceptions import CoreException, ERR_REASON_VALIDATION
from src.mybootstrap_mvc_itskovichanton.pipeline import ActionRunner
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter


@bean
class ErrorHandlerFastAPISupport:
    action_runner: ActionRunner
    presenter: ResultPresenter = default_dataclass_field(JSONResultPresenterImpl())

    def mount(self, fast_api: FastAPI):
        def _raise(e: Exception):
            raise e

        @fast_api.exception_handler(RequestValidationError)
        async def unicorn_exception_handler(request: Request, e: Exception):
            return self.presenter.present(
                await self.action_runner.run(_raise, call=CoreException(message=str(e), reason=ERR_REASON_VALIDATION)))
