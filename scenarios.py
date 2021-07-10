import logging
import datetime
import pytz
import itertools
import secrets
import notion
import todoist_utils
import todoist

from notion import PropertyFormatter as pformat
from notion import PropertyParser as pparser

_LOG = logging.getLogger(__name__)
LOCAL_TIMEZONE = pytz.timezone('Europe/Moscow')


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    notion.update_page(page_id, TodoistTaskId=pformat.rich_text_link(str(task_id), task_link))


def create_history_record(action_id, task) -> (bool, object):
    task_id = str(task['id'])
    dt = task['date_completed']
    desc = task['description']
    child_blocks = []
    if task['notes']:
        child_blocks.append(pformat.heading_block("Notes", 2))
        child_blocks.append(pformat.paragraph_text_block(task['notes']))

    if dt:
        dt = LOCAL_TIMEZONE.normalize(
            pytz.timezone("UTC").localize(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ")))
    else:
        dt = LOCAL_TIMEZONE.localize(datetime.datetime.now())
    title = dt.strftime('%y.%m.%d') + ('' if desc == '' else ' ' + desc)
    task_link = f"https://todoist.com/showTask?id={task_id}"

    return notion.create_page(secrets.HISTORY_DATABASE_ID,
                              *child_blocks,
                              Record=pformat.title(title),
                              Completed=pformat.date(dt.isoformat()),
                              Action=pformat.relation(action_id),
                              TodoistTaskId=pformat.rich_text_link(task_id, task_link))


def create_action_entry(tag_mapping, task):
    priority_mapper = {1: 'p4', 2: 'p3', 3: 'p2', 4: 'p1'}
    project_mapper = {2219986415: '3142b10bfeac4b669a24d4603efb2f3a',  # ML career path
                      2267650566: 'b3ab76ee27634672b6fa966415248e5d'}  # Integration app
    child_blocks = []
    if task['notes']:
        child_blocks.append(pformat.heading_block("Notes", 2))
        child_blocks.append(pformat.paragraph_text_block(task['notes']))
    tags = list(tag_mapping[i] for i in filter(lambda l: tag_mapping.__contains__(l), task['labels']))
    task_link = f"https://todoist.com/showTask?id={task['id']}"
    notion_task = {'Name': pformat.title(task['content']),
                   'Priority': pformat.select(priority_mapper[task['priority']]),
                   'TodoistTaskId': pformat.rich_text_link(str(task['id']), task_link),
                   'Done': pformat.checkbox(bool(task['checked']))}
    if project_mapper.__contains__(task['project_id']):
        notion_task.update({'Projects': pformat.relation(project_mapper[task['project_id']])})
    if tags:
        child_blocks.append(pformat.heading_block("Tags", 3))
        child_blocks.append(pformat.paragraph_mention_block(*tags))
    success, page = notion.create_page(secrets.MASTER_TASKS_DB_ID,
                                       *child_blocks, **notion_task)
    if success:
        _LOG.info(f"Page created: https://www.notion.so/jallermax/{page['id']}")
    else:
        _LOG.error(f"Error creating page from {task=}: {page}")


def create_action_entry_v2(task):
    notion_task = {'Name': pformat.title(task['content']),
                   'Done': pformat.checkbox(bool(task['checked']))}

    # TODO iterate through all keys in mappings for particular scenario instead of manually map each property type
    _, child_blocks = todoist_utils.map_property(task, 'id', notion_task)
    todoist_utils.map_property(task, 'notes', notion_task, child_blocks)
    todoist_utils.map_priority(task, notion_task, child_blocks)
    todoist_utils.map_project(task, notion_task, child_blocks)
    todoist_utils.map_labels(task, notion_task, child_blocks)

    success, page = notion.create_page(secrets.MASTER_TASKS_DB_ID,
                                       *child_blocks, **notion_task)
    if success:
        _LOG.info(f"Page created: {page['url']}")
    else:
        _LOG.error(f"Error creating page from {task=}\n\t{notion_task=}\n\t{child_blocks=}\n\t{page}")


def get_recent_tasks(todoist_api: todoist.TodoistAPI = None, days_old=3):
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
    # TODO loop through activities with offset if > limit
    events = todoist_api.activity.get(object_type='item', event_type='added', limit=100)['events']
    _LOG.debug(f"Received {len(events)} events for the last {days_old} days")
    created_tasks = list(x['object_id'] for x in filter(
        lambda x: datetime.datetime.strptime(x['event_date'], "%Y-%m-%dT%H:%M:%SZ") > (
                datetime.datetime.now() - datetime.timedelta(days=days_old)), events))
    all_tasks = todoist_api.items.all(lambda x: (created_tasks.__contains__(x['id']) and x['checked'] == 0))
    return all_tasks


def append_notes_to_tasks(all_tasks, todoist_api: todoist.TodoistAPI = None):
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
    all_notes = todoist_api.notes.all()
    for task in all_tasks:
        notes = []
        for note in all_notes:
            if note['item_id'] == task['id']:
                notes.append(note['content'])
        task['notes'] = notes


def gather_metadata(todoist_api: todoist.TodoistAPI = None):
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()
    # Todoist
    print("Todoist Projects:")
    for prj in todoist_api.state['projects']:
        print(f"name: {prj['name']}; id: {prj['id']}")
    print("Todoist Labels:")
    for prj in todoist_api.state['labels']:
        print(f"name: {prj['name']}; id: {prj['id']}")

    # Notion
    # db_list = notion.read_databases_list()
    # print("databases list: ", db_list)
    maintenance_metadata = notion.read_database_metadata(secrets.MAINTENANCE_DATABASE_ID)
    print("Maintenance DB metadata:")
    p_dict = {k: {'type': v['type'], v['type']: v[v['type']] if len(v[v['type']]) > 0 else None} for k, v in
              maintenance_metadata['properties'].items()}
    print(f"id: {maintenance_metadata['id']}; name: {maintenance_metadata['title'][0]['plain_text']};\n"
          f"properties: {p_dict}")


def sync_periodic_actions():
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()
    # gather_metadata(todoist_api)

    # 1.Get completed tasks from Todoist
    completed_tasks = todoist_api.completed.get_all(project_id=secrets.MAINTENANCE_PROJECT_ID)['items']
    by_task_id_filter = list(
        {"property": "TodoistTaskId", "text": {"equals": str(task['task_id'])}} for task in completed_tasks)

    # 2.Create history records in Notion for each completed task
    query = {"filter": {"or": by_task_id_filter}}
    completed_actions = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, query, log_to_file=True)

    history_records_ids = []
    for action in completed_actions:
        completed_task = list(filter(
            lambda ct: str(ct['task_id']) == pparser.rich_text(action, 'TodoistTaskId'), completed_tasks))[0]
        detailed_task = todoist_api.items.get_by_id(completed_task['task_id'])
        append_notes_to_tasks([detailed_task], todoist_api)
        success, page = create_history_record(action['id'], detailed_task)
        if success:
            history_records_ids.append(page['id'])

    # 3.Gather notion maintenance actions [without TodoistTaskId and not OnHold] or [completed from previous step]
    empty_task_id_filter = {"property": "TodoistTaskId", "text": {"is_empty": True}}
    not_on_hold_filter = {"property": "OnHold", "checkbox": {"equals": False}}
    completed_actions_filter = list(
        {"property": "History records", "relation": {"contains": page_id}} for page_id in history_records_ids)
    no_tasks_query = {
        "filter": {"or": [{"and": [empty_task_id_filter, not_on_hold_filter]}, *completed_actions_filter]}}
    actions_to_update = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, no_tasks_query, True)

    # 4.Create task in Todoist for each maintenance action without active link to by task_id
    dummy_task = {'id': '', 'user_id': ''}
    for action in actions_to_update:
        if pparser.generic_prop(action, 'OnHold'):
            action.update({"created_task": dummy_task})
            continue
        labels = []
        try:
            title = pparser.title(action, 'Sub-Topic')
            if len(pparser.generic_prop(action, 'Master Tags')) > 0:
                temp_list = list(tag['text'] for tag in pparser.generic_prop(action, 'TodoistTags')['array'])
                labels = list(x['plain_text'] for x in itertools.chain(*temp_list))
            _LOG.debug(f"creating task for action {title}")
            try:
                # Notion bug where it doesn't put date in Next action in some cases(e.x. if formula result is 'now()')
                due_date = {"string": pparser.formula_start_date(action, 'Next action')}
            except TypeError as e:
                _LOG.error(f"Error during parsing Next Action date property of {title}:", str(e))
                due_date = {"string": "today"}
        except Exception as e:
            _LOG.error("Error during parsing action action properties:", str(e))
            continue

        label_ids = list(label['id'] for label in todoist_api.labels.all(lambda l: l['name'] in labels))
        task = todoist_api.items.add(title, project_id=secrets.MAINTENANCE_PROJECT_ID, labels=label_ids, due=due_date)
        _LOG.debug(task)
        action.update({"created_task": task})
    todoist_api.commit()

    # 5.Save task_id to notion actions
    for atu in actions_to_update:
        # Check that task was created
        if 'created_task' in atu and 'user_id' in atu['created_task']:
            update_task_id(atu['id'], atu['created_task']['id'])


def sync_created_tasks():
    # content->title, todoist id, notes->paragraph block, label->Tag Vault, priority (not yet: creation time, due date)
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()

    # 1.Get tasks with notes from Todoist
    # all_tasks = todoist_api.items.all()
    all_tasks = get_recent_tasks(todoist_api, 15)

    append_notes_to_tasks(all_tasks, todoist_api)

    # 2.Get Notion Tag/Knowledge vault and create 'Todoist_tag to Notion Tag page_id' mapping
    tag_mapping = todoist_utils.get_label_tag_mapping(todoist_api)

    # 3. Get already created linked actions not to create dupes
    linked_actions_query = {"filter": {"property": "TodoistTaskId", "text": {"is_not_empty": True}}}
    linked_actions = notion.read_database(secrets.MASTER_TASKS_DB_ID, linked_actions_query)
    linked_task_ids = list(pparser.rich_text(action, 'TodoistTaskId') for action in linked_actions)

    # 4. Create not yet linked actions/tasks in Notion
    for task in all_tasks:
        if linked_task_ids.__contains__(str(task['id'])):
            print(f"linked task {task['id']=}; {task['content']}")
            continue
        # create_action_entry(tag_mapping, task)
        create_action_entry_v2(task)
