from dataclasses import dataclass
from typing import Any, Optional, Union

from dicttoxml import dicttoxml
from fastapi.encoders import jsonable_encoder, SetIntStr, DictIntStrAny
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from src.mybootstrap_mvc_fastapi_itskovichanton.utils import object_to_dict
from src.mybootstrap_mvc_itskovichanton.pipeline import Result
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter


@dataclass
class XMLResultPresenterImpl(ResultPresenter):
    root = True
    custom_root = None
    ids = False
    attr_type = True
    cdata = False

    def present(self, r: Result) -> Any:
        data = dicttoxml(object_to_dict(r), custom_root=self.custom_root, root=self.root, ids=self.ids,
                         attr_type=self.attr_type, cdata=self.cdata)
        return Response(content=data, media_type="application/xml")


@dataclass
class JSONResultPresenterImpl(ResultPresenter):
    exclude: Optional[Union[SetIntStr, DictIntStrAny]] = None,
    by_alias: bool = True,
    exclude_unset: bool = False,
    exclude_defaults: bool = False,
    exclude_none: bool = False,
    sqlalchemy_safe: bool = True

    def present(self, r: Result) -> Any:
        return JSONResponse(
            status_code=self.http_code(r),
            content=jsonable_encoder(r, exclude_unset=self.exclude_unset,
                                     exclude_none=self.exclude_none,
                                     exclude_defaults=self.exclude_defaults,
                                     exclude=self.exclude, by_alias=self.by_alias,
                                     sqlalchemy_safe=self.sqlalchemy_safe),
        )
