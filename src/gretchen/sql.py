import logging 
logger = logging.getLogger(__name__)
import pandas as pd
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, Mapped, sessionmaker
from sqlalchemy.orm.decl_api import DeclarativeMeta
from threading import RLock

from gretchen.config import db_path

# Define the base class
Base = declarative_base()


def _make_sql_columns_from_types(**kwargs):
    res = dict(
        id = sa.Column(sa.Integer, primary_key=True, autoincrement=True),
        timestamp = sa.Column(sa.DateTime, default=sa.func.now(), nullable=False)
    )
    for name, type_ in kwargs.items():
        assert isinstance(type_, type)
        col = Mapped[type_]
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


class engine_manager:
    """Helper class for creating connection engines, or reusing if an engine has already been
    created for a given URL"""
    
    _lock = RLock()  # Just to make sure threading doesn't cause problems
    _engines = dict()

    @classmethod
    def get_engine(cls, url: str) -> sa.Engine:
        """Returns a connection engine for the provided URL. Creates one if none exists yet."""
        with cls._lock:
            if url not in cls._engines:
                cls._engines[url] = sa.create_engine(url)
                logger.debug(f"Created engine for {url}.")
            return cls._engines[url]
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
        #
    #


class Gateway:
    """Handles engines and autogeneration of data models for saving scraped stuff."""

    def __init__(self, url: str, table_name: str):
        """url is the URL for the DB
        table_name_or_model can be a table name (str) or ORM data model class. (declarative_base() subclass)"""

        self.url = url
        self.table_name = table_name
        
        self._base = declarative_base()  # setup a base thingy to be used if we need to autogenerate a model
        self._checked_models = set([])
        self._Session = None
    
    @property
    def engine(self) -> sa.Engine:
        return engine_manager.get_engine(self.url)
    
    @property
    def Session(self):
        if not self._Session:
            self._Session = sessionmaker(bind=self.engine)
        return self._Session
    
    def _check_model(self, model: DeclarativeMeta, only_once=True):
        """Helper method for ensuring that a table has been created. Might check columns in the future"""
        
        if only_once and model in self._checked_models:
            return
        
        logger.debug(f"Checking table {model.__tablename__} is setup at {self.url}")
        model.metadata.create_all(self.engine)
        self._checked_models.add(model)
    
    def _get_model(self, data: dict):
        """Given a dictionary of data, returns a model for storing the data.
        An appropriate model is inferred from the provided data."""
        
        columns = make_sql_columns_from_values_dict(data)
        model = make_model(Base=self._base, table_name=self.table_name, **columns)
        
        self._check_model(model=model)
        
        return model

    def save(self, data: dict):
        model = self._get_model(data=data)
        with self.Session() as session:
            row = model(**data)
            session.add(row)
            session.commit()
        #

    def contents(self, limit=None):
        """Returns a dataframe containing the top <limit> rows in the cache.
        Defaults to all rows."""
        
        metadata = sa.MetaData()
        table = sa.Table(self.table_name, metadata, autoload_with=self.engine)

        with engine.connect() as connection:
            stmt = table.select().limit(limit)
            result = connection.execute(stmt)
            # Convert the result to a DataFrame
            df = pd.DataFrame(result.fetchall(), columns=result.keys())
        
        return df
    

# Define the table model
class ExampleTable(Base):
    __tablename__ = 'example_table'
    
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    created_at = sa.Column(sa.DateTime, default=sa.func.now(), nullable=False)
    value = sa.Column(sa.String, nullable=False)


engine = sa.create_engine(f'sqlite:///{db_path}', echo=False)
Base.metadata.create_all(engine)
Session = sessionmaker(bind=engine)


def current_db_datetime(session=None):
    """Gets current datetime from the database."""

    if session is None:
        with Session() as session:
            return current_db_datetime(session=session)
        #
    
    res = session.query(sa.func.now()).scalar()
    return res


if __name__ == '__main__':
    now = current_db_datetime()
    print(now)
    
    print(ExampleTable)
    print(dir(ExampleTable))
    print(ExampleTable.value)
    print(type(Session))