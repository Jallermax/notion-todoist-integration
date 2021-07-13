import ast
from enum import Enum
from functools import reduce

import secrets
import todoist
import notion
from notion import PropertyFormatter as pformat
from notion import PropertyParser as pparser


class NoneStrategy(Enum):
    IGNORE = 'ignore'
    VALUE_AS_IS = 'value-as-is'
    MAP_BY_NAME = 'map-by-name'


def load_todoist_to_notion_mapper():
    # TODO add file parametric based on running scenario + caching
    file = open("mappings.json", "r")

    contents = file.read()
    dictionary = ast.literal_eval(contents)

    file.close()
    return dictionary


def get_label_tag_mapping(todoist_api: todoist.TodoistAPI = None, n_tags=None):
    """
    Creates an id mapping between 'Todoist Tags' property in Notion Master Tag DB and Todoist Labels by name.
    :return: dict(todoist_label_id: notion_tag_page_id)
    """
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    labels = {label['name']: label['id'] for label in todoist_api.labels.all()}
    notion_master_tags = n_tags if n_tags else notion.read_database(secrets.MASTER_TAG_DB)
    notion_tags = {pparser.rich_text(page, 'Todoist Tags'): page['id'] for page in notion_master_tags if
                   pparser.rich_text(page, 'Todoist Tags')}
    tag_mapping = {labels[key]: notion_tags[key] for key in notion_tags}

    return tag_mapping


def get_notion_formatter_mapper():
    # TODO move 'is_property' to pformat object
    return {'title': {'method': pformat.title, 'is_property': True},
            'rich_text_link': {'method': pformat.rich_text_link, 'is_property': True},
            'select': {'method': pformat.select, 'is_property': True},
            'checkbox': {'method': pformat.checkbox, 'is_property': True},
            'relation': {'method': pformat.relation, 'is_property': True},
            'paragraph_text_block': {'method': pformat.paragraph_text_block, 'is_property': False},
            'paragraph_mention_block': {'method': pformat.paragraph_mention_block, 'is_property': False}}


def get_default_values():
    return {'type': 'paragraph_text_block'}


def deep_get(dictionary, keys, default=None):
    return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split("."), dictionary)


def map_property(task, prop_name: str, props: dict = None, child_blocks: list = None):
    if isinstance(props, type(None)):
        props = {}
    if isinstance(child_blocks, type(None)):
        child_blocks = []

    _p, _c = parse_prop(task, prop_name)
    if _p:
        props.update(_p)
    if _c:
        child_blocks.append(_c)
    return props, child_blocks


def map_project(task, props: dict = None, child_blocks: list = None):
    return map_property(task, 'project_id', props, child_blocks)


def map_priority(task, props: dict = None, child_blocks: list = None):
    return map_property(task, 'priority', props, child_blocks)


def map_labels(task, props: dict = None, child_blocks: list = None):
    # TODO join with parse_prop() function
    if isinstance(props, type(None)):
        props = {}
    if isinstance(child_blocks, type(None)):
        child_blocks = []

    mappings = load_todoist_to_notion_mapper()['labels']
    # TODO add caching of label_tag_mapping
    label_mapper = get_label_tag_mapping()

    for label in task['labels']:
        notion_prop = mappings.get('values', {}).get(str(label))
        if notion_prop:
            n_name = notion_prop.get('name', mappings.get('default_values', get_default_values()).get('name'))
            n_type = notion_prop.get('type', mappings.get('default_values', get_default_values()).get('type'))
            formatter = get_notion_formatter_mapper().get(n_type)
            n_value = notion_prop.get('value')

            if n_value and formatter['is_property'] and n_name:
                props.update({n_name: formatter['method'](n_value)})
                continue
            elif n_value and not formatter['is_property']:
                child_blocks.append(formatter['method'](f"Label: {n_value}"))
                continue

        # TODO strategy handling of mappings['none_strategy']
        if mappings.get('none_strategy') == NoneStrategy.IGNORE.value:
            continue

        if mappings.get('none_strategy') == NoneStrategy.MAP_BY_NAME.value and label_mapper.__contains__(label):
            child_blocks.append(pformat.paragraph_mention_block(label_mapper[label]))
            continue

        # Default strategy: value-as-is
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
        # TODO add label_name to label mapper
        label_name = todoist_api.labels.get_by_id(label)['name']
        if 'link' in mappings.keys():
            link = mappings.get('link').format(label_name)
            child_blocks.append(pformat.paragraph_block(pformat.rich_text_link(f"{label_name}", link)))
        else:
            child_blocks.append(pformat.paragraph_block(pformat.rich_text(f"Todoist label: {str(label_name)}")))

    return props, child_blocks


def parse_prop(task, prop_key):
    if not task or not deep_get(task.data, prop_key):
        return None, None

    # TODO add list parsing if isinstance(task[prop_key], list)
    todoist_val = deep_get(task.data, prop_key)
    mappings = load_todoist_to_notion_mapper()[prop_key]
    notion_prop = mappings.get('values', {}).get(str(todoist_val))
    default_notion_values = mappings.get('default_values', get_default_values())

    # Parse mapped property value according to mapping file
    if notion_prop:
        n_name = notion_prop.get('name', default_notion_values.get('name'))
        n_type = notion_prop.get('type', default_notion_values.get('type'))
        formatter = get_notion_formatter_mapper().get(n_type)
        n_value = notion_prop.get('value')

        if n_value and formatter['is_property']:
            return {n_name: formatter['method'](n_value)}, None
        elif n_value and not formatter['is_property']:
            return None, formatter['method'](f"{n_name}: {n_value}")

    # If property value is not mapped, ignore it
    # TODO strategy handling of mappings['none_strategy']
    if mappings.get('none_strategy') == NoneStrategy.IGNORE.value:
        return None, None

    # If property value is not mapped, parse it according to default_values rules
    # if mappings.get('none_strategy') == NoneStrategy.VALUE_AS_IS.value:
    formatter = get_notion_formatter_mapper().get(default_notion_values.get('type'))

    link = None
    if 'link' in mappings.keys():
        link = mappings.get('link').format(todoist_val)

    if 'expression' in default_notion_values.keys():
        todoist_val = eval(default_notion_values.get('expression'), {'value': todoist_val})

    if formatter['is_property']:
        if link:
            return {default_notion_values.get('name'): formatter['method'](todoist_val, link=link)}, None
        return {default_notion_values.get('name'): formatter['method'](todoist_val)}, None
    elif not formatter['is_property']:
        if link:
            return None, formatter['method'](f"{prop_key}: {todoist_val}", link=link)
        return None, formatter['method'](f"{prop_key}: {todoist_val}")

