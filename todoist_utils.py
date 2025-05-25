import ast
import logging
import re
from datetime import datetime, timedelta
from enum import Enum
from functools import reduce, lru_cache
from typing import Literal, Any
from tqdm import tqdm

import httpx
import pytz
from todoist_api_python.api import TodoistAPI
from synctodoist import TodoistAPI as SyncTodoistAPI
from synctodoist.managers import command_manager
from todoist_api_python.models import Task
from models import TodoistTask

import notion
import secrets
from notion import PropertyFormatter as PFormat
from notion import PropertyParser as PParser

_LOG = logging.getLogger(__name__)
LOCAL_TIMEZONE = pytz.timezone(secrets.T_ZONE)
MD_LINK_PATTERN = re.compile(r"\[([^]]*)]\((https?://[^\s)]+)\)|(https?://[^\s)]+)")
NOTION_LINK_PATTERN = re.compile(
    "(https://www.notion.so)?/"  # Optional Notion host
    "([a-zA-Z0-9-]+/)?"  # Optional Username
    "([a-zA-Z0-9-]+-)?"  # Optional Page name
    "([a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})"  # UUID
    "(\\?[a-zA-Z0-9%=\\-&]*)?"  # Optional Query parameters
)
NOTION_MARKDOWN_LINK_PATTERN = re.compile(
    "\\[(.+?)]\\((" + NOTION_LINK_PATTERN.pattern + ")\\)"
)
NOTION_SHORTHAND_LINK_PATTERN = re.compile(
    "\\[Notion]\\((" + NOTION_LINK_PATTERN.pattern + ")\\)"
)

ObjectType = Literal['item', 'project', 'note']
EventType = Literal['added', 'updated', 'deleted', 'completed', 'uncompleted']
ObjectEventType = Literal[
    'item:added', 'item:updated', 'item:deleted', 'item:completed', 'item:uncompleted',
    'project:added', 'project:updated', 'project:deleted', 'project:archived', 'project:unarchived',
    'note:added', 'note:updated', 'note:deleted']


class NoneStrategy(Enum):
    IGNORE = 'ignore'  # Ignore property value if it is not mapped
    VALUE_AS_IS = 'value-as-is'
    MAP_BY_NAME = 'map-by-name'  # Map property values (labels) to relations by identical name


@lru_cache
def load_todoist_to_notion_mapper() -> dict:
    # TODO add file parametric based on running scenario
    with open("mappings.json", "r", encoding="utf-8") as file:
        contents = file.read()
        return ast.literal_eval(contents)


def get_notion_formatter_mapper():
    # TODO move 'is_property' to pformat object
    return {'title': {'method': PFormat.single_title, 'parser': PParser.title, 'list_values': True},
            'rich_text': {'method': PFormat.single_rich_text, 'parser': PParser.rich_text, 'list_values': True},
            'relation': {'method': PFormat.single_relation, 'parser': PParser.relation, 'list_values': True},
            'select': {'method': PFormat.select, 'parser': PParser.select, 'list_values': False},
            'checkbox': {'method': PFormat.checkbox, 'parser': PParser.checkbox, 'list_values': False},
            'date': {'method': PFormat.date, 'parser': PParser.date_wo_tz, 'list_values': False},
            'status': {'method': PFormat.status, 'parser': PParser.status, 'list_values': False}
            }


def get_default_property_values():
    return {'type': 'rich_text'}


