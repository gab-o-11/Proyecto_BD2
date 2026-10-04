from dataclasses import dataclass, field
from typing import List, Optional

class Node:
    def accept(self, visitor):
        return getattr(visitor, "visit_" + type(self).__name__)(self)


@dataclass(frozen=True)
class Point(Node):
    latitude: float
    longitude: float


@dataclass(frozen=True)
class Distance(Node):
    left: str | Point
    right: str | Point
    metric: str = "haversine"


@dataclass(frozen=True)
class Polygon(Node):
    vertices: tuple[Point, ...]


@dataclass(frozen=True)
class Intersection(Node):
    column: str
    polygon: Polygon


def expression_columns(expression):
    if isinstance(expression, Distance):
        return [operand for operand in (expression.left, expression.right) if isinstance(operand, str)]
    return [expression] if isinstance(expression, str) else []

@dataclass(frozen=True)
class ColumnRef(Node):
    name: str


@dataclass
class Compare(Node):
    column: str | Distance
    op: str
    value: str


@dataclass(frozen=True)
class And(Node):
    conditions: tuple


@dataclass(frozen=True)
class Or(Node):
    conditions: tuple


@dataclass(frozen=True)
class Not(Node):
    condition: Node


@dataclass(frozen=True)
class Between(Node):
    column: str | Distance
    low: object
    high: object
    negated: bool = False


@dataclass(frozen=True)
class InList(Node):
    column: str | Distance
    values: tuple
    negated: bool = False


@dataclass(frozen=True)
class Like(Node):
    column: str
    pattern: str
    negated: bool = False


@dataclass(frozen=True)
class IsNull(Node):
    column: str | Distance
    negated: bool = False


def condition_columns(condition):
    if condition is None:
        return []
    if isinstance(condition, (And, Or)):
        return [c for parte in condition.conditions for c in condition_columns(parte)]
    if isinstance(condition, Not):
        return condition_columns(condition.condition)
    if isinstance(condition, Intersection):
        return [condition.column]
    columnas = expression_columns(condition.column)
    if isinstance(getattr(condition, "value", None), ColumnRef):
        columnas.append(condition.value.name)
    return columnas

@dataclass
class Select(Node):
    table: str
    columns: Optional[List[str]]
    where: Compare | Intersection | None = None
    group_by: Optional[str] = None
    order_by: str | Distance | None = None
    aggregates: Optional[List[tuple]] = None
    order_desc: bool = False
    table_alias: Optional[str] = None
    joins: List["Join"] = field(default_factory=list)
    projection: Optional[List[str]] = None
    limit: Optional[int] = None


def aggregate_name(function, column):
    return "conteo" if function == "count" and column is None else function + "_" + str(column)


@dataclass
class Join:
    table: str
    left_column: str
    right_column: str
    alias: Optional[str] = None

@dataclass
class Insert(Node):
    table: str
    values: List[str]
    columns: Optional[List[str]] = None
    more_values: Optional[List[List[str]]] = None

    def all_values(self):
        return [self.values] + list(self.more_values or [])

@dataclass
class Delete(Node):
    table: str
    where: Compare | Intersection

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
class CreateIndex(Node):
    name: str
    table: str
    column: str
    kind: Optional[str] = None


@dataclass
class DropTable(Node):
    table: str
    if_exists: bool = False


@dataclass
class DropIndex(Node):
    name: str
    if_exists: bool = False


@dataclass
class Explain(Node):
    statement: Node
    analyze: bool = False


@dataclass
class Analyze(Node):
    table: str


@dataclass
class Update(Node):
    table: str
    assignments: List[tuple]
    where: Compare | Intersection | None = None
