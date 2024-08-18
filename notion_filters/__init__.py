from .checkbox import CheckboxFilter
from .base import AndFilter, OrFilter
from .date import DateFilter
from .files import FilesFilter
from .formula import FormulaFilter
from .multi_select import MultiSelectFilter
from .number import NumberFilter
from .people import PeopleFilter
from .relation import RelationFilter
from .rich_text import RichTextFilter
from .rollup import RollupFilter
from .select import SelectFilter
from .status import StatusFilter
from .timestamp import TimestampFilter
from .unique_id import UniqueIDFilter


class Filter:
    """
    A class that contains all the filters available in Notion
    Usage example for simple filter: Filter.RichText("property_name").contains("value_to_contain")
    Usage example for complex filter: Filter.And(Filter.RichText("property_name").contains("value_to_contain"),
                                                 Filter.Number("property_name").greater_than(5))
    """
    Checkbox = CheckboxFilter
    Date = DateFilter
    Files = FilesFilter
    Formula = FormulaFilter
    MultiSelect = MultiSelectFilter
    Number = NumberFilter
    People = PeopleFilter
    Relation = RelationFilter
    RichText = RichTextFilter
    Rollup = RollupFilter
    Select = SelectFilter
    Status = StatusFilter
    Timestamp = TimestampFilter
    UniqueID = UniqueIDFilter
    And = AndFilter
    Or = OrFilter