class TodoistToNotionMapper:

    def __init__(self):
        self.mappings = load_todoist_to_notion_mapper()
        self.todoist_api = TodoistAPI(token=secrets.TODOIST_TOKEN)

    def get_mapping(self, prop_key: str) -> dict:
        return self.mappings[prop_key]

    @lru_cache
    def get_label_tag_mapping(self, n_tags=None, todoist_tags_text_prop='Todoist Tags'):
        """
        Creates an id mapping between 'Todoist Tags' property in Notion Master Tag DB and Todoist Labels by name.
        :return: dict(todoist_label_id: notion_tag_page_id)
        """
        labels = {label.name: label.id for page in self.todoist_api.get_labels() for label in page}
        notion_master_tags = n_tags if n_tags else notion.read_database(secrets.MASTER_TAG_DB)
        notion_tags = {tag: page['id'] for page in notion_master_tags if
                       (tag := PParser.rich_text(page, todoist_tags_text_prop))}
        tag_mapping = {labels[key]: notion_tags[key] for key in notion_tags if key in labels}

        return tag_mapping

    def extract_parent_notion_uuid(self, task: TodoistTask) -> str | None:
        parent_id = task.task.parent_id
        if not parent_id:
            return None
        parent_task = self.todoist_api.get_task(parent_id)
        match = re.match(NOTION_MARKDOWN_LINK_PATTERN, parent_task.description)
        if match:
            return match.group(6)
        return None

    def map_property(self, task: TodoistTask, prop_name: str, db_metadata: dict, notion_props: dict = None,
                     child_blocks: list = None,
                     convert_md_links=False) -> tuple[dict[str, Any], list[dict]]:
        if isinstance(notion_props, type(None)):
            notion_props = {}
        if isinstance(child_blocks, type(None)):
            child_blocks = []

        _p, _c = self.parse_prop(task, prop_name, db_metadata, convert_md_links)
        if _p:
            notion_props.update(_p)
        if _c:
            child_blocks.append(_c) if not isinstance(_c, list) else child_blocks.extend(_c)
        return notion_props, child_blocks

    def parse_prop(self, task: TodoistTask, prop_key: str,
                   db_metadata: dict, convert_md_links: bool) -> tuple[dict[str, Any] | None, list[dict] | None]:
        if not task or not (todoist_val := deep_get_task_prop(task.task.to_dict(), prop_key)):
            return None, None

        value_list = todoist_val if isinstance(todoist_val, list) else [todoist_val]
        return self.parse_prop_list(value_list, prop_key, db_metadata, convert_md_links)

    def parse_prop_list(self, todoist_val_list, prop_key, db_metadata, convert_md_links
                        ) -> tuple[dict[str, Any], list[dict]]:
        props = self.parse_prop_list_to_dict(todoist_val_list, prop_key, db_metadata, convert_md_links)

        listed_props = {}
        listed_blocks = []
        for k, v in props.items():
            if len(v['values']) == 0:
                continue
            if k not in db_metadata.keys() or not v['formatter']:
                listed_blocks.append(PFormat.heading_block(k))
                listed_blocks.append(PFormat.paragraph_block(*v['values']))
            # Wrap if property is complex types
            elif db_metadata[k]['type'] == 'title':
                listed_props[k] = PFormat.title(v['values'])
            elif db_metadata[k]['type'] == 'rich_text':
                listed_props[k] = PFormat.rich_text(v['values'])
            elif db_metadata[k]['type'] == 'relation':
                listed_props[k] = PFormat.relation(v['values'])
            else:
                listed_props[k] = v['values'][0]

        return listed_props, listed_blocks

    def parse_prop_list_to_dict(self, todoist_val_list, prop_key, db_metadata, convert_md_links):
        """

        :param convert_md_links:
        :param db_metadata:
        :param prop_key:
        :param todoist_val_list:
        :return: example:
            {"POM": {"formatter": {"method": pformat.select, "list_values": False}, "values": [], "raw_val": []}}
        """
        label_mapper = self.get_label_tag_mapping() if prop_key == 'labels' else None
        props = {}
        mappings = self.get_mapping(prop_key)
        default_notion_values = mappings.get('default_values', {})
        for todoist_val in todoist_val_list:
            mapped_prop = mappings.get('values', {}).get(str(todoist_val), {})
            mapped_name = mapped_prop.get('name',
                                          default_notion_values.get('name',
                                                                    get_default_property_values().get('name',
                                                                                                      f"{prop_key}: ")))
            mapped_type = mapped_prop.get('type',
                                          default_notion_values.get('type', get_default_property_values().get('type')))
            mapped_value = mapped_prop.get('value')
            is_property = mapped_name and mapped_name in db_metadata.keys()
            formatter = get_notion_formatter_mapper().get(
                db_metadata[mapped_name]['type'] if is_property else mapped_type)

            current_prop = props.get(mapped_name, {})
            current_prop['formatter'] = formatter
            current_prop_values = current_prop.get('values', [])
            current_prop_raw_values = current_prop.get('raw_val', [])

            current_prop['values'] = current_prop_values
            current_prop['raw_val'] = current_prop_raw_values
            props[mapped_name] = current_prop

            # Parse mapped property value according to mapping file
            if mapped_value:
                current_prop_raw_values.append(mapped_value)
                if not formatter:
                    _LOG.warning(f"Formatter for {prop_key} value {todoist_val} is not defined.")
                    current_prop_values.append(PFormat.text(mapped_value))
                    continue
                elif formatter['method'] == PFormat.single_title:
                    current_prop_values.append(PFormat.text(mapped_value))
                    continue
                elif formatter['method'] == PFormat.single_rich_text:
                    current_prop_values.append(PFormat.text(mapped_value))
                    continue
                elif formatter['method'] == PFormat.single_relation:
                    current_prop_values.append(PFormat.id(mapped_value))
                    continue
                current_prop_values.append(formatter['method'](mapped_value, property_obj=is_property))
                continue

            # If property value is not mapped, ignore it
            if mappings.get('none_strategy') == NoneStrategy.IGNORE.value:
                _LOG.warning(f"Property {prop_key} value {todoist_val} is not mapped. Ignoring it.")
                continue

            if (mappings.get('none_strategy') == NoneStrategy.MAP_BY_NAME.value
                    and label_mapper and todoist_val in label_mapper):
                current_prop_values.append(PFormat.mention(label_mapper[todoist_val]))
                current_prop_raw_values.append(todoist_val)
                continue

            # If property value is not mapped, parse it according to NoneStrategy.VALUE_AS_IS and default_values rules
            if convert_md_links and formatter['method'] in \
                    [PFormat.single_title, PFormat.single_rich_text] and MD_LINK_PATTERN.search(todoist_val):
                rich_text_objects = parse_md_string_to_rich_text_objects(todoist_val)
                current_prop_values.extend(rich_text_objects)
                current_prop_raw_values.append(parse_md_string_to_notion_view(todoist_val))
                continue

            if 'link' in mappings.keys():
                link = mappings.get('link').format(todoist_val)
                current_prop_values.append(PFormat.link(todoist_val, link))
                continue

            if 'expression' in default_notion_values.keys():
                todoist_val = eval(default_notion_values.get('expression'), {'value': todoist_val})

            if formatter['method'] in [PFormat.single_title, PFormat.single_rich_text]:
                current_prop_values.append(PFormat.text(todoist_val))
            else:
                current_prop_values.append(formatter['method'](todoist_val, property_obj=is_property))

            current_prop_raw_values.append(todoist_val)
        return props

    def map_todoist_to_notion_task(self, task: TodoistTask, notion_db_metadata: dict[str, Any], parent_property: str
                                   ) -> tuple[dict[str, Any], list[dict]]:
        notion_props, child_blocks = {}, []
        # Map task properties to Notion properties or child blocks
        for prop in self.mappings.keys():
            self.map_property(task, prop, notion_db_metadata, notion_props, child_blocks, convert_md_links=True)
        # Map task comments to Notion properties or child blocks
        if task.comments:
            props, blocks = self.parse_prop_list([comment.content for comment in task.comments],
                                                 'comments', notion_db_metadata, True)
            notion_props.update(props)
            child_blocks.extend(blocks)
        # Add parent page relation
        parent_page_id = self.extract_parent_notion_uuid(task)
        if parent_page_id:
            notion_props.update({parent_property: PFormat.single_relation(parent_page_id)})
        return notion_props, child_blocks

    def update_properties(self, notion_task, todoist_task, prop_keys_to_update, db_metadata):
        props_to_upd = {}
        for prop_key in prop_keys_to_update:
            mappings = self.get_mapping(prop_key)
            # TODO handle list properties
            todoist_val = deep_get_task_prop(todoist_task.data, prop_key)
            default_notion_values = mappings.get('default_values', {})
            mapped_prop = mappings.get('values', {}).get(str(todoist_val), {})
            mapped_name = mapped_prop.get('name', default_notion_values.get('name'))
            if not mapped_name or mapped_name not in db_metadata.keys():
                continue
            mapped_type = db_metadata[mapped_name]['type']
            parser = get_notion_formatter_mapper().get(mapped_type)['parser']

            if todoist_val is not None and (not isinstance(todoist_val, list) or len(todoist_val) != 0):
                props = self.parse_prop_list_to_dict(todoist_val if isinstance(todoist_val, list) else [todoist_val],
                                                     prop_key,
                                                     db_metadata, prop_key == 'content')
                new_val = reduce(lambda x, y: f"{x}{y}", props[mapped_name]['raw_val'], '')
                formatted_values = props[mapped_name]['values']
            else:
                new_val = None
                if mapped_type in ['title', 'rich_text', 'relation']:
                    formatted_values = [None]
                else:
                    props = self.parse_prop_list_to_dict([None], prop_key, db_metadata, prop_key == 'content')
                    formatted_values = props[mapped_name]['values']
            old_val = parser(notion_task, mapped_name)

            if new_val != old_val:
                _LOG.debug(f"for {todoist_task['content']=}, {prop_key=} \n\t\t{old_val=}, \n\t\t{new_val=}")
                # append to dict to_upd
                if mapped_type == 'title':
                    props_to_upd[mapped_name] = PFormat.title(formatted_values)
                elif mapped_type == 'rich_text':
                    props_to_upd[mapped_name] = PFormat.rich_text(formatted_values)
                elif mapped_type == 'relation':
                    props_to_upd[mapped_name] = PFormat.relation(formatted_values)
                else:
                    props_to_upd[mapped_name] = formatted_values[0]
        return props_to_upd


