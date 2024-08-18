from .date import DateFilter
from .number import NumberFilter
from .base import FilterBase


class RollupFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "rollup"

    def any(self, filter_condition: FilterBase):
        self.condition = {
            "any": {filter_condition._get_property_type(): filter_condition.condition}
        }
        return self

    def every(self, filter_condition: FilterBase):
        self.condition = {
            "every": {filter_condition._get_property_type(): filter_condition.condition}
        }
        return self

    def none(self, filter_condition: FilterBase):
        self.condition = {
            "none": {filter_condition._get_property_type(): filter_condition.condition}
        }
        return self

    def date(self, date_filter: DateFilter):
        """
        Example: Filter.Rollup("Rollup3").date(Filter.Date("").on_or_after("2022-01-01"))
        """
        self.condition = {"date": date_filter.condition}
        return self

    def number(self, number_filter: NumberFilter):
        self.condition = {"number": number_filter.condition}
        return self
