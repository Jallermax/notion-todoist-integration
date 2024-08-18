from .base import FilterBase


class NumberFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "number"

    def greater_than(self, value: float):
        self.condition = {"greater_than": value}
        return self

    def greater_than_or_equal_to(self, value: float):
        self.condition = {"greater_than_or_equal_to": value}
        return self

    def less_than(self, value: float):
        self.condition = {"less_than": value}
        return self

    def less_than_or_equal_to(self, value: float):
        self.condition = {"less_than_or_equal_to": value}
        return self

    def equals(self, value: float):
        self.condition = {"equals": value}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
