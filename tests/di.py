from opyoid import Module
from src.mybootstrap_core_itskovichanton import di

from src.mybootstrap_mvc_itskovichanton.di import MVCModule


class TestMVCModule(Module):
    def configure(self) -> None:
        self.install(MVCModule)


injector = di.init([TestMVCModule])
