"""
SQLite 데이터베이스 연결 및 세션 관리 (v13 스키마)
"""
import os
from sqlalchemy import create_engine, Column, Integer, String, Text
from sqlalchemy.orm import sessionmaker, declarative_base, Session

Base = declarative_base()


class BudgetItem(Base):
    __tablename__ = 'budget_items'

    id = Column(Integer, primary_key=True, autoincrement=True)
    parent_id = Column(Integer, nullable=True)
    depth = Column(Integer, nullable=False)
    dept = Column(Text, default='')
    policy = Column(Text, default='')
    unit = Column(Text, default='')
    detail = Column(Text, default='')
    item_name = Column(Text, default='')
    label = Column(Text, default='')
    calc_name = Column(Text, default='')
    budget_amount = Column(Integer, default=0)
    finance_national = Column(Integer, default=0)
    finance_province = Column(Integer, default=0)
    finance_county = Column(Integer, default=0)
    finance_special = Column(Integer, default=0)
    finance_balance = Column(Integer, default=0)
    finance_other = Column(Integer, default=0)
    page = Column(Text, default='')
    budget_original = Column(Integer, default=0)
    budget_modified = Column(Integer, default=0)
    status = Column(Text, default='')
    carryover = Column(Integer, default=0)
    carryover_national = Column(Integer, default=0)
    carryover_province = Column(Integer, default=0)
    carryover_county = Column(Integer, default=0)
    carryover_special = Column(Integer, default=0)
    carryover_balance = Column(Integer, default=0)
    carryover_other = Column(Integer, default=0)
    summary_text = Column(Text, default='')


_engines: dict[str, any] = {}
_SessionLocal: dict[str, any] = {}


def init_db(db_path: str = 'budget.db') -> None:
    abs_path = os.path.abspath(db_path)
    engine = create_engine(f'sqlite:///{abs_path}', echo=False)
    Base.metadata.create_all(engine)
    _engines[abs_path] = engine
    _SessionLocal[abs_path] = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db(db_path: str = 'budget.db') -> Session:
    abs_path = os.path.abspath(db_path)
    if abs_path not in _SessionLocal:
        init_db(db_path)
    return _SessionLocal[abs_path]()
