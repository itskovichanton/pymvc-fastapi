from tests import server
from tests.app import ServerMVCApp
from tests.di import injector
from tests.server import TestServer


def main() -> None:
    app = injector.inject(ServerMVCApp)
    server.a = 10
    server.srv = injector.inject(TestServer)
    app.run()
    #
    # a = injector.inject(SearchFeedAction)
    # print(a.run("hello"))


if __name__ == '__main__':
    main()
