from .base import FilterBase


class RelationFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "relation"

    def contains(self, uuid: str):
        self.condition = {"contains": uuid}
        return self

    def does_not_contain(self, uuid: str):
        self.condition = {"does_not_contain": uuid}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
