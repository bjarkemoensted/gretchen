from __future__ import annotations
import datetime
import dis
from functools import wraps
import hashlib
import inspect
import json
import logging
import pandas as pd
from pathlib import Path
import pickle
import sqlalchemy as sa
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import declarative_base, sessionmaker
from threading import RLock
import time
from typing import Callable

from gretchen import config


def stubborn(func):
    """Wrapper for making backend methods 'stubborn', i.e. attempt increasingly more aggresive
    recovery strategies when encountering SQL errors."""

    @wraps(func)
    def inner(self: Backend, *args, **kwargs):
        # Try standard recovery - ensuring table folder exists, recreating engines, etc
        try:
            return func(self, *args, **kwargs)
        except (OperationalError,) as e:
            logging.error(f"Backend {self.__class__} encountered an error. Attempt to recover.\n{e}")
            self._attempt_recover()
        
        # Could be wrong data types or something. Try just dumping the cache and starting over
        try:
            return func(self, *args, **kwargs)
        except (OperationalError,) as e:
            logging.error(f"Backend {self.__class__} failed recovery. Attempting cache dump.\n{e}")
            self.wipe()
        
        # :(
        try:
            return func(self, *args, **kwargs)
        except (OperationalError,) as e:
            logging.critical(f"Backend {self.__class__} failed after cache dump!\n{e}")
            raise
        #
    
    return inner


class Backend:
    """Handles saving and loading cached data to/from a cache."""

    _lock = RLock()
    _engines = dict()

    def __init__(self, db_path: Path=None, serialize: bool=None, table_name: str=None):
        """db_path is the folder for the database file.
        serialize indicates whether to pickle data before storing. If False, json is used.
        table_name is the name of the table to use for cachine. A prefix will be added if serializing."""
        
        if db_path is None:
            db_path = config.local_data_dir / "cache.db"
        
        if serialize is None:
            serialize = True
        
        if table_name is None:
            suffix = "_serialized" if serialize else ""
            table_name = "cache"+suffix
        
        # Set hooks for processing data before saving/after loading.
        self.save_hook = pickle.dumps if serialize else json.dumps
        self.load_hook = pickle.loads if serialize else json.loads
        self.column_dtype = sa.LargeBinary if serialize else sa.String
        
        self.db_path = db_path
        self.table_name = table_name
        
        self.BaseModel = declarative_base()
        self.CacheModel = self._make_cache_model()
        
        # Set up engine and stuff (setting up in a separate method)
        self.engine = None
        self.Session = None
        self.setup()
    
    def setup(self, restart_engine=False):
        """Setup up folder for database file, and SQL engine+sessionmaker.
        This can be called with restart_engine=True to force creation of a fresh engine"""
        
        self.db_path.parent.mkdir(exist_ok=True)
        self.engine = self.get_engine(url=self.url, force_new=restart_engine)
        self.Session = sessionmaker(bind=self.engine)
        self.db_path.parent.mkdir(exist_ok=True)
        self.BaseModel.metadata.create_all(self.engine)
    
    @property
    def url(self):
        res = f'sqlite:///{self.db_path.absolute()}'
        return res
    
    @classmethod
    def get_engine(cls, url: str, force_new=False) -> sa.Engine:
        """Make an engine. Looks up by url in a class dict to avoid creating multiple engines for URLs"""
        with cls._lock:
            if force_new or url not in cls._engines:
                cls._engines[url] = sa.create_engine(url, echo=False, pool_pre_ping=True)
            return cls._engines[url]
        #
    
    
    def _make_cache_model(self):
        """Returns a declarative base model for the cache."""
        
        class CacheModel(self.BaseModel):
            __tablename__ = self.table_name
            key = sa.Column(sa.String, primary_key=True)
            timestamp = sa.Column(sa.BigInteger, default=config.epoch, nullable=False)
            expires = sa.Column(sa.BigInteger, nullable=True)
            data = sa.Column(self.column_dtype, nullable=False)
        
        return CacheModel
    
    def _attempt_recover(self):
        """Attempts recovery. Re-runs setup to make sure a db file and a functioning connection engine are available.
        This can be called as part of a failure recovery strategy."""
        
        with self._lock:  # Acquire the lock to make sure no other threads attempt caching while resetting
            self.setup(restart_engine=True)
        #

    @stubborn
    def contents(self, limit=None):
        """Returns a dataframe containing the top <limit> rows in the cache.
        Defaults to all rows."""

        with self.Session() as session:
            stmt = sa.select(self.CacheModel).limit(limit)
            df = pd.read_sql(stmt, session.connection())
        
        return df
    
    def wipe(self):
        """Wipes this cache by dropping the table and rerunning setup."""
        self.CacheModel.__table__.drop(self.engine)
        self.setup()
    
    @stubborn
    def __setitem__(self, key, val):
        """Saves data in cache using the provided key.
        If a max age is also provided, i.e. with my_cache[my_key, 60], the cached data will default to expire
        after that number of seconds."""
        
        # Unpack key in case a max age is provided
        if isinstance(key, tuple):
            key, max_age_seconds = key
            expires = config.epoch() + max_age_seconds
        else:
            expires = None
        
        # Prepare data for caching
        data = self.save_hook(val)
        with self.Session() as session:
            row = self.CacheModel(
                key=key,
                data=data,
                expires=expires
            )
            
            session.merge(row)  # save/update row by primary key
            session.commit()
        #
    
    
    @stubborn
    def __getitem__(self, key):
        """Gets cached data by key.
        If a max age is also provided, i.e. with my_cache[my_key, max_age], cached data will only be returned
        if it is at most max_age seconds old. If no max_age is provided, cached data is considered expired based
        on the expiration column. If that is none, data of arbitrary age might be returned."""
        
        # Unpack key in case a max age is provided
        if isinstance(key, tuple):
            key, max_age_seconds = key
        else:
            max_age_seconds = None
        
        with self.Session() as session:
            # Use the provided key for lookup
            hit = session.get(self.CacheModel, key)
            
            # Return None on missing keys
            if not hit:
                return None
            
            # Determine staleness based on 1) specified max age and 2) expiration column, in said priority
            if max_age_seconds is None:
                # If no max age is provided to getter, base staleness on any max age stored in the cache
                stale = hit.expires is not None and hit.expires <= config.epoch()
            else:
                # If a timestamp is provided, override and expiration time stored at cache time
                stale = hit.timestamp + max_age_seconds <= config.epoch()
            
            if stale:
                return None
        
        # Run loading hook to recover original data (e.g. unpickling)    
        res = self.load_hook(hit.data)
        
        return res
    
    @stubborn
    def __delitem__(self, key):
        with self.Session() as session:
            rec = session.get(self.CacheModel, key)
            session.delete(rec)
            session.commit()


