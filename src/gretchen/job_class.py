from bs4 import BeautifulSoup
import cachier
from functools import wraps, partial
import inspect
from pathlib import Path
import re
import requests
import sqlalchemy as sa
from typing import Callable

from gretchen.config import local_data_dir
from gretchen import sql


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


def cache_factory(func: Callable, max_age_seconds: int=None) -> Callable:
    pass  # @cachier(stale_after=datetime.timedelta(days=3))

    

class Task:
    """Class for handling 1) reading of HTML from URLs, and 2) parsing said HTML into a desired format.
    A cache instance can be used to avoid hitting sites too often when developing the parsing methods etc."""

    def __init__(self, url: str, html_parser: Callable, verbose=False):
        """url: the URL from which to read HTML
        html_parser: The callable which will parse HTML into a quantity of interest
        verbose: Whether to print stuff
        html_cache: A Cache instance for caching HTML locally so I don't get blocked"""

        self.url = url
        self.html_parser = html_parser
        self.verbose=verbose
    
    def vprint(self, *args, **kwargs):
        """Print, if verbose is True"""
        if self.verbose:
            print(*args, **kwargs)
    
    def read_url(self):
        """Reads a URL"""
        r = requests.get(self.url)
        res = r.text
        return res
    
    def _attempt_cache(self):
        if self.cache:
            return self.cache.read()
    
    def get_html(self):
        """Gets HTML either from the URL, or from a local cache if available"""
        
        # Return cached HTML if available and sufficiently fresh
        cached = self._attempt_cache()
        if cached is not None:
            self.vprint("Got HTML from cache")
            return cached
        
        # Otherwise, read from URL (and cache, if using cache)
        html = self.read_url()
        if self.cache:
            self.cache.save(html)
            print("HTML saved to cache")
        
        return html

    def run(self):
        """Run the task - grabs HTML and parses it"""
        html = self.get_html()
        res = self.html_parser(html)
        return res
    #


def with_class_defaults(f):
    """Wrapper for methods which looks at optional arguments which are not specified, and instead uses attributes
    with the same name from the containing class/instance.
    Assumes all keywords are in fact mandatory, so this will throw an error if a keyword is not specified, or available
    in the instance containing the method."""
    
    # Determine optional arguments
    sig = inspect.signature(f)
    optional = [name for name, param in sig.parameters.items() if param.default is not param.empty]
    
    @wraps(f)
    def inner(self, *args, **kwargs):
        # Find non-specified keyword arguments
        d = {k: v for k, v in kwargs.items()}
        for k in optional:
            if k not in kwargs:
                # Attempt to use default from the containing instance
                v = getattr(self, k)
                if v is None:
                    raise RuntimeError(f"No value provided, and no default in {self} for {k}.")
                
                d[k] = v
        res = f(self, *args, **d)
        return res
    
    return inner


class Job:
    """Job class which handles a collection of tasks and updating a data store with the results."""

    def __init__(self, name: str, url: str=None, html_parser=None, col_or_type: sa.Column|type=None):
        """name: a name for this job
        use: URL at which to look for data.
        html_parser: callable parsing HTML into data.
        col_or_type: info on the column used for storing resulting data. Can be an SQLAlchemy Column instance,
        or a builtin python datatype. In the latter case, a suitable column is inferred.
        
        For html_parser, url, and col_or_type, values can be specified when instantiating the job, or individually,
        for each of the job's tasks."""

        self.name = name
        self.task_names = []
        self.tasks = dict()
        self.cols = dict()
        
        self.url = url
        self.html_parser = html_parser
        self.col_or_type = col_or_type
    
    
    def _register_task(self, name: str, col: sa.Column, task: Task):
        """Registers a task with this job"""
        if name in self.tasks:
            raise RuntimeError(f"Already registered as task with name '{name}'.")
    
        self.task_names.append(name)
        self.tasks[name] = task
        self.cols[name] = col
    
    @with_class_defaults
    def add_task(
            self,
            name: str,
            url: str=None,
            html_parser: Callable=None,
            col_or_type: sa.Column | type=None
    ):
        """Adds a new task to this job.
        name is the task name, also used for the column in which to store results."""
        
        # Set up the task
        task = Task(url=url, html_parser=html_parser)
        
        # Set up the column for storing result
        if not isinstance(col_or_type, sa.Column):
            col = sql.infer_column(python_type=col_or_type)
        else:
            col = col_or_type

        self._register_task(name=name, col=col, task=task)
        
        return self


job = Job(
    name="pommier",
    html_parser=parse_cp
).add_task(
    name="cotto",
    url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/",
    col_or_type=int
).add_task(
    name="otto",
    url="https://pommier-furniture.com/product/otto-solid-wood-chair/",
    col_or_type=int
)


if __name__ == '__main__':
    # cache = Cache(cache_dir / "deleteme.json")
    # scraper = Task(
    #     url="https://pommier-furniture.com/product/mosso-solid-wood-armchair/",
    #     html_parser=parse_cp,
    #     verbose=True,
    #     html_cache=cache
    # )
    
    #print(job)
    #for name, task in job.tasks.items():
    #    print(name, task.run())
    
    #cache.reset()
    
    a = mock("myurl")
    
    ca = cachier()(mock)
    
    a2 = ca("myurl")
    print(a)
    print(a2)