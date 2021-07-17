import datetime
import json
import logging
import pytz
import requests
import secrets

_LOG = logging.getLogger(__name__)
LOCAL_TIMEZONE = pytz.timezone(secrets.T_ZONE)

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
    params = {"filter": {"object": "database"}}
    params.update(kwargs)
    res = requests.post(url, headers=headers, json=params)
    process_response(res)
    return res.json()


def read_database(database_id, raw_query=None, log_to_file=False, all_batch=True):
    data = []
    query = raw_query
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    has_more = True
    while has_more:
        if not query:
            res = requests.post(url, headers=headers)
        else:
            res = requests.post(url, headers=headers, json=query)
        if not process_response(res):
            return
        data.extend(res.json()['results'])
        has_more = all_batch and res.json()['has_more']
        if has_more:
            if not query:
                query = {}
            query.update({'start_cursor': res.json()['next_cursor']})

    _LOG.debug(f"Received {len(data)} records for {database_id=}")
    if log_to_file:
        with open('test/db.json', 'w', encoding='utf8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return data


def create_page(parent_id, *args, **kwargs):
    url = f"https://api.notion.com/v1/pages/"

    params = {"parent": {"database_id": parent_id}, "properties": kwargs}
    if args:
        params.update({"children": args})
    res = requests.post(url, headers=headers, json=params)
    process_response(res)
    return process_response(res), res.json()


def update_page(page_id, **kwargs):
    url = f"https://api.notion.com/v1/pages/{page_id}"

    properties = {"properties": kwargs}
    res = requests.patch(url, headers=headers, json=properties)
    process_response(res)


def process_response(res, log=False):
    if res.status_code != 200:
        _LOG.error(f"Got response for {res.request.method} {res.request.url}")
        _LOG.error(f"Error message: {json.dumps(res.json(), ensure_ascii=False, indent=2)}")
        return False
    if log:
        _LOG.debug(res.json())
    return True


class PropertyFormatter:

    """
    Primitive rich-text types
    """
    @staticmethod
    def text(text):
        text = text if isinstance(text, str) else str(text)
        return {"text": {"content": text}}

    @staticmethod
    def link(text, link):
        text = text if isinstance(text, str) else str(text)
        link = link if isinstance(link, str) else str(link)
        return {"text": {"content": text, "link": {"url": link}}}

    @staticmethod
    def mention(page_id):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"mention": {"page": {"id": page_id}}}

    """
    Primitive property object types
    """
    @staticmethod
    def date(value: str, localize=True, property_obj=True):
        # TODO use from dateutil.parser import parse (or Maya) instead and eject parsing method from formatting method
        if localize:
            if len(value) == 20:
                value = LOCAL_TIMEZONE.localize(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")).isoformat()
            elif len(value) == 19:
                value = LOCAL_TIMEZONE.localize(datetime.datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")).isoformat()
        return {"date": {"start": value}} if property_obj else PropertyFormatter.text(value)

    @staticmethod
    def relation(page_id, property_obj=True):
        # TODO page_id to tuple
        # lst = [pid if isinstance(page_id, str) else str(page_id) for pid in [page_id]]
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"relation": [{"id": page_id}]} if property_obj else PropertyFormatter.mention(page_id)

    @staticmethod
    def checkbox(value, property_obj=True):
        value = value if isinstance(value, bool) else bool(value)
        return {"checkbox": value} if property_obj else PropertyFormatter.text(value)

    @staticmethod
    def select(name, property_obj=True):
        name = name if isinstance(name, str) else str(name)
        return {"select": {"name": name}} if property_obj else PropertyFormatter.text(name)

    """
    Final prop types
    """
    @staticmethod
    def title(values: list, property_obj=True):
        return {"title": values} if property_obj else PropertyFormatter.paragraph_block(*values)

    @staticmethod
    def rich_text(values: list, property_obj=True):
        return {"rich_text": values} if property_obj else PropertyFormatter.paragraph_block(*values)

    @staticmethod
    def single_title(value, property_obj=True):
        return PropertyFormatter.title([PropertyFormatter.text(value)], property_obj)

    @staticmethod
    def single_rich_text(value, property_obj=True):
        return PropertyFormatter.rich_text([PropertyFormatter.text(value)], property_obj)

    @staticmethod
    def single_rich_text_link(text, link, property_obj=True):
        return PropertyFormatter.rich_text([PropertyFormatter.link(text, link)], property_obj)

    """
    Final block types
    """
    @staticmethod
    def heading_block(text, header_num=3):
        if header_num not in [1, 2, 3]:
            _LOG.warning(f"Wrong {header_num=}. Should be one of [1, 2, 3]")
            header_num = 3
        block_type = "heading_" + str(header_num)
        return {
            "object": "block",
            "type": block_type,
            block_type: {
                "text": [PropertyFormatter.text(text)]
            }
        }

    @staticmethod
    def paragraph_block(*formatted_prop):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "text": [*formatted_prop]
            }
        }

    @staticmethod
    def paragraph_text_block(*text):
        return PropertyFormatter.paragraph_block(*[PropertyFormatter.text(txt) for txt in text])


class PropertyParser:

    @staticmethod
    def generic_prop(action, name):
        return action['properties'][name][action['properties'][name]['type']]

    @staticmethod
    def rich_text(page: dict, name: str):
        prop = page['properties'][name]['rich_text']
        return None if len(prop) == 0 else prop[0]['plain_text']

    @staticmethod
    def title(page: dict, name: str):
        prop = page['properties'][name]['title']
        return None if len(prop) == 0 else prop[0]['plain_text']

    @staticmethod
    def formula_start_date(page: dict, name: str):
        prop = page['properties'][name]['formula']
        return None if len(prop) == 0 else prop['date']['start']
