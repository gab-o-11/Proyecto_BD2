from dataclasses import dataclass
from typing import List, Optional

class Node:
    def accept(self, visitor):
        return getattr(visitor, "visit_" + type(self).__name__)(self)

@dataclass
class Compare(Node):
    column: str
    op: str
    value: str

@dataclass
class Select(Node):
    table: str
    columns: Optional[List[str]]
    where: Optional[Compare] = None
    group_by: Optional[str] = None
    order_by: Optional[str] = None
    aggregates: Optional[List[tuple]] = None

@dataclass
class Insert(Node):
    table: str
    values: List[str]

@dataclass
class Delete(Node):
    table: str
    where: Compare

@dataclass
class BeginTransaction(Node):
    pass

@dataclass
class EndTransaction(Node):
    pass

@dataclass
class ColumnDef(Node):
    name: str
    type: str
    size: Optional[int] = None
    primary_key: bool = False
    not_null: bool = False

@dataclass
class CreateTable(Node):
    table: str
    columns: List[ColumnDef]
    index_column: Optional[str] = None
    index_kind: Optional[str] = None


@dataclass
class Update(Node):
    table: str
    assignments: List[tuple]
    where: Optional[Compare] = None 