class Cache:
    """Cache for persisting data between python sessions.
    This class can be used as a decorator, to store results given a function and argument combination.
    Works by automatically determining a key from the wrapped function and arguments, then storing cached
    data under that key.
    Example:
    
    Cache()
    def some_slow_function(foo, bar=0):
        pass  # code here
    
    """
    
    def __init__(self, db_path: Path=None, serialize: bool=None, max_age_seconds=3600, table_name: str=None):
        self.backend = Backend(db_path=db_path, serialize=serialize, table_name=table_name)
        self.max_age_seconds = max_age_seconds
  
    @staticmethod
    def _shorten(val, max_chars=20) -> str:
        res = str(val)
        if len(res) > max_chars:
            res = res[:max_chars] + "<...>"
        
        return res
  
    def __call__(self, func: Callable):
        """This is the decorator part."""
        
        # Determine a hash for the function. Uses its bytecode to ignore e.g. comment updates
        instructions = dis.Bytecode(func).dis()
        func_hash = hashlib.md5(instructions.encode("utf8")).hexdigest()
        
        sig = inspect.signature(func)
        
        @wraps(func)
        def wrapped(*args, **kwargs):
            # Make a tuple of arguments. Equivalent arg/kwargs combinations produce the same tuple
            bound_args = sig.bind(*args, **kwargs)
            bound_args.apply_defaults()
            arg_key = tuple(list(bound_args.args) + [v for _, v in sorted(bound_args.kwargs.items())])
            
            # Make a key from the combination of function + argument hash
            key = f"{func_hash}_{arg_key}"
            cached = self.backend[key, self.max_age_seconds]
            
            # Attempt to lookup cached data. If no fresh data, (re)compute results and cache
            if cached is None:
                res = func(*args, **kwargs)
                logging.debug(f"Cache missed - caching {self._shorten(res)}")
                self.backend[key] = res
            else:
                res = cached
                logging.debug(f"Cache hit: {self._shorten(res)}")
            
            return res
        
        return wrapped
    #


@Cache()
def fun(a, *args, b=42, c=None, **kwargs):
    """hmm..."""
    return a+b


if __name__ == '__main__':
    logging.basicConfig(level=logging.DEBUG)
    
    db_path = config.local_data_dir / "cache.db"
    backend = Backend(serialize=False)

    k = "iamakey"
    backend[k] = "ehrmagerd content!"
    
    
    #res = fun(18, 1337, b=1, whatevs=-1)
    #print(res)