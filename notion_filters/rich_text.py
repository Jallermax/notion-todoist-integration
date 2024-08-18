from .base import FilterBase


class RichTextFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "rich_text"

    def contains(self, value: str):
        self.condition = {"contains": value}
        return self

    def does_not_contain(self, value: str):
        self.condition = {"does_not_contain": value}
        return self

    def equals(self, value: str):
        self.condition = {"equals": value}
        return self

    def does_not_equal(self, value: str):
        self.condition = {"does_not_equal": value}
        return self

    def starts_with(self, value: str):
        self.condition = {"starts_with": value}
        return self

    def ends_with(self, value: str):
        self.condition = {"ends_with": value}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
