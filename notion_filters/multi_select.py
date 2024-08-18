from .base import FilterBase


class MultiSelectFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "multi_select"

    def contains(self, value: str):
        self.condition = {"contains": value}
        return self

    def does_not_contain(self, value: str):
        self.condition = {"does_not_contain": value}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
