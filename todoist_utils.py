import ast
from enum import Enum, auto

import secrets
import todoist
import notion
from notion import PropertyFormatter as pformat
from notion import PropertyParser as pparser


class NotionPropType(Enum):
    PROPERTY = auto()
    CHILD_BLOCK = auto()


def load_todoist_to_notion_mapper():
    file = open("mappings.json", "r")

    contents = file.read()
    dictionary = ast.literal_eval(contents)

    file.close()
    return dictionary


def get_label_tag_mapping(todoist_api: todoist.TodoistAPI = None):
    """
    Creates an id mapping between 'Todoist Tags' property in Notion Master Tag DB and Todoist Labels by name.
    :return: dict(todoist_label_id: notion_tag_page_id)
    """
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    labels = {label['name']: label['id'] for label in todoist_api.labels.all()}
    notion_tags = list(
        filter(lambda x: pparser.rich_text(x, 'Todoist Tags'), notion.read_database(secrets.MASTER_TAG_DB)))
    notion_tags = {pparser.rich_text(page, 'Todoist Tags'): page['id'] for page in notion_tags}
    tag_mapping = {}
    for key in notion_tags:
        tag_mapping[labels[key]] = notion_tags[key]

    return tag_mapping


def get_notion_formatter_mapper():
    return {'rich_text_link': (pformat.rich_text_link, NotionPropType.PROPERTY),
            'select': (pformat.select, NotionPropType.PROPERTY),
            'relation': (pformat.relation, NotionPropType.PROPERTY),
            'paragraph_text_block': (pformat.paragraph_text_block, NotionPropType.CHILD_BLOCK),
            'paragraph_mention_block': (pformat.paragraph_mention_block, NotionPropType.CHILD_BLOCK)}


def map_property(task, prop_name, props: dict = None, child_blocks: list = None):
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
    label_mapper = get_label_tag_mapping()

    for label in task['labels']:
        notion_prop = mappings.get('values', {}).get(str(label))
        if notion_prop:
            n_name = notion_prop.get('name', mappings['default_values'].get('name'))
            n_type = notion_prop.get('type', mappings['default_values'].get('type'))
            formatter = get_notion_formatter_mapper().get(n_type)
            n_value = notion_prop.get('value')

            if n_name and formatter and n_value and formatter[1] == NotionPropType.PROPERTY:
                props.update({n_name: formatter[0](n_value)})
                continue
            elif formatter and n_value and formatter[1] == NotionPropType.CHILD_BLOCK:
                child_blocks.append(formatter[0](n_value))
                continue

        # TODO strategy handling of mappings['none_strategy']
        if mappings.get('none_strategy') == 'ignore':
            continue

        if mappings.get('none_strategy') == 'map-by-name' and label_mapper.__contains__(label):
            child_blocks.append(pformat.paragraph_mention_block(label_mapper[label]))
            continue

        # Default strategy: value-as-is
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
        # TODO add name to label mapper
        label_name = todoist_api.labels.get_by_id(label)['name']
        if 'link' in mappings.keys():
            link = mappings.get('link').format(label_name)
            child_blocks.append(pformat.paragraph_block(pformat.rich_text_link(f"{label_name}", link)))
        else:
            child_blocks.append(pformat.paragraph_block(pformat.rich_text(f"Todoist label: {str(label_name)}")))

    return props, child_blocks


def parse_prop(task, prop_key):
    if not task[prop_key]:
        return None, None

    todoist_val = str(task[prop_key])
    mappings = load_todoist_to_notion_mapper()[prop_key]
    notion_prop = mappings.get('values', {}).get(todoist_val)
    if notion_prop:
        n_name = notion_prop.get('name', mappings['default_values'].get('name'))
        n_type = notion_prop.get('type', mappings['default_values'].get('type'))
        formatter = get_notion_formatter_mapper().get(n_type)
        n_value = notion_prop.get('value')

        if n_name and formatter and formatter[1] == NotionPropType.PROPERTY and n_value:
            return {n_name: formatter[0](n_value)}, None
        elif formatter and formatter[1] == NotionPropType.CHILD_BLOCK and n_value:
            return None, formatter[0](n_value)

    # TODO strategy handling of mappings['none_strategy']
    if mappings.get('none_strategy') == 'ignore':
        return None, None

    if mappings.get('none_strategy') == 'value-as-is' and mappings['default_values'].get('type'):
        formatter = get_notion_formatter_mapper().get(mappings['default_values'].get('type'))
        # TODO find a way to pass link to formatter[0] without breaking pformaters without 2nd parameter
        link = None
        if 'link' in mappings.keys():
            link = mappings.get('link').format(todoist_val)
        if mappings['default_values'].get('name') and formatter and formatter[1] == NotionPropType.PROPERTY:
            return {mappings['default_values'].get('name'): formatter[0](todoist_val, link=link)}, None
        elif formatter and formatter[1] == NotionPropType.CHILD_BLOCK:
            return None, formatter[0](todoist_val, link=link)

    if 'link' in mappings.keys():
        link = mappings.get('link').format(todoist_val)
        return None, pformat.paragraph_block(pformat.rich_text_link(f"{prop_key}: {todoist_val}", link))
    else:
        return None, pformat.paragraph_block(pformat.rich_text(f"{prop_key}: {todoist_val}"))


def parse_checked(task):
    return bool(task['checked'])
