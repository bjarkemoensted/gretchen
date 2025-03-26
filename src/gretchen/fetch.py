import anytree
from bs4 import BeautifulSoup
import functools
import logging
import re
import requests
from typing import Callable

from gretchen.caching import Cache


class FuncNodeMixin(anytree.NodeMixin):
    def disp(self, parent):
        s = f"{self.name} - {parent.name}"
        return s
    
    def _pre_detach(self, parent):
        print(f"_pre_detach", self.disp(parent))
    def _post_detach(self, parent):
        print(f"_post_detach", self.disp(parent))
    def _pre_attach(self, parent):
        print(f"_pre_attach", self.disp(parent))
    def _post_attach(self, parent):
        print(f"_post_attach", self.disp(parent))



class Fetch(FuncNodeMixin):
    
    def __init__(self, func: Callable=None, name: str=None, parent=None):
        self.func = func
        self.name = func.__name__ if not name and func else name
        self.key = name
        self.parent = parent

    def add_function(self, func: Callable, name=None):
        f = self.__class__(func, name=name, parent=self)
        return f


    def __call__(self, *args, **kwargs):
        pass  # TODO make empty dict, compute results, if self.key, do d[key] = res, then pass res to children
        for c in self.children:
            c(*args, **kwargs)
        #
    
    def __repr__(self):
        return f"<Node: {self.name}>"

    def __str__(self):
        lines = []
        for pre, fill, node in anytree.RenderTree(self):
            lines.append("%s%s" % (pre, node.name))
        
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


@Cache()
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

if __name__ == '__main__':
    import gretchen
    logger = logging.getLogger("gretchen")
    logger.setLevel(logging.DEBUG)
    # Create a console handler
    console_handler = logging.StreamHandler()

    # Add the handler to your logger
    logger.addHandler(console_handler)

    
    
    fetch = Fetch(name="foo")
    f_node = fetch.add_function(f)
    
    g_node = f_node.add_function(g)
    scraper = functools.partial(read_url, url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/")
    html = scraper()
    

    #b = Fetch("bar", parent=a)
    
    print(f"Eyy {fetch()}")
    
    url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/"
    url2 = "https://pommier-furniture.com/product/otto-solid-wood-chair/"
    
    print("go again!!!")
    again = Fetch()
    again.add_function(read_url).add_function(parse_cp, name="cotto_chair")
    print(again["cotto_chair"])
    print(again["read_url"])
    
    print(again(url))
    
    