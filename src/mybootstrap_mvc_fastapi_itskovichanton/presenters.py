from dataclasses import dataclass
from typing import Any, Optional, Union

from fastapi.encoders import jsonable_encoder, SetIntStr, DictIntStrAny
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from src.mybootstrap_mvc_itskovichanton.pipeline import Result
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


@dataclass
class XMLResultPresenterImpl(ResultPresenter):

    def __init__(self, config: SerializerConfig = SerializerConfig(pretty_print=True)) -> None:
        super().__init__()
        self.xml_serializer = XmlSerializer(config=config)

    def present(self, r: Result) -> Any:
        return Response(content=self.xml_serializer.render(r), media_type="application/xml")


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
