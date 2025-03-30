from __future__ import annotations
import datetime
import decimal
import logging 
logger = logging.getLogger(__name__)
import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.orm.decl_api import DeclarativeMeta
from threading import RLock


# Incredibly, this doesn't seem to be built into sqlalchemy
_type_py2sql_dict = {
    int: sa.sql.sqltypes.BigInteger,
    str: sa.sql.sqltypes.Unicode,
    float: sa.sql.sqltypes.Float,
    decimal.Decimal: sa.sql.sqltypes.Numeric,
    datetime.datetime: sa.sql.sqltypes.DateTime,
    bytes: sa.sql.sqltypes.LargeBinary,
    bool: sa.sql.sqltypes.Boolean,
    datetime.date: sa.sql.sqltypes.Date,
    datetime.time: sa.sql.sqltypes.Time,
    datetime.timedelta: sa.sql.sqltypes.Interval,
    list: sa.sql.sqltypes.ARRAY,
    dict: sa.sql.sqltypes.JSON
}


ID_COLNAME = "id"
TIMESTAMP_COLNAME = "timestamp"

DEFAULT_TIME_FACTORY = sa.func.current_timestamp

def _make_sql_columns_from_types(**kwargs):
    res = {
        ID_COLNAME: sa.Column(sa.Integer, primary_key=True, autoincrement=True),
        TIMESTAMP_COLNAME:  sa.Column(sa.DateTime, server_default=DEFAULT_TIME_FACTORY(), nullable=False)
    }
    
    for name, type_ in kwargs.items():
        assert isinstance(type_, type)
        sql_type = _type_py2sql_dict[type_]
        col = sa.Column(sql_type)
        res[name] = col
    
    return res


def make_sql_columns_from_values_dict(d: dict) -> dict:
    """Takes a dict mapping names to values.
    Returns a similar dict mapping names to an appropriate SQLAlchemy column type, in addition
    to columns for id and timestamp for storing data."""
    
    d = {name: type(value) for name, value in d.items()}
    res = _make_sql_columns_from_types(**d)
    return res


def make_model(Base: DeclarativeMeta, table_name: str, **columns):
    """Creates a model class (SQLAlchemy declarative base thingy) for storing data.
    Base is the base type, usually created with sqlalchemy.orm.declarative_base()
    table_name is the name to be used for the table.
    columns is additional keywords with column names as keys and sqlalchemy column instances
    as values."""

    model = type(
        'DataModel',  # Name of the model class 
        (Base,),  # Inherit from the provided Base
        {
            '__tablename__': table_name,  # Set the table name
            **columns  # set the columns (similar to declaring them in a class body inheriting from Base)
        }
    )
    
    return model


