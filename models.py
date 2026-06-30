"""
Pydantic v2 모델 — API Request/Response 스키마 (v13)
"""
from pydantic import BaseModel
from typing import Optional


class BudgetItemOut(BaseModel):
    id: int
    parent_id: Optional[int] = None
    depth: int
    dept: str = ''
    policy: str = ''
    unit: str = ''
    detail: str = ''
    item_name: str = ''
    label: str = ''
    calc_name: str = ''
    budget_amount: int = 0
    finance_national: int = 0
    finance_province: int = 0
    finance_county: int = 0
    finance_special: int = 0
    finance_balance: int = 0
    finance_other: int = 0
    page: str = ''
    budget_original: int = 0
    budget_modified: int = 0
    status: str = ''
    carryover: int = 0
    carryover_national: int = 0
    carryover_province: int = 0
    carryover_county: int = 0
    carryover_special: int = 0
    carryover_balance: int = 0
    carryover_other: int = 0
    summary_text: str = ''

    model_config = {'from_attributes': True}


class TreeItem(BaseModel):
    id: int
    parent_id: Optional[int] = None
    depth: int
    dept: str = ''
    policy: str = ''
    unit: str = ''
    detail: str = ''
    item_name: str = ''
    label: str = ''
    calc_name: str = ''
    budget_amount: int = 0
    budget_original: int = 0
    budget_modified: int = 0
    status: str = ''
    carryover: int = 0
    carryover_national: int = 0
    carryover_province: int = 0
    carryover_county: int = 0
    carryover_special: int = 0
    carryover_balance: int = 0
    carryover_other: int = 0
    summary_text: str = ''
    finance_national: int = 0
    finance_province: int = 0
    finance_county: int = 0
    finance_special: int = 0
    finance_balance: int = 0
    finance_other: int = 0
    carryover_continued: int = 0
    carryover_explicit: int = 0
    carryover_accident: int = 0
    page: str = ''
    children_count: int = 0
    has_children: bool = False
    children: list['TreeItem'] = []

    model_config = {'from_attributes': True}


class SummaryDept(BaseModel):
    dept: str
    total_budget: int = 0
    budget_original: int = 0
    budget_modified: int = 0
    status: str = ''
    carryover: int = 0
    carryover_national: int = 0
    carryover_province: int = 0
    carryover_county: int = 0
    carryover_special: int = 0
    carryover_balance: int = 0
    carryover_other: int = 0
    summary_text: str = ''
    finance_national: int = 0
    finance_province: int = 0
    finance_county: int = 0
    finance_special: int = 0
    finance_balance: int = 0
    finance_other: int = 0
    policy_count: int = 0
    unit_count: int = 0


class SummaryOut(BaseModel):
    total_budget: int = 0
    total_carryover: int = 0
    total_combined: int = 0
    dept_count: int = 0
    department_count: int = 0
    total_nodes: int = 0
    departments: list[SummaryDept] = []


class StatsOut(BaseModel):
    total_rows: int = 0
    total_dept: int = 0
    total_policy: int = 0
    total_unit: int = 0
    total_detail: int = 0
    total_item_name: int = 0
    total_label: int = 0
    total_budget: int = 0
    finance_national: int = 0
    finance_province: int = 0
    finance_county: int = 0
    finance_special: int = 0
    finance_balance: int = 0
    finance_other: int = 0


class SearchResult(BaseModel):
    items: list[BudgetItemOut] = []
    total_found: int = 0


class TreeResponse(BaseModel):
    items: list[TreeItem] = []
    total: int = 0


class HealthOut(BaseModel):
    status: str = 'ok'
    db_path: str = ''
    db_size_mb: float = 0.0
