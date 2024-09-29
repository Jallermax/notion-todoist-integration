from datetime import datetime
import json
import logging
from functools import reduce

import pytz
import requests

import secrets
from notion_filters import Filter
from models import TodoistTask

_LOG = logging.getLogger(__name__)
LOCAL_TIMEZONE = pytz.timezone(secrets.T_ZONE)

headers = {
    "Authorization": "Bearer " + secrets.NOTION_TOKEN,
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json"
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


def read_database(database_id, raw_query=None, log_to_file=False, all_batch=True) -> list[dict]:
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
            return data
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


def get_synced_notion_tasks(database_id: str, todoist_id_prop: str) -> list[dict]:
    """Fetch tasks already linked in Notion"""
    query = Filter.RichText(todoist_id_prop).is_not_empty()
    return read_database(database_id, query)

def get_notion_tasks_before_time(db_id: str, todoist_id_text_prop: str, last_synced_date_prop: str,
                                 updated_tasks: list[TodoistTask], updated_events: dict[str, str]) -> list[dict]:
    entries_to_update = []
    for upd_tasks_chunk in chunks(updated_tasks, 100):
        by_task_id_and_after_sync_filter = [Filter.And(
            Filter.RichText(todoist_id_text_prop).equals(upd_id.task.id),
            Filter.Date(last_synced_date_prop).on_or_before(updated_events[upd_id.task.id])
        ) for upd_id in upd_tasks_chunk]
        query = Filter.Or(*by_task_id_and_after_sync_filter)
        entries_to_update.extend(read_database(db_id, query))
    return entries_to_update


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def fetch_task_by_todoist_id(database_id: str, todoist_id_prop: str, todoist_id: str) -> dict | None:
    """Fetch a single Notion task by Todoist Task ID."""
    query = Filter.RichText(todoist_id_prop).equals(todoist_id)
    tasks = read_database(database_id, query)
    return tasks[0] if tasks else None


def create_page(parent_id, *args, **kwargs):
    url = f"https://api.notion.com/v1/pages/"

    params = {"parent": {"database_id": parent_id}, "properties": kwargs}
    if args:
        params.update({"children": args})
    res = requests.post(url, headers=headers, json=params)
    return process_response(res), res.json()


def update_page(page_id, archive=False, **kwargs):
    url = f"https://api.notion.com/v1/pages/{page_id}"

    properties = {"properties": kwargs}
    if archive:
        properties['archived'] = True
    res = requests.patch(url, headers=headers, json=properties)
    return process_response(res), res.json()


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
    def id(page_id):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"id": page_id}

    @staticmethod
    def mention(page_id):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"mention": {"page": PropertyFormatter.id(page_id)}}

    """
    Primitive property object types
    """

    @staticmethod
    def date(value: str, localize=True, property_obj=True):
        # TODO use from dateutil.parser import parse (or Maya) instead and eject parsing method from formatting method
        if not value:
            return {"date": None} if property_obj else PropertyFormatter.text('')
        if localize:
            if len(value) == 20:
                value = LOCAL_TIMEZONE.localize(datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")).isoformat()
            elif len(value) == 19:
                value = LOCAL_TIMEZONE.localize(datetime.strptime(value, "%Y-%m-%dT%H:%M:%S")).isoformat()
        return {"date": {"start": value}} if property_obj else PropertyFormatter.text(value)

    @staticmethod
    def single_relation(page_id, property_obj=True):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return PropertyFormatter.relation([PropertyFormatter.id(page_id)], property_obj)

    @staticmethod
    def relation(formatted_props: list, property_obj=True):
        return {"relation": formatted_props} if property_obj else PropertyFormatter.paragraph_block(
            *[PropertyFormatter.mention(fp) for fp in formatted_props])

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
    def status(name, property_obj=True):
        name = name if isinstance(name, str) else str(name)
        return {"status": {"name": name}} if property_obj else PropertyFormatter.text(name)

    @staticmethod
    def title(formatted_props: list, property_obj=True):
        return {"title": formatted_props} if property_obj else PropertyFormatter.paragraph_block(*formatted_props)

    @staticmethod
    def rich_text(formatted_props: list, property_obj=True):
        return {"rich_text": formatted_props} if property_obj else PropertyFormatter.paragraph_block(*formatted_props)

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
    def generic_prop(page: dict, name: str, p_type=None):
        if not page['properties'].get(name):
            return None
        if not p_type:
            p_type = page['properties'][name]['type']
        return page['properties'][name][p_type]

    @staticmethod
    def rich_text(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'rich_text')
        return reduce(lambda x, y: x + y['plain_text'], prop, '') if prop else None

    @staticmethod
    def title(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'title')
        return reduce(lambda x, y: f"{x}{y['plain_text']}" if not y['href'] else f"{x}[{y['plain_text']}]({y['href']})",
                      prop, '') if prop else None

    @staticmethod
    def select(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'select')
        return prop['name'] if prop else None

    @staticmethod
    def status(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'status')
        return prop['name'] if prop else None

    @staticmethod
    def checkbox(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'checkbox')
        return str(prop) if isinstance(prop, bool) else None

    @staticmethod
    def relation(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'relation')
        return ','.join([r['id'] for r in prop]) if prop else None

    @staticmethod
    def date(page: dict, name: str):
        prop = PropertyParser.generic_prop(page, name, 'date')
        return prop['start'] if prop else None

    @staticmethod
    def date_wo_tz(page: dict, name: str):
        date_prop = PropertyParser.date(page, name)
        return date_prop[:19] if date_prop else None

    @staticmethod
    def formula_start_date(page: dict, name: str):
        prop = page['properties'][name]['formula']
        return prop['date']['start'] if prop else None
