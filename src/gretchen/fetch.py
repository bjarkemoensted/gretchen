import anytree
from bs4 import BeautifulSoup
import functools
import re
import requests
from sqlalchemy.orm.decl_api import DeclarativeMeta
from typing import Callable

import logging 
logger = logging.getLogger(__name__)

from gretchen.caching import Cache


def parse_cp(html: str):
    soup = BeautifulSoup(html, 'html.parser')
    hit = soup.find('p', class_='product-page-price')
    
    s = hit.text.replace(",", "")
    res = min(map(int, re.findall(r"€(\d+)", s)))
    
    return res


def read_url(url: str):
    """Reads a URL"""
    r = requests.get(url)
    res = r.text
    return res
    
    
class Scraper:
    def __init__(self, cache_kwargs: dict=None):
        
        # url, table name, dict?
        if cache_kwargs is None:
            cache_kwargs = dict()
        
        self.cache = Cache(**cache_kwargs)
        self.scrapers = dict()
    
    def add_scraper(self, name: str, url: str, parser: Callable):
        cache_html = self.cache(read_url)
        read_and_cache = functools.partial(cache_html, url)
        
        f = lambda: parser(read_and_cache())
        self.scrapers[name] = f
        
        return self



if __name__ == '__main__':
    from gretchen import logger as pkglog
    logging.basicConfig(level=logging.ERROR)
    pkglog.setLevel(logging.DEBUG)
    logger.debug("fuck off")
    
    url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/"
    url2 = "https://pommier-furniture.com/product/otto-solid-wood-chair/"
    
    
    scrape = Scraper()
    scrape.add_scraper(
        name="cotto",
        url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/",
        parser=parse_cp
    ).add_scraper(
        name="otto",
        url="https://pommier-furniture.com/product/otto-solid-wood-chair/",
        parser=parse_cp
    )
    
    d = scrape()
    print(d)
    
    print(scrape)
    
    fp = functools.partial(read_url, url)
    
    f1 = functools.partial(f, a=2)
    f2 = functools.partial(f1, b=2)