class TableGateway:
    def __init__(self, table_name: str, db_gateway: DatabaseGateway):
        self.table_name = table_name
        self.db_gateway = db_gateway
        self._model = None
        logger.debug(f"Gateway created for {self.table_name} @ {self.db_gateway.url}")
    
    def table_exists(self) -> bool:
        inspector = sa.inspect(self.db_gateway.engine)
        return self.table_name in inspector.get_table_names()

    def now(self):
        with self.db_gateway.engine.connect() as connection:
            res = connection.execute(
                sa.select(
                    DEFAULT_TIME_FACTORY()
                    )
                ).scalar()
            return res

    def _get_model(self, data: dict):
        """Given a dictionary of data, returns a model for storing the data.
        An appropriate model is inferred from the provided data."""
        
        if self._model is None:
            columns = make_sql_columns_from_values_dict(data)
            self._model = make_model(
                Base=self.db_gateway.Base,
                table_name=self.table_name,
                **columns
            )
            
            if not self.table_exists():
                self._model.__table__.create(self.db_gateway.engine, checkfirst=True)
            #

        return self._model

    def save(self, data: dict):
        model = self._get_model(data=data)
        with self.db_gateway.Session() as session:
            row = model(**data)
            session.merge(row)
            session.commit()
        #

    def contents(self, limit=None) -> pd.DataFrame|None:
        """Returns a dataframe containing the top <limit> rows in the cache.
        Defaults to all rows."""
        
        if not self.table_exists():
            return None
        
        table = sa.Table(
            self.table_name,
            sa.MetaData(),
            autoload_with=self.db_gateway.engine
        )

        with self.db_gateway.engine.connect() as connection:
            stmt = table.select().limit(limit)
            result = connection.execute(stmt)
            # Convert the result to a DataFrame
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        return df

    def drop(self):
        #IF OBJECT_ID('dbo.Scores', 'U') IS NOT NULL DROP TABLE dbo.Scores; 
        drop_statement = sa.text(f"DROP TABLE IF EXISTS {self.table_name}")
        with self.db_gateway.engine.connect() as connection:
            connection.execute(drop_statement)
        #
    
    @property
    def _base_model(self):
        return make_model(Base=declarative_base(), table_name=self.table_name)
    
    def _table(self):
        table = sa.Table(
            self.table_name,
            sa.MetaData(),
            autoload_with=self.db_gateway.engine
        )
        return table
    
    def seconds_since_last_update(self):
        table = self._table()
        
        # Execute the query
        with self.db_gateway.engine.connect() as connection:
            ts = connection.execute(
                sa.select(sa.func.max(getattr(table.columns, TIMESTAMP_COLNAME)))
            ).scalar()
            
        age = self.now() - ts
        res = age.seconds

        return res



class DatabaseGateway:
    """Handles engines and autogeneration of data models for saving scraped stuff."""
    
    _lock = RLock()  # Just to make sure threading doesn't cause problems
    _engines = dict()

    def __init__(self, url: str, **engine_kwargs):
        """url is the URL for the DB
        table_name_or_model can be a table name (str) or ORM data model class. (declarative_base() subclass)"""

        self.url = url
        self.Base = declarative_base()  # setup a base thingy to be used if we need to autogenerate a model
        self._checked_models = set([])  # REMOVE!!!!!
        self._Session = None
        self._tables = dict()
        self._engine = None
        self._engine_kwargs = dict() if not engine_kwargs else engine_kwargs
    
    @property
    def engine(self) -> sa.Engine:
        """Returns a connection engine for the provided URL. Creates one if none exists yet."""
        
        with self._lock:
            if not self._engine:
                self._engine = sa.create_engine(self.url, **self._engine_kwargs)
                logger.debug(f"Created engine for {self.url}.")
            return self._engine
        #

    @classmethod
    def dispose_all(cls):
        """Dispose all engines"""
        with cls._lock:
            for engine in cls._engines.values():
                engine.dispose()
            cls._engines = dict()
        #
    
    @classmethod
    def recreate(cls, url: str=None):
        with cls._lock:
            urls = list(cls._engines.keys())
            cls.dispose_all()
            for url in urls:
                _ = cls.get_engine(url=url)
            #
    
    def __getitem__(self, key):
        return self._tables[key]
    
    @property
    def Session(self):
        if not self._Session:
            self._Session = sessionmaker(bind=self.engine)
        return self._Session

    def add_table(self, table_name: str) -> TableGateway:
        """Adds a table gateway with the provided name, registers it to the database gateway, and returns it"""
        table_gateway = TableGateway(table_name=table_name, db_gateway=self)
        self._tables[table_name] = table_gateway
        return table_gateway


if __name__ == '__main__':
    from gretchen import logger as pkglog
    logging.basicConfig(level=logging.ERROR)
    pkglog.setLevel(logging.DEBUG)
    logging.getLogger(__name__).setLevel(logging.DEBUG)
    
    from gretchen.config import db_path
    db_url = f'sqlite:///{db_path}'
    
    db_gateway = DatabaseGateway(url=db_url, echo=False)
    
    s = "hmm"
    t = db_gateway.add_table(s)
    
    t.drop()
    df = t.contents()
    #print(df)
    
    
    d = dict(a=42, b="foo")
    t.save(d)
    
    df2 = t.contents()
    #print(df2)
    
    delta = t.seconds_since_last_update()
    print(delta)