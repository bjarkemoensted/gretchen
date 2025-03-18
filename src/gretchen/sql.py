from dataclasses import dataclass
import sqlalchemy as sa
from sqlalchemy.orm import declarative_base, sessionmaker

from gretchen.config import db_path

# Define the base class
Base = declarative_base()

# Map common builtin datatypes to corresponding sql types
python_type2sqlalchemy = {
    str: sa.String,
    int: sa.Integer
}


def infer_column(python_type: type, nullable=True) -> sa.Column:
    """Takes a python type (str, int, etc) and returns an SQLAlchemy column for it."""

    sql_type = python_type2sqlalchemy[python_type]
    col = sa.Column(sql_type, nullable=nullable)
    return col


@dataclass
class default_columns:
    id = sa.Column(sa.Integer, primary_key=True, autoincrement=True)
    timestamp = sa.Column(sa.DateTime, default=sa.func.now(), nullable=False)


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
