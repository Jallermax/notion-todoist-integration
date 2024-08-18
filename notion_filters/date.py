from .base import FilterBase


class DateFilter(FilterBase):
    """
    A class that contains all the filters available for Date property type
    date is string in https://en.wikipedia.org/wiki/ISO_8601 format ("2021-10-15T12:00:00-07:00")
    Usage example: Filter.Date("Due").on_or_after("2021-01-01")
    """
    def _get_property_type(self) -> str:
        return "date"

    def after(self, date: str):
        self.condition = {"after": date}
        return self

    def before(self, date: str):
        self.condition = {"before": date}
        return self

    def on_or_after(self, date: str):
        self.condition = {"on_or_after": date}
        return self

    def on_or_before(self, date: str):
        self.condition = {"on_or_before": date}
        return self

    def equals(self, date: str):
        self.condition = {"equals": date}
        return self

    def is_empty(self, value: bool = True):
        self.condition = {"is_empty": value}
        return self

    def is_not_empty(self, value: bool = True):
        self.condition = {"is_not_empty": value}
        return self

    def next_month(self):
        self.condition = {"next_month": {}}
        return self

    def next_week(self):
        self.condition = {"next_week": {}}
        return self

    def next_year(self):
        self.condition = {"next_year": {}}
        return self

    def past_month(self):
        self.condition = {"past_month": {}}
        return self

    def past_week(self):
        self.condition = {"past_week": {}}
        return self

    def past_year(self):
        self.condition = {"past_year": {}}
        return self

    def this_week(self):
        self.condition = {"this_week": {}}
        return self