class TodoistFetcher:
    def __init__(self):
        self.todoist_api = TodoistAPI(token=secrets.TODOIST_TOKEN)
        self.sync_api = SyncTodoistAPI(api_key=secrets.TODOIST_TOKEN)
        self.sync_api.sync(True)

    def get_completed_tasks(self, since: datetime = None, exclude_ids: list[str] = None) -> list[Task]:
        completed_tasks = self._get_completed_tasks(since=since.isoformat() if since else None)
        return [Task.from_dict(task) for task in completed_tasks if not exclude_ids or task['id'] not in exclude_ids]

    def _get_completed_tasks(self, since: str = None, limit: int = 500, batch_size: int = 100) -> list[dict]:
        """@since: datetime string in '2024-1-15T10:13:00' format"""
        self.sync_api.sync()
        params = {'limit': batch_size, 'offset': 0}
        if since:
            params['since'] = since
        all_items = []
        while len(all_items) < limit:
            items = self._send_sync_get('completed/get_all', **params)['items']
            all_items.extend(items)
            params['offset'] += batch_size
            if len(items) == 0:
                break
        return all_items

    def get_events(self, limit=10000, batch_size=100,
                   event_type: EventType = None,
                   object_type: ObjectType = None,
                   object_event_types: list[ObjectEventType] = None) -> list[dict]:
        """
        For todoist_api doc possible kwargs see https://developer.todoist.com/sync/v9/#get-activity-logs
        @param limit: limit of all collected events available from Todoist.
        @param batch_size: batch size for activities in one request.
        @param event_type: filter events by type (e.g. 'added', 'updated', 'deleted', 'completed').
        @param object_type: filter events by object type (e.g. 'item', 'project', 'note'),
        @param object_event_types: list of strings of the form [object_type]:[event_type].
            When this parameter is specified the object_type and event_type parameters are ignored.
        @return: event objects (see https://developer.todoist.com/sync/v9/#activity).
        """
        if 0 > batch_size > 100:
            _LOG.warning(f"{batch_size=}, but value must be between 1 and 100. Setting value to 100")
            batch_size = 100

        self.sync_api.sync()
        events = []
        count = batch_size
        params = {'limit': batch_size, 'offset': 0}
        if event_type:
            params['event_type'] = event_type
        if object_type:
            params['object_type'] = object_type
        if object_event_types:
            params['object_event_types'] = object_event_types
        while len(events) < count:
            result = self._send_sync_get('activity/get', **params)
            events.extend(result['events'])
            if params['offset'] == 0:
                count = min(result['count'], limit)
            params['offset'] += batch_size
        return events

    def get_all_tasks(self, get_completed: bool = False) -> list[Task]:
        active_tasks = [task for page in self.todoist_api.get_tasks() for task in page]

        if get_completed:
            completed = self.get_completed_tasks(exclude_ids=[task.id for task in active_tasks])
            active_tasks.extend(completed)

        return active_tasks

    def get_recently_added_tasks(self, since_date: datetime = None, days_old: int = None, get_completed: bool = True
                                 ) -> list[Task]:
        events: list[dict] = self.get_events(object_type='item', event_type='added')
        since_date = datetime.now(LOCAL_TIMEZONE) - timedelta(days=days_old) if not since_date and days_old else None
        created_tasks: list[str] = list(x['object_id'] for x in events if not since_date
                                        or datetime.strptime(x['event_date'], "%Y-%m-%dT%H:%M:%SZ")
                                        > since_date)
        _LOG.debug(f"Received {len(created_tasks)} recently created tasks" + (
            f" for the last {days_old} days" if days_old else ""))

        all_tasks = [task for page in self.todoist_api.get_tasks(ids=created_tasks) for task in page]
        if get_completed:
            completed_tasks = self.get_completed_tasks(since=since_date, exclude_ids=[task.id for task in all_tasks])
            all_tasks.extend(completed_tasks)

        return all_tasks

    def get_updated_tasks(self, sync_created: bool = True, sync_completed: bool = True
                          ) -> tuple[list[Task], dict[str, str]]:
        """
        @return: tuple of updated tasks and dict of task_id: event_date
        """
        events = self.get_events(object_type='item', event_type='updated')
        if sync_completed:
            events.extend(self.get_events(object_type='item', event_type='completed'))
            # sort to have latest event_date after reducing to unique dict entry
            events.sort(key=lambda k: k['event_date'])
        updated_tasks_to_date = {x['object_id']: LOCAL_TIMEZONE.normalize(
            pytz.timezone("UTC").localize(
                datetime.strptime(x['event_date'], "%Y-%m-%dT%H:%M:%SZ"))).isoformat() for x in events}

        tasks_to_exclude = []
        if not sync_created:
            events = self.get_events(object_type='item', event_type='added')
            tasks_to_exclude.extend([x['object_id'] for x in events])
        tasks_to_exclude = list(set(tasks_to_exclude))
        for task_id in tasks_to_exclude:
            if not tasks_to_exclude or task_id in updated_tasks_to_date.keys():
                updated_tasks_to_date.pop(task_id)

        updated_tasks = [task for page in self.todoist_api.get_tasks(ids=list(updated_tasks_to_date.keys())) for task in page]
        # items.all(
        #     lambda x: x['id'] in updated_tasks_to_date.keys() and (sync_completed or x['checked'] == 0))
        _LOG.debug(f"Received {len(updated_tasks)} updated tasks")
        return updated_tasks, updated_tasks_to_date

    def append_comments(self, tasks: list[TodoistTask]):
        """Append comments to tasks."""
        # for task in [task for task in tasks if task.task.comment_count > 0]:
        for task in tqdm(tasks, desc="Fetching comments", unit="task"):
            try:
                task.comments = [comment for page in self.todoist_api.get_comments(task_id=task.task.id) for comment in page]
            except Exception as e:
                _LOG.error(f"Failed to fetch comments for task {task.task.id}: {e}")

    @staticmethod
    def _send_sync_get(endpoint: str, **params) -> dict:
        """Reuse sync api get request"""
        url = f'{command_manager.BASE_URL}/{endpoint}'
        command_manager._headers.update({'Authorization': f'Bearer {command_manager.settings.api_key}'})
        with httpx.Client(headers=command_manager._headers) as client:
            response = client.get(url=url, params=params)
            response.raise_for_status()
            return response.json()  # type: ignore


