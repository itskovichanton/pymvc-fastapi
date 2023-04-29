from dataclasses import dataclass
from typing import Any, Optional, Union, Dict, Callable

from fastapi.encoders import jsonable_encoder, SetIntStr, DictIntStrAny
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from src.mbulak_tools.utils import to_dict_deep
from src.mybootstrap_mvc_itskovichanton.pipeline import Result
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


@dataclass
class AsIsResultPresenterImpl(ResultPresenter):

    def __init__(self, media_type: str) -> None:
        super().__init__()
        self.media_type = media_type

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        content = r.error
        if not content:
            content = r.result
        return Response(content=content, media_type=self.media_type)


@dataclass
class XMLResultPresenterImpl(ResultPresenter):

    def __init__(self, config: SerializerConfig = SerializerConfig(pretty_print=True)) -> None:
        super().__init__()
        self.xml_serializer = XmlSerializer(config=config)

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        return Response(content=self.xml_serializer.render(r), media_type="application/xml")


@dataclass
class JSONResultPresenterImpl(ResultPresenter):
    to_dict: bool = False
    exclude: Optional[Union[SetIntStr, DictIntStrAny]] = None
    by_alias: bool = True
    exclude_unset: bool = False
    exclude_defaults: bool = False
    exclude_none: bool = False
    sqlalchemy_safe: bool = True
    include: Optional[Union[SetIntStr, DictIntStrAny]] = None
    custom_encoder: Optional[Dict[Any, Callable[[Any], Any]]] = None

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        return JSONResponse(
            status_code=self.http_code(r),
            content=jsonable_encoder(to_dict_deep(r) if self.to_dict else r, exclude_unset=self.exclude_unset,
                                     include=self.include,
                                     exclude_none=self.exclude_none,
                                     exclude_defaults=self.exclude_defaults,
                                     exclude=self.exclude, by_alias=self.by_alias,
                                     sqlalchemy_safe=self.sqlalchemy_safe, custom_encoder=self.custom_encoder),
        )


