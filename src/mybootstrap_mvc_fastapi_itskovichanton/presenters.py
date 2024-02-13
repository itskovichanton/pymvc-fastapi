import mimetypes
import os
from dataclasses import dataclass, asdict
from typing import Any, Optional, Union, Dict, Callable

from fastapi.encoders import jsonable_encoder, SetIntStr, DictIntStrAny
from fastapi.responses import JSONResponse
from fastapi.responses import Response
from pydantic import BaseModel, Extra
from src.mybootstrap_core_itskovichanton.utils import to_dict_deep
from src.mybootstrap_ioc_itskovichanton.utils import default_dataclass_field
from src.mybootstrap_mvc_fastapi_itskovichanton.utils import to_pydantic_model
from src.mybootstrap_mvc_itskovichanton.pipeline import Result
from src.mybootstrap_mvc_itskovichanton.result_presenter import ResultPresenter
from starlette.responses import FileResponse
from xsdata.formats.dataclass.serializers import XmlSerializer
from xsdata.formats.dataclass.serializers.config import SerializerConfig


@dataclass
class AsIsResultPresenterImpl(ResultPresenter):

    def __init__(self, media_type: str) -> None:
        super().__init__()
        self.media_type = media_type
        self.default_presenter = JSONResultPresenterImpl()

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        content = r.error
        if not content:
            content = r.result
        try:
            return Response(content=content, media_type=self.media_type)
        except:
            return self.default_presenter.present(r)


@dataclass
class XMLResultPresenterImpl(ResultPresenter):

    def __init__(self, config: SerializerConfig = SerializerConfig(pretty_print=True)) -> None:
        super().__init__()
        self.xml_serializer = XmlSerializer(config=config)

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        return Response(content=self.xml_serializer.render(r), media_type="application/xml")


class _ErrM(BaseModel):
    class Config:
        extra = Extra.allow


class _ResultM(BaseModel):
    error: _ErrM = None
    result: Any = None

    class Config:
        extra = Extra.allow


def to_result_model(x: Result):
    r = _ResultM(result=x.result)
    if x.error:
        r.error = _ErrM()
        for key, value in asdict(x.error).items():
            setattr(r.error, key, value)
    return r


@dataclass
class JSONResultPresenterImpl(ResultPresenter):
    to_dict: bool = False
    exclude: Optional[Union[SetIntStr, DictIntStrAny]] = None
    by_alias: bool = True
    exclude_unset: bool = False
    exclude_defaults: bool = False
    exclude_none: bool = True
    sqlalchemy_safe: bool = True
    include: Optional[Union[SetIntStr, DictIntStrAny]] = None
    custom_encoder: Optional[Dict[Any, Callable[[Any], Any]]] = None

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        return JSONResponse(
            status_code=self.http_code(r),
            content=jsonable_encoder(to_dict_deep(r) if self.to_dict else to_pydantic_model(r),
                                     exclude_unset=self.exclude_unset,
                                     include=self.include,
                                     exclude_none=self.exclude_none,
                                     exclude_defaults=self.exclude_defaults,
                                     exclude=self.exclude, by_alias=self.by_alias,
                                     sqlalchemy_safe=self.sqlalchemy_safe, custom_encoder=self.custom_encoder),
        )


@dataclass
class AnyResultPresenterImpl(ResultPresenter):
    error_presenter: ResultPresenter = default_dataclass_field(JSONResultPresenterImpl())

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        if r.error:
            return self.error_presenter.present(r)

        file_path = self.get_file_path(r.result)
        mime = mimetypes.guess_type(file_path)
        mime = mime[0] if len(mime) > 0 else None
        return FileResponse(path=file_path, filename=os.path.basename(file_path),
                            media_type=mime, status_code=self.http_code(r))

    def get_file_path(self, result):
        return str(result)


@dataclass
class BytesResultPresenterImpl(ResultPresenter):
    error_presenter: ResultPresenter = default_dataclass_field(JSONResultPresenterImpl())
    mime_type: str = None

    def present(self, r: Result) -> Any:
        r = self.preprocess_result(r)
        if r.error:
            return self.error_presenter.present(r)

        return Response(r.result, media_type=self.get_mime_type(r.result) or self.mime_type,
                        status_code=self.http_code(r))

    def get_mime_type(self, result):
        ...
