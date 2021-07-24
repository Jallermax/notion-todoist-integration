import ast
import logging
import re
from enum import Enum
from functools import reduce

import secrets
import todoist
import notion
from notion import PropertyFormatter as pformat
from notion import PropertyParser as pparser

_LOG = logging.getLogger(__name__)
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


def get_label_tag_mapping(todoist_api: todoist.TodoistAPI = None, n_tags=None, todoist_tags_text_prop='Todoist Tags'):
    """
    Creates an id mapping between 'Todoist Tags' property in Notion Master Tag DB and Todoist Labels by name.
    :return: dict(todoist_label_id: notion_tag_page_id)
    """
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    labels = {label['name']: label['id'] for label in todoist_api.labels.all()}
    notion_master_tags = n_tags if n_tags else notion.read_database(secrets.MASTER_TAG_DB)
    notion_tags = {pparser.rich_text(page, todoist_tags_text_prop): page['id'] for page in notion_master_tags if
                   pparser.rich_text(page, todoist_tags_text_prop)}
    tag_mapping = {labels[key]: notion_tags[key] for key in notion_tags}

    return tag_mapping


def get_notion_formatter_mapper():
    # TODO move 'is_property' to pformat object
    return {'title': {'method': pformat.single_title, 'parser': pparser.title, 'list_values': True},
            'rich_text': {'method': pformat.single_rich_text, 'parser': pparser.rich_text, 'list_values': True},
            'relation': {'method': pformat.single_relation, 'parser': pparser.relation, 'list_values': True},
            'select': {'method': pformat.select, 'parser': pparser.select, 'list_values': False},
            'checkbox': {'method': pformat.checkbox, 'parser': pparser.checkbox, 'list_values': False},
            'date': {'method': pformat.date, 'parser': pparser.date_wo_tz, 'list_values': False}}


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
        child_blocks.append(_c) if not isinstance(_c, list) else child_blocks.extend(_c)
    return props, child_blocks


def parse_prop(task, prop_key, db_metadata, convert_md_links):
    if not task or not deep_get(task.data, prop_key):
        return None, None

    todoist_val = deep_get(task.data, prop_key)
    if isinstance(todoist_val, list):
        return parse_prop_list(todoist_val, prop_key, db_metadata, convert_md_links)
    return parse_prop_list([todoist_val], prop_key, db_metadata, convert_md_links)


def parse_prop_list(todoist_val_list, prop_key, db_metadata, convert_md_links):
    # TODO add caching of label_tag_mapping
    props = parse_prop_list_to_dict(todoist_val_list, prop_key, db_metadata, convert_md_links)

    listed_props = {}
    listed_blocks = []
    for k, v in props.items():
        if len(v['values']) == 0:
            continue
        if k not in db_metadata.keys():
            listed_blocks.append(pformat.heading_block(k))
            listed_blocks.append(pformat.paragraph_block(*v['values']))
        elif db_metadata[k]['type'] == 'title':
            listed_props[k] = pformat.title(v['values'])
        elif db_metadata[k]['type'] == 'rich_text':
            listed_props[k] = pformat.rich_text(v['values'])
        elif db_metadata[k]['type'] == 'relation':
            listed_props[k] = pformat.relation(v['values'])
        else:
            listed_props[k] = v['values'][0]

    return listed_props, listed_blocks


def parse_prop_list_to_dict(todoist_val_list, prop_key, db_metadata, convert_md_links):
    """

    :param convert_md_links:
    :param db_metadata:
    :param prop_key:
    :param todoist_val_list:
    :return: example:
        {"POM": {"formatter": {"method": pformat.select, "list_values": False}, "values": [], "raw_val": []}}
    """
    label_mapper = get_label_tag_mapping() if prop_key == 'labels' else None
    props = {}
    mappings = load_todoist_to_notion_mapper()[prop_key]
    default_notion_values = mappings.get('default_values', {})
    for todoist_val in todoist_val_list:
        mapped_prop = mappings.get('values', {}).get(str(todoist_val), {})
        mapped_name = mapped_prop.get('name', default_notion_values.get('name', get_default_values().get('name',
                                                                                                         f"{prop_key}: ")))
        mapped_type = mapped_prop.get('type', default_notion_values.get('type', get_default_values().get('type')))
        mapped_value = mapped_prop.get('value')
        is_property = mapped_name and mapped_name in db_metadata.keys()
        formatter = get_notion_formatter_mapper().get(db_metadata[mapped_name]['type'] if is_property else mapped_type)

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
            if formatter['method'] == pformat.single_title:
                current_prop_values.append(pformat.text(mapped_value))
                continue
            current_prop_values.append(formatter['method'](mapped_value, property_obj=is_property))
            continue

        # If property value is not mapped, ignore it
        if mappings.get('none_strategy') == NoneStrategy.IGNORE.value:
            continue

        if mappings.get(
                'none_strategy') == NoneStrategy.MAP_BY_NAME.value and label_mapper and todoist_val in label_mapper:
            current_prop_values.append(pformat.mention(label_mapper[todoist_val]))
            current_prop_raw_values.append(todoist_val)
            continue

        # If property value is not mapped, parse it according to NoneStrategy.VALUE_AS_IS and default_values rules
        if convert_md_links and formatter['method'] in [pformat.single_title,
                                                        pformat.single_rich_text] and md_link_pattern.search(
                                                        todoist_val):
            rich_text_objects = parse_md_string_to_rich_text_objects(todoist_val)
            current_prop_values.append(rich_text_objects)
            current_prop_raw_values.append(parse_md_string_to_notion_view(todoist_val))
            continue

        if 'link' in mappings.keys():
            link = mappings.get('link').format(todoist_val)
            current_prop_values.append(pformat.link(todoist_val, link))
            continue

        if 'expression' in default_notion_values.keys():
            todoist_val = eval(default_notion_values.get('expression'), {'value': todoist_val})

        if formatter['method'] in [pformat.single_title, pformat.single_rich_text]:
            current_prop_values.append(pformat.text(todoist_val))
        else:
            current_prop_values.append(formatter['method'](todoist_val, property_obj=is_property))

        current_prop_raw_values.append(todoist_val)
    return props


