from .base import FilterBase


class UniqueIDFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "unique_id"

    def equals(self, value: int):
        self.condition = {"equals": value}
        return self

    def does_not_equal(self, value: int):
        self.condition = {"does_not_equal": value}
        return self

    def greater_than(self, value: int):
        self.condition = {"greater_than": value}
        return self

    def less_than(self, value: int):
        self.condition = {"less_than": value}
        return self

    def greater_than_or_equal_to(self, value: int):
        self.condition = {"greater_than_or_equal_to": value}
        return self

    def less_than_or_equal_to(self, value: int):
        self.condition = {"less_than_or_equal_to": value}
        return self