def deep_get_task_prop(task_dict, keys, default=None):
    return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split("."), task_dict)


def parse_md_string_to_rich_text_objects(todoist_val: str) -> list:
    rich_text_blocks = []
    last_index = 0

    for match in MD_LINK_PATTERN.finditer(todoist_val):
        # Text before the match
        if match.start() > last_index:
            rich_text_blocks.append(PFormat.text(todoist_val[last_index:match.start()]))

        if match.group(3):  # This matches a plain URL
            rich_text_blocks.append(PFormat.link(match.group(3), match.group(3)))
        else:  # This matches a Markdown link
            rich_text_blocks.append(PFormat.link(f"{match.group(1)}🔗", match.group(2)))

        last_index = match.end()

    # Add any remaining text after the last match
    if last_index < len(todoist_val):
        rich_text_blocks.append(PFormat.text(todoist_val[last_index:]))

    return rich_text_blocks


def parse_md_string_to_notion_view(todoist_val) -> str:
    def replace(match: re.Match) -> str:
        if match.group(3):  # This is a plain URL
            return match.group(3)
        else:  # This is a Markdown link
            link_text = match.group(1)
            link_url = match.group(2)
            return f"[{link_text}🔗]({link_url})"

    modified_text = MD_LINK_PATTERN.sub(replace, todoist_val)
    return modified_text
