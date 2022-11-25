from src.mybootstrap_core_itskovichanton.app import Application
from src.mybootstrap_ioc_itskovichanton.ioc import bean

from tests.server import TestServer


@bean(no_polymorph=True)
class ServerMVCApp(Application):
    server: TestServer

    def run(self):
        self.server.start()
