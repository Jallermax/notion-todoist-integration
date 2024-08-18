from .base import FilterBase


class CheckboxFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "checkbox"

    def equals(self, value: bool):
        self.condition = {"equals": value}
        return self

    def does_not_equal(self, value: bool):
        self.condition = {"does_not_equal": value}
        return self
