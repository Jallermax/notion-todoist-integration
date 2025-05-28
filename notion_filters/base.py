import json
from abc import ABC, abstractmethod
from typing import Any, Union


class FilterBase(ABC):
    def __init__(self, property_name: str):
        self.property_name = property_name
        self.condition = {}

    def __str__(self) -> str:
        return json.dumps(self.to_dict())

    def __dict__(self) -> dict[str, Any]:
        return self.to_dict()

    def __repr__(self) -> str:
        return (f"{self.__class__.__name__}(property_name={self.property_name},"
                f" property_type={self._get_property_type()}, condition={self.condition})")

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the FilterBase to a dictionary format required by the Notion API.
        """
        return {
            "filter": {
                "property": self.property_name,
                self._get_property_type(): self.condition
            }
        }

    @abstractmethod
    def _get_property_type(self) -> str:
        """
        Return the type of the property based on the filter type.
        """
        pass


class AndFilter:
    def __init__(self, *filters: Union[FilterBase, 'OrFilter', 'AndFilter']):
        """
        Initialize an AndFilter.

        :param filters: A list of filters to combine with AND logic.
        """
        self.filters = filters

    def __str__(self) -> str:
        return str(self.to_dict())

    def __dict__(self) -> dict[str, Any]:
        return self.to_dict()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(filters={self.filters})"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the AndFilter to a dictionary format required by the Notion API.

        :return: A dictionary representing the AND filter.
        """
        return {
            "filter": {
                "and": [filter_.to_dict()["filter"] for filter_ in self.filters]
            }
        }


class OrFilter:
    def __init__(self, *filters: Union[FilterBase, 'AndFilter', 'OrFilter']):
        """
        Initialize an OrFilter.

        :param filters: A list of filters to combine with OR logic.
        """
        self.filters = filters

    def __str__(self) -> str:
        return str(self.to_dict())

    def __dict__(self) -> dict[str, Any]:
        return self.to_dict()

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(filters={self.filters})"

    def to_dict(self) -> dict[str, Any]:
        """
        Convert the OrFilter to a dictionary format required by the Notion API.

        :return: A dictionary representing the OR filter.
        """
        return {
            "filter": {
                "or": [filter_.to_dict()["filter"] for filter_ in self.filters]
            }
        }
