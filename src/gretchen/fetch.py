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
from gretchen import sql


class FuncNodeMixin(anytree.NodeMixin):
    def disp(self, parent):
        s = f"{self.name} - {parent.name}"
        return s
    
    def _pre_detach(self, parent):
        pass  #print(f"_pre_detach", self.disp(parent))
    def _post_detach(self, parent):
        pass  # print(f"_post_detach", self.disp(parent))
    def _pre_attach(self, parent):
        pass  # print(f"_pre_attach", self.disp(parent))
    def _post_attach(self, parent):
        pass  # print(f"_post_attach", self.disp(parent))


def _infer_callable_name(f: Callable|None) -> str|None:
    """Helper method for determining an appropriate representation of a callable"""
    
    # Try looking for name attribute
    try:
        return f.__name__
    except AttributeError:
        pass
    
    # Represent partial functions as function_name(arg1, arg2, k1=v1, k2=v2, ...)
    if isinstance(f, functools.partial):
        args_ = [str(arg) for arg in f.args]
        kws_ = [f"{k}={v}" for k, v in f.keywords.items()]
        argpart = ", ".join(args_ + kws_)
            
        res = f"{f.func.__name__}({argpart})"
        return res
    
    return None


class Fetch(FuncNodeMixin):
    
    def __init__(self, func: Callable=None, name: str=None, parent=None):
        self.func = func
        if name is None:
            try:
                name = func.__name__
            except AttributeError:
                pass
        self.name = name
        self.key = name
        self.parent = parent

    def add_function(self, func: Callable, name=None):
        f = Fetch(func, name=name, parent=self)
        return f


    def __call__(self, *args, results_dict: dict=None, **kwargs):
        if results_dict is None:
            results_dict = dict()
        
        if self.func is None:
            next_args = args
            next_kwargs = kwargs
        else:
            res = self.func(*args, **kwargs)
            
            if self.key is not None:
                assert self.key not in results_dict
                results_dict[self.key] = res
            next_args = (res,)
            next_kwargs = dict()
        
        for child in self.children:
            child(*next_args, results_dict=results_dict, **next_kwargs)
        
        return results_dict
    
    @property
    def displayname(self):
        name = self.name
        if name is None:
            name = _infer_callable_name(self.func)
        if name is None and self.parent is None:
            name = "root"
        
        return name
            
    def __repr__(self):
        return f"<Node: {self.displayname}>"

    def __str__(self):
        lines = []
        for pre, fill, node in anytree.RenderTree(self):
            lines.append("%s%s" % (pre, node.displayname))
        
        s = "\n".join(lines)
        return s
    
    def __getitem__(self, name: str):
        for node in anytree.PreOrderIter(self):
            if node.name == name:
                return node
            #
        raise KeyError(f"No node with name {name} located under {repr(self)}")


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



def f(a, b=42):
    print(f"Got {a=}, {b=}")
    return a + b


def g(x):
    print(f"Got {x=}")
    return 2*x


class Scraper(DBMixin, Fetch):
    def __init__(self, db_url: str, table_name_or_model: str|DeclarativeMeta, cache_kwargs: dict=None):
        
        # url, table name, dict?
        if cache_kwargs is None:
            cache_kwargs = dict()
        
        self.db_url = db_url
        self.table = table_name_or_model
        self._ensured_table_created = False
        self.cache = Cache(**cache_kwargs)
        super().__init__()
    
    @property
    def engine(self):
        return self.get_engine(url=self.db_url)
    
    def _get_model(self):
        pass  # !!!
    
    def add_scraper(self, name: str, url: str, parser: Callable):
        cache_html = self.cache(read_url)
        read_and_cache = functools.partial(cache_html, url)
        
        f = lambda: parser(read_and_cache())
        self.scrapers[name] = f
        
        return self

    def fetch(self):
        data = self()
        # url, table_name..... needed for model thingy? 
        self.gateway.save(data)


if __name__ == '__main__':
    from gretchen.config import db_path
    db_url = f'sqlite:///{db_path}'
    
    from gretchen import logger as pkglog
    logging.basicConfig(level=logging.ERROR)
    pkglog.setLevel(logging.DEBUG)
    
    url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/"
    url2 = "https://pommier-furniture.com/product/otto-solid-wood-chair/"
    
    
    scraper = Scraper(
        name="pommier",
        db_url=db_url
    )
    scraper.add_scraper(
        name="cotto",
        url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/",
        parser=parse_cp
    ).add_scraper(
        name="otto",
        url="https://pommier-furniture.com/product/otto-solid-wood-chair/",
        parser=parse_cp
    )
    
    d = scraper()
    print(d)
    
    print(scraper)
    
    res = scraper.fetch()
    print(res)