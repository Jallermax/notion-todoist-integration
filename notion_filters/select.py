from .base import FilterBase


class SelectFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "select"

    def equals(self, value: str):
        self.condition = {"equals": value}
        return self

    def does_not_equal(self, value: str):
        self.condition = {"does_not_equal": value}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
