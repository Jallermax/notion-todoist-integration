import ast
import re
from enum import Enum
from functools import reduce

import secrets
import todoist
import notion
from notion import PropertyFormatter as pformat
from notion import PropertyParser as pparser

md_link_pattern = re.compile(r"\[(.+)\]\((https?:\/\/[\w\d./?=+\-#%&]+)\)")
page_id_from_url_pattern = re.compile(r"\[.+\]\(https?:\/\/.*([\d\w]{32})\)")


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
    return {'title': {'method': pformat.single_title, 'is_property': True},
            # 'rich_text': {'method': pformat.single_rich_text, 'is_property': True},
            # 'rich_text_link': {'method': pformat.single_rich_text_link, 'is_property': True},
            'rich_text': {'method': pformat.single_rich_text, 'is_property': True},
            'select': {'method': pformat.select, 'is_property': True},
            'checkbox': {'method': pformat.checkbox, 'is_property': True},
            'date': {'method': pformat.date, 'is_property': True},
            'relation': {'method': pformat.relation, 'is_property': True},
            # 'paragraph_text_block': {'method': pformat.paragraph_text_block, 'is_property': False}
            }


def get_default_values():
    return {'type': 'rich_text'}


def deep_get(dictionary, keys, default=None):
    return reduce(lambda d, key: d.get(key, default) if isinstance(d, dict) else default, keys.split("."), dictionary)


def map_property(task, prop_name: str, db_metadata, props: dict = None, child_blocks: list = None,
                 convert_md_links=False):
    if isinstance(props, type(None)):
        props = {}
    if isinstance(child_blocks, type(None)):
        child_blocks = []

    _p, _c = parse_prop(task, prop_name, db_metadata, convert_md_links)
    if _p:
        props.update(_p)
    if _c:
        child_blocks.append(_c)
    return props, child_blocks


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

        if mappings.get('none_strategy') == NoneStrategy.MAP_BY_NAME.value and label in label_mapper:
            child_blocks.append(pformat.paragraph_block(pformat.mention(label_mapper[label])))
            continue

        # Default strategy: value-as-is
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
        # TODO add label_name to label mapper
        label_name = todoist_api.labels.get_by_id(label)['name']
        if 'link' in mappings.keys():
            link = mappings.get('link').format(label_name)
            child_blocks.append(pformat.paragraph_block(pformat.link(f"{label_name}", link)))
        else:
            child_blocks.append(pformat.paragraph_block(pformat.text(f"Todoist label: {str(label_name)}")))

    return props, child_blocks


def parse_prop(task, prop_key, db_metadata, convert_md_links):
    # [ {"formatter": formatter_x, "props": [{"prop_key1": "Todoist Tags", values: ['214412412', '2414']}, ]}, ]
    # { "title": {"Todoist Tags": ['214412412', '2414']}
    if not task or not deep_get(task.data, prop_key):
        return None, None

    # TODO add list parsing if isinstance(task[prop_key], list)
    todoist_val = deep_get(task.data, prop_key)
    mappings = load_todoist_to_notion_mapper()[prop_key]
    notion_prop = mappings.get('values', {}).get(str(todoist_val))
    default_notion_values = mappings.get('default_values', get_default_values())
    default_name = default_notion_values.get('name')
    default_type = default_notion_values.get('type')

    # Parse mapped property value according to mapping file
    if notion_prop:
        n_name = notion_prop.get('name', default_name)
        n_type = notion_prop.get('type', default_type)
        n_value = notion_prop.get('value')
        formatter = get_notion_formatter_mapper().get(n_type)
        is_property = n_name and n_name in db_metadata.keys()

        if n_value and is_property:
            return {n_name: formatter['method'](n_value, property_obj=True)}, None
        elif n_value:
            return None, pformat.paragraph_block(formatter['method'](f"{n_value}", property_obj=False))

    # If property value is not mapped, ignore it
    # TODO strategy handling of mappings['none_strategy']
    if mappings.get('none_strategy') == NoneStrategy.IGNORE.value:
        return None, None

    # If property value is not mapped, parse it according to default_values rules
    # if mappings.get('none_strategy') == NoneStrategy.VALUE_AS_IS.value:
    is_property = default_name and default_name in db_metadata.keys()
    formatter = get_notion_formatter_mapper().get(db_metadata[default_name]['type'] if is_property else default_type)

    if convert_md_links and formatter['method'] in [pformat.single_title,
                                                    pformat.single_rich_text] and md_link_pattern.search(todoist_val):
        rich_text_objects = parse_md_string_to_rich_text_objects(todoist_val)
        if is_property and formatter['method'] == pformat.single_title:
            return {default_name: pformat.title(rich_text_objects)}, None
        elif is_property and formatter['method'] == pformat.single_rich_text:
            return {default_name: pformat.rich_text(rich_text_objects)}, None
        else:
            return None, pformat.paragraph_block(pformat.text(f"{prop_key}: "), *rich_text_objects)

    link = None
    if 'link' in mappings.keys():
        link = mappings.get('link').format(todoist_val)
        link = pformat.link(todoist_val, link)

    if 'expression' in default_notion_values.keys():
        todoist_val = eval(default_notion_values.get('expression'), {'value': todoist_val})

    if is_property:
        if link and formatter['method'] == pformat.single_title:
            return {default_name: pformat.title([link])}, None
        if link and formatter['method'] == pformat.single_rich_text:
            return {default_name: pformat.rich_text([link])}, None
        return {default_name: formatter['method'](todoist_val)}, None
    else:
        return None, pformat.paragraph_block(pformat.text(f"{prop_key}: "), link if link else pformat.text(todoist_val))


def parse_md_string_to_rich_text_objects(todoist_val) -> list:
    # TODO add handling of multiple links in string
    regs = md_link_pattern.search(todoist_val).regs
    notion_link = pformat.link(todoist_val[regs[1][0]:regs[1][1]] + '🔗', todoist_val[regs[2][0]:regs[2][1]])
    begin_text = todoist_val[:regs[0][0]]
    end_text = todoist_val[regs[0][1]:]
    text_blocks = (pformat.text(begin_text) if len(begin_text) > 0 else None, notion_link,
                   pformat.text(end_text) if len(end_text) > 0 else None)
    return [b for b in text_blocks if b]


def extract_link_to_parent(task, todoist_api: todoist.TodoistAPI = None):
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    if task['parent_id']:
        parent_task = todoist_api.items.get_by_id(task['parent_id'])
        parent_page_id = page_id_from_url_pattern.findall(parent_task.data.get('description'))
        if parent_page_id:
            return parent_page_id[0]
    return None
