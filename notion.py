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

    _LOG.info(f"Received {len(data)} records")
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
    return res.json()


def update_page(page_id, **kwargs):
    url = f"https://api.notion.com/v1/pages/{page_id}"

    properties = {"properties": kwargs}
    res = requests.patch(url, headers=headers, json=properties)
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
    def rich_text_page_mention(page_id: str):
        return {"rich_text": [{"mention": {"page": {"id": page_id}}}]}

    @staticmethod
    def date(value: str):
        return {"date": {"start": value}}

    @staticmethod
    def relation(page_id: str):
        return {"relation": [{"id": page_id}]}

    @staticmethod
    def checkbox(value: bool):
        return {"checkbox": value}

    @staticmethod
    def select(name):
        return {"select": {"name": name}}

    @staticmethod
    def heading_block(text, header_num=3):
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
    def paragraph_blocks(*text_blocks):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "text": list({"type": "text", "text": {"content": n}} for n in list(*text_blocks))
            }
        }

    @staticmethod
    def paragraph_mention_blocks(*page_ids):
        return {
            "object": "block",
            "type": "paragraph",
            "paragraph": {
                "text": list({"mention": {"page": {"id": p_id}}} for p_id in page_ids)
            }
        }


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
