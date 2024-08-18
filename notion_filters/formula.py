from .rich_text import RichTextFilter
from .number import NumberFilter
from .date import DateFilter
from .checkbox import CheckboxFilter
from .base import FilterBase


class FormulaFilter(FilterBase):
    def _get_property_type(self) -> str:
        return "formula"

    def checkbox(self, filter_condition: CheckboxFilter):
        self.condition = {"checkbox": filter_condition.condition}
        return self

    def date(self, filter_condition: DateFilter):
        self.condition = {"date": filter_condition.condition}
        return self

    def number(self, filter_condition: NumberFilter):
        self.condition = {"number": filter_condition.condition}
        return self

    def string(self, filter_condition: RichTextFilter):
        self.condition = {"string": filter_condition.condition}
        return self
