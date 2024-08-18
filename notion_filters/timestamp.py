from .date import DateFilter
from .base import FilterBase


class TimestampFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "timestamp"

    def created_time(self, filter_condition: DateFilter):
        self.condition = {"created_time": filter_condition.condition}
        return self

    def last_edited_time(self, filter_condition: DateFilter):
        self.condition = {"last_edited_time": filter_condition.condition}
        return self
