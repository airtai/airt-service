# AUTOGENERATED! DO NOT EDIT! File to edit: ../notebooks/Uvicorn_Helpers.ipynb.

# %% auto 0
__all__ = ['run_uvicorn']

# %% ../notebooks/Uvicorn_Helpers.ipynb 1
import multiprocessing
from contextlib import contextmanager
from time import sleep
from typing import *

from fastapi import FastAPI
from uvicorn import Config, Server

# %% ../notebooks/Uvicorn_Helpers.ipynb 2
@contextmanager
def run_uvicorn(arg: Union[Config, FastAPI]) -> Iterator[None]:
    if isinstance(arg, Config):
        config: Config = arg
    else:
        config = Config(app=arg)

    def run(config: Config = config) -> None:
        server = Server(config=config)
        server.run()

    p = multiprocessing.Process(target=run)
    try:
        p.start()
        sleep(15)
        yield
    finally:
        p.terminate()
        p.join()
        p.close()
