from dataclasses import dataclass


@dataclass(frozen=True)
class Resource:
    resource_type: str
    name: str
    resource_id: int = None
