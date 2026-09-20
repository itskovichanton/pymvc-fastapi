import functools
from dataclasses import dataclass

from dacite import from_dict, Config
from src.mybootstrap_core_itskovichanton import di
from src.mybootstrap_core_itskovichanton.logger import LoggerService
from src.mybootstrap_core_itskovichanton.utils import generate_uid, get_basic_auth_header
from src.mybootstrap_ioc_itskovichanton.config import ConfigService
from src.mybootstrap_mvc_fastapi_itskovichanton.utils import parse_response
from src.mybootstrap_pyauth_itskovichanton.entities import AuthArgs


@dataclass
class MBClientConfig:
    url: str
    lang: str = None
    auth: AuthArgs = None


_injector = di.injector()
_logger_service = _injector.inject(LoggerService)
_config_service = _injector.inject(ConfigService)


def on_mbclient_api(_name, request_id_field_name="request_id"):
    def decor(func):

        def _get_config(self):
            config_name = f"{_name}_config"
            cfg: MBClientConfig = getattr(self, config_name, None)
            if not cfg:
                cfg = from_dict(data_class=MBClientConfig,
                                data=_config_service.get_config().settings[_name],
                                config=Config(check_types=False))
                setattr(self, config_name, cfg)
            return cfg

        @functools.wraps(func)
        def decorator_wrapper(self, *args, **kwargs):

            cfg = _get_config(self)

            kwargs['url'] = cfg.url
            headers = {request_id_field_name: generate_uid(version=4), }
            kwargs['headers'] = headers
            kwargs['session'] = _logger_service.get_logged_session(_name, url=cfg.url)

            if cfg:
                headers["lang"] = cfg.lang
                if cfg.auth:
                    headers["sessionToken"] = cfg.auth.session_token
                    if cfg.auth.username and cfg.auth.password:
                        headers["Authorization"] = get_basic_auth_header(cfg.auth.username, cfg.auth.password)

            r = func(self, *args, **kwargs)
            return parse_response(r)

        return decorator_wrapper

    return decor
