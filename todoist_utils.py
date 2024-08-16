import ast
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from functools import reduce, lru_cache

from todoist_api_python.api import TodoistAPI
from todoist_api_python.models import (Task, Comment)

import notion
import secrets
from notion import PropertyFormatter as PFormat
from notion import PropertyParser as PParser

_LOG = logging.getLogger(__name__)
MD_LINK_PATTERN = re.compile(r"\[([^]]*)]\((https?://[^\s)]+)\)|(https?://[^\s)]+)")
NOTION_URL_PATTERN = re.compile("\\[.+]\\("
                                "(https://www.notion.so)?"  # Notion host
                                "/([a-zA-Z0-9-]+/)?"  # Username
                                "([a-zA-Z0-9-]+-)?"  # Page name
                                "([a-f0-9]{8}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{4}-?[a-f0-9]{12})"  # UUID
                                "(\\?[a-zA-Z0-9%=\\-&]*)?\\)")


class NoneStrategy(Enum):
    IGNORE = 'ignore'  # Ignore property value if it is not mapped
    VALUE_AS_IS = 'value-as-is'
    MAP_BY_NAME = 'map-by-name'  # Map property values (labels) to relations by identical name


@dataclass
class TodoistTask:
    task: Task
    comments: list[Comment] = field(default_factory=list)
    notion_url: str | None = None


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
            'date': {'method': PFormat.date, 'parser': PParser.date_wo_tz, 'list_values': False}}


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
        labels = {label.name: label.id for label in self.todoist_api.get_labels()}
        notion_master_tags = n_tags if n_tags else notion.read_database(secrets.MASTER_TAG_DB)
        notion_tags = {tag: page['id'] for page in notion_master_tags if
                       (tag := PParser.rich_text(page, todoist_tags_text_prop))}
        tag_mapping = {labels[key]: notion_tags[key] for key in notion_tags if key in labels}

        return tag_mapping

    def extract_link_to_parent(self, task: TodoistTask):
        parent_id = task.task.parent_id
        if not parent_id:
            return None
        parent_task = self.todoist_api.get_task(parent_id)
        match = re.match(NOTION_URL_PATTERN, parent_task.description)
        if match:
            return match.group(4)
        return None

    def get_events(self, limit=1000000, batch_size=100, **kwargs):
        """
        For todoist_api doc possible kwargs see https://developer.todoist.com/sync/v8/?shell#get-activity-logs
        :param limit: limit of all collected events available from Todoist.
        :param batch_size: batch size for activities in one request.
        :return: event object (see https://developer.todoist.com/sync/v8/?shell#activity).
        """
        if 0 > batch_size > 100:
            _LOG.warning(f"{batch_size=}, but value must be between 1 and 100. Setting value to 100")
            batch_size = 100

        events = []
        count = batch_size
        offset = 0
        while len(events) < count:
            result = self.todoist_api.activity.get(**kwargs, limit=batch_size, offset=offset)
            events.extend(result['events'])
            if offset == 0:
                count = min(result['count'], limit)
            offset += batch_size
        return events

    def map_property(self, task: TodoistTask, prop_name: str, db_metadata: dict, notion_props: dict = None,
                     child_blocks: list = None,
                     convert_md_links=False) -> tuple[dict | None, list | None]:
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
                   db_metadata: dict, convert_md_links: bool) -> tuple[dict | None, list | None]:
        if not task or not (todoist_val := deep_get_task_prop(task.task.to_dict(), prop_key)):
            return None, None

        value_list = todoist_val if isinstance(todoist_val, list) else [todoist_val]
        return self.parse_prop_list(value_list, prop_key, db_metadata, convert_md_links)

    def parse_prop_list(self, todoist_val_list, prop_key, db_metadata, convert_md_links) -> tuple[dict, list]:
        props = self.parse_prop_list_to_dict(todoist_val_list, prop_key, db_metadata, convert_md_links)

        listed_props = {}
        listed_blocks = []
        for k, v in props.items():
            if len(v['values']) == 0:
                continue
            if k not in db_metadata.keys():
                listed_blocks.append(PFormat.heading_block(k))
                listed_blocks.append(PFormat.paragraph_block(*v['values']))
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
                if formatter['method'] == PFormat.single_title:
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

    def update_properties(self, notion_task, todoist_task, prop_keys_to_update, db_metadata):
        mapper = self.mappings
        props_to_upd = {}
        for prop_key in prop_keys_to_update:
            mappings = mapper[prop_key]
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
