import requests

from notion_api.databases import DatabasesManager
from notion_api.pages import PagesManager

NOTION_VERSION = "2021-05-13"
DEFAULT_API_VERSION = "v1"


class NotionApi(object):

    def __init__(self, token="", api_endpoint="https://api.notion.com", api_version=DEFAULT_API_VERSION):
        self.api_endpoint = api_endpoint
        self.api_version = api_version
        self.token = token
        self.session = requests.Session()

        self.databases = DatabasesManager(self)
        self.pages = PagesManager(self)
        self.property_formatter = PropertyFormatter()

    def get_api_url(self):
        return "{0}/{1}/".format(self.api_endpoint, self.api_version)

    def _request_headers(self, json=False):
        headers = {"Authorization": "Bearer {}".format(self.token),
                   "Notion-Version": NOTION_VERSION}
        if json:
            headers.update({"Content-Type": "application/json"})
        return headers

    def _get(self, call, url=None, **kwargs):
        """
        Sends an HTTP GET request to the specified URL, and returns the JSON
        object received (if any), or whatever answer it got otherwise.
        """
        if not url:
            url = self.get_api_url()

        response = self.session.get(url + call, headers=self._request_headers(), **kwargs)

        try:
            return response.json()
        except ValueError:
            return response.text

    def _post(self, call, url=None, **kwargs):
        """
        Sends an HTTP POST request to the specified URL, and returns the JSON
        object received (if any), or whatever answer it got otherwise.
        """
        if not url:
            url = self.get_api_url()

        response = self.session.post(url + call, headers=self._request_headers(kwargs is not None), json=kwargs)

        try:
            return response.json()
        except ValueError:
            return response.text

    def _patch(self, call, url=None, **kwargs):
        """
        Sends an HTTP PATCH request to the specified URL, and returns the JSON
        object received (if any), or whatever answer it got otherwise.
        """
        if not url:
            url = self.get_api_url()

        response = self.session.patch(url + call, headers=self._request_headers(kwargs is not None), json=kwargs)

        try:
            return response.json()
        except ValueError:
            return response.text


class PropertyFormatter(object):

    @staticmethod
    def title(value: str):
        return {"title": [{"text": {"content": value}}]}

    @staticmethod
    def rich_text(value: str):
        return {"rich_text": [{"text": {"content": value}}]}

    @staticmethod
    def rich_text_link(text: str, link: str):
        return {"rich_text": [{"text": {"content": text, "link": {"url": link}}}]}

    @staticmethod
    def date(value: str):
        return {"date": {"start": value}}

    @staticmethod
    def relation(page_id: str):
        return {"relation": [{"id": page_id}]}

    @staticmethod
    def checkbox(value: bool):
        return {"checkbox": value}
