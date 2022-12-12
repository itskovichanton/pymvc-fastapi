from tests.app import ServerMVCApp
from tests.di import injector


def main() -> None:
    app = injector.inject(ServerMVCApp)
    app.run()


if __name__ == '__main__':
    main()