def parse_md_string_to_rich_text_objects(todoist_val) -> list:
    # TODO add handling of multiple links in string
    regs = md_link_pattern.search(todoist_val).regs
    notion_link = pformat.link(todoist_val[regs[1][0]:regs[1][1]] + '🔗', todoist_val[regs[2][0]:regs[2][1]])
    begin_text = todoist_val[:regs[0][0]]
    end_text = todoist_val[regs[0][1]:]
    text_blocks = (pformat.text(begin_text) if len(begin_text) > 0 else None, notion_link,
                   pformat.text(end_text) if len(end_text) > 0 else None)
    return [b for b in text_blocks if b]


def parse_md_string_to_notion_view(todoist_val) -> str:
    regs = md_link_pattern.search(todoist_val).regs
    return f"{todoist_val[:regs[0][0]]}" \
           f"[{todoist_val[regs[1][0]:regs[1][1]]}🔗]({todoist_val[regs[2][0]:regs[2][1]]})" \
           f"{todoist_val[regs[0][1]:]}"


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


def get_events(todoist_api: todoist.TodoistAPI = None, limit=1000000, batch_size=100, **kwargs):
    """
    For todoist_api doc possible kwargs see https://developer.todoist.com/sync/v8/?shell#get-activity-logs
    :param todoist_api: TODO move to context
    :param limit: limit of all collected events available from Todoist.
    :param batch_size: batch size for activities in one request.
    :return: event object (see https://developer.todoist.com/sync/v8/?shell#activity).
    """
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    if 0 > batch_size > 100:
        _LOG.warning(f"{batch_size=}, but value must be between 1 and 100. Setting value to 100")
        batch_size = 100

    events = []
    count = batch_size
    offset = 0
    while len(events) < count:
        result = todoist_api.activity.get(**kwargs, limit=batch_size, offset=offset)
        events.extend(result['events'])
        if offset == 0:
            count = min(result['count'], limit)
        offset += batch_size
    return events


def update_properties(notion_task, todoist_task, props_to_update, db_metadata):
    mapper = load_todoist_to_notion_mapper()
    props_to_upd = {}
    for prop_key in props_to_update:
        mappings = mapper[prop_key]
        todoist_val = deep_get(todoist_task.data, prop_key)
        default_notion_values = mappings.get('default_values', {})
        mapped_prop = mappings.get('values', {}).get(str(todoist_val), {})
        mapped_name = mapped_prop.get('name', default_notion_values.get('name'))
        if not mapped_name or mapped_name not in db_metadata.keys():
            continue
        mapped_type = db_metadata[mapped_name]['type']
        parser = get_notion_formatter_mapper().get(mapped_type)['parser']

        if todoist_val is not None:
            props = parse_prop_list_to_dict([todoist_val], prop_key, db_metadata, prop_key == 'content')
            new_val = reduce(lambda x, y: f"{x}{y}", props[mapped_name]['raw_val'], '')
            formatted_values = props[mapped_name]['values']
        else:
            new_val = None
            formatted_values = [None]
        old_val = parser(notion_task, mapped_name)

        if new_val != old_val:
            _LOG.debug(f"for {todoist_task['content']=}, {prop_key=} \n\t\t{old_val=}, \n\t\t{new_val=}")
            # append to dict to_upd
            if mapped_type == 'title':
                props_to_upd[mapped_name] = pformat.title(formatted_values)
            elif mapped_type == 'rich_text':
                props_to_upd[mapped_name] = pformat.rich_text(formatted_values)
            elif mapped_type == 'relation':
                props_to_upd[mapped_name] = pformat.relation(formatted_values)
            else:
                props_to_upd[mapped_name] = formatted_values[0]
    return props_to_upd
