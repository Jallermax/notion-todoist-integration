from .base import FilterBase


class FilesFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "files"

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self
