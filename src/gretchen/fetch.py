from bs4 import BeautifulSoup
from functools import wraps, partial
import inspect
from pathlib import Path
import re
import requests
import sqlalchemy as sa
from typing import Callable

from gretchen.config import local_data_dir
from gretchen.caching.cache_tools import Cache
from gretchen.config import logger
from gretchen import sql


def read_url(url: str):
    """Reads a URL"""
    r = requests.get(url)
    res = r.text
    return res


class Fetcher:
    """Responsible for getting raw text data from a remote source, and handling caching"""
    
    def __init__(self, url: str=None, data_getter: Callable=None, get_endpoint: str=None, cache: Cache=None):
        """Initialize a fetcher.
        url: url to read raw html from.
        get_endpoint: endpoint to get data from
        data_getter: callable which returns raw data. Specify one of: data_getter, url, or get_endpoint
        cache: a cache instance to use for caching"""
        
        if data_getter is None:
            data_getter = self.setup_getter(url=url, get_endpoint=get_endpoint)
        
        self.get_data_from_remote = data_getter
        self.cache = cache
    
    @staticmethod
    def setup_getter(**kwargs):
        not_none = [k for k, v in kwargs.items() if v is not None]
        if len(not_none) != 1:
            raise ValueError(f"Exactly one argument must be specified. Got: {', '.join(sorted(not_none))}")
        k = not_none[0]
        v = kwargs[v]
        match k:
            case "url":
                return partial(read_url, url=v)
            case "get_endpoint":
                raise NotImplementedError("Should probably do this at some point")
            case _:
                raise RuntimeError(f"No getter could be defined for {k}={v}.")
            #
        #
    
    def _attempt_cache(self):
        if self.cache:
            return self.cache.read()
        #
    
    def get_data(self):
        raise NotImplementedError


if __name__ == '__main__':
    # cache = Cache(cache_dir / "deleteme.json")
    # scraper = Task(
    #     url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/",
    #     html_parser=parse_cp,
    #     verbose=True,
    #     html_cache=cache
    # )
    print(job)
    for name, task in job.tasks.items():
        print(name, task.run())
    #cache.reset()