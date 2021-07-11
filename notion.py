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

    _LOG.info(f"Received {len(data)} records for {database_id=}")
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
        # _LOG.debug(json.dumps(res.json(), ensure_ascii=False, indent=2))
        _LOG.debug(res.json())
    return True


def flatten_properties(*formatted_prop):
    flattened_props = []
    for fp in list(formatted_prop):
        if 'rich_text' in fp.keys():
            flattened_props.extend(fp['rich_text'])
        else:
            flattened_props.append(fp)
    return flattened_props


class PropertyFormatter:

    @staticmethod
    def title(value, **kwargs):
        value = value if isinstance(value, str) else str(value)
        return {"title": [{"text": {"content": value}}]}

    @staticmethod
    def rich_text(value, **kwargs):
        value = value if isinstance(value, str) else str(value)
        return {"rich_text": [{"text": {"content": value}}]}

    @staticmethod
    def rich_text_link(text, link, **kwargs):
        text = text if isinstance(text, str) else str(text)
        link = link if isinstance(link, str) else str(link)
        return {"rich_text": [{"text": {"content": text, "link": {"url": link}}}]}

    @staticmethod
    def rich_text_page_mention(page_id, **kwargs):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"rich_text": [{"mention": {"page": {"id": page_id}}}]}

    @staticmethod
    def date(value: str, **kwargs):
        return {"date": {"start": value}}

    @staticmethod
    def relation(page_id, **kwargs):
        page_id = page_id if isinstance(page_id, str) else str(page_id)
        return {"relation": [{"id": page_id}]}

    @staticmethod
    def checkbox(value, **kwargs):
        value = value if isinstance(value, bool) else bool(value)
        return {"checkbox": value}

    @staticmethod
    def select(name, **kwargs):
        name = name if isinstance(name, str) else str(name)
        return {"select": {"name": name}}

    @staticmethod
    def heading_block(text, header_num=3, **kwargs):
        if not [1, 2, 3].__contains__(header_num):
            _LOG.warning(f"Wrong {header_num=}. Should be one of [1, 2, 3]")
            header_num = 3
        block_type = "heading_" + str(header_num)
        return {
            "object": "block",
            "type": block_type,
            block_type: {
                "text": [{"type": "text", "text": {"content": text}}]
            }
        }

    @staticmethod
    def paragraph_block(*formatted_prop, **kwargs):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "text": flatten_properties(*formatted_prop)
            }
        }

    @staticmethod
    def paragraph_text_block(*text, **kwargs):
        rich_text_list = [PropertyFormatter.rich_text_link(txt, kwargs['link']) for txt in
                          text] if 'link' in kwargs.keys() else [PropertyFormatter.rich_text(txt) for txt in text]
        return PropertyFormatter.paragraph_block(*rich_text_list)

    @staticmethod
    def paragraph_mention_block(*page_ids, **kwargs):
        return PropertyFormatter.paragraph_block(
            *[PropertyFormatter.rich_text_page_mention(page_id) for page_id in page_ids])


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
