import json
import logging
import requests
import secrets

_LOG = logging.getLogger(__name__)

headers = {
    "Authorization": "Bearer " + secrets.NOTION_TOKEN,
    "Notion-Version": "2021-05-13"
}


def read_database_metadata(database_id):
    url = f"https://api.notion.com/v1/databases/{database_id}"

    res = requests.get(url, headers=headers)
    process_response(res)
    return res.json()


def read_databases_list(**kwargs):
    url = "https://api.notion.com/v1/search"
    params = {"filter": {"property": {"object": "database"}}}
    params.update(kwargs)
    res = requests.get(url, headers=headers, json=params)
    process_response(res)
    return res.json()


def read_database(database_id, query=None, log_to_file=False):
    url = f"https://api.notion.com/v1/databases/{database_id}/query"

    if not query:
        res = requests.post(url, headers=headers)
    else:
        res = requests.post(url, headers=headers, json=query)
    if not process_response(res):
        return

    data = res.json()
    _LOG.info(f"Received {len(data['results'])} records")
    if log_to_file:
        with open('test/db.json', 'w', encoding='utf8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def create_page(parent_id, children=None, **kwargs):
    url = f"https://api.notion.com/v1/pages/"

    page_properties = {}
    page_properties.update(kwargs)
    params = {"parent": {"database_id": parent_id}, "properties": page_properties}
    if children:
        params['children'] = children
    res = requests.post(url, headers=headers, json=params)
    process_response(res)


def update_page(page_id, **kwargs):
    url = f"https://api.notion.com/v1/pages/{page_id}"

    properties = {}
    properties.update(kwargs)
    res = requests.patch(url, headers=headers, json={"properties": properties})
    process_response(res)


def process_response(res, log=True):
    if res.status_code != 200:
        _LOG.error(f"Got response for {res.request.method} {res.request.url}")
        _LOG.error(f"Error message: {json.dumps(res.json(), ensure_ascii=False, indent=2)}")
        return False
    if log:
        # _LOG.debug(json.dumps(res.json(), ensure_ascii=False, indent=2))
        _LOG.debug(res.json())
    return True


class PropertyFormatter:

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
