from src.mybootstrap_core_itskovichanton.di import injector

from app import ServerMVCApp


def main() -> None:
    app = injector().inject(ServerMVCApp)
    app.run()


if __name__ == '__main__':
    main()
