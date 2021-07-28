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
LOCAL_TIMEZONE = pytz.timezone(secrets.T_ZONE)


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    success, page = notion.update_page(page_id, TodoistTaskId=pformat.rich_text([pformat.link(task_id, task_link)]))
    if not success:
        _LOG.error(f"Error adding TodoistTaskId={task_id} to notion task '{page['url']}'")


def create_history_entry(action_id, task) -> (bool, object):
    task_id = str(task['id'])
    dt = task['date_completed']
    child_blocks = []
    if task['notes']:
        child_blocks.append(pformat.heading_block("Notes", 2))
        child_blocks.append(pformat.paragraph_text_block(*task['notes']))

    if dt:
        dt = LOCAL_TIMEZONE.normalize(
            pytz.timezone("UTC").localize(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ")))
    else:
        dt = LOCAL_TIMEZONE.localize(datetime.datetime.now())
    title = dt.strftime('%y.%m.%d')
    task_link = f"https://todoist.com/showTask?id={task_id}"

    return notion.create_page(secrets.HISTORY_DATABASE_ID,
                              *child_blocks,
                              Record=pformat.single_title(title),
                              Completed=pformat.date(dt.date().isoformat(), localize=False),
                              Action=pformat.single_relation(action_id),
                              TodoistTaskId=pformat.rich_text([pformat.link(task_id, task_link)]))


def create_action_entry(todoist_api: todoist.TodoistAPI, task):
    metadata = notion.read_database_metadata(secrets.MASTER_TASKS_DB_ID)['properties']

    # TODO iterate through all keys in mappings for particular scenario instead of manually map each property type
    notion_task, child_blocks = todoist_utils.map_property(task, 'content', metadata, convert_md_links=True)
    todoist_utils.map_property(task, 'due.date', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'id', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'checked', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'notes', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'project_id', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'priority', metadata, notion_task, child_blocks)
    todoist_utils.map_property(task, 'labels', metadata, notion_task, child_blocks)

    parent_page_id = todoist_utils.extract_link_to_parent(task, todoist_api)
    if parent_page_id:
        notion_task.update({"Waiting_for": pformat.single_relation(parent_page_id)})
    synced_time = datetime.datetime.now(LOCAL_TIMEZONE).isoformat()
    notion_task.update({"Synced": pformat.date(synced_time)})

    success, page = notion.create_page(secrets.MASTER_TASKS_DB_ID, *child_blocks, **notion_task)
    if success:
        _LOG.info(f"Page created: {page['url']}")
        notion_reference = f"[Notion]({page['url']})"
        task.update(description=notion_reference)
    else:
        _LOG.error(f"Error creating page from {task=}\n\t{notion_task=}\n\t{child_blocks=}\n\t{page}")


def get_recently_added_tasks(todoist_api: todoist.TodoistAPI = None, days_old=None, get_checked=True):
    if not todoist_api:
        todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
        todoist_api.sync()

    events = todoist_utils.get_events(object_type='item', event_type='added')
    created_tasks = list(x['object_id'] for x in events if
                         not days_old or datetime.datetime.strptime(x['event_date'], "%Y-%m-%dT%H:%M:%SZ") > (
                                 datetime.datetime.now() - datetime.timedelta(days=days_old)))
    _LOG.debug(f"Received {len(created_tasks)} recently created tasks" + (
        f" for the last {days_old} days" if days_old else ""))
    all_tasks = todoist_api.items.all(
        lambda x: (x['id'] in created_tasks and (get_checked or x['checked'] == 0)))
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


def sync_periodic_actions(todoist_id_text_prop='TodoistTaskId', on_hold_bool_prop="OnHold"):
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()

    # 1.Get completed tasks from Todoist
    completed_tasks = todoist_api.completed.get_all(project_id=secrets.MAINTENANCE_PROJECT_ID)['items']
    by_task_id_filter = list(
        {"property": todoist_id_text_prop, "text": {"equals": str(task['task_id'])}} for task in completed_tasks)

    # 2.Create history records in Notion for each completed task
    query = {"filter": {"or": by_task_id_filter}}
    completed_actions = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, query, log_to_file=True)

    history_records_ids = []
    for action in completed_actions:
        completed_task = list(filter(
            lambda ct: str(ct['task_id']) == pparser.rich_text(action, todoist_id_text_prop), completed_tasks))[0]
        detailed_task = todoist_api.items.get_by_id(completed_task['task_id'])
        append_notes_to_tasks([detailed_task], todoist_api)
        success, page = create_history_entry(action['id'], detailed_task)
        if success:
            history_records_ids.append(page['id'])
            _LOG.info(f"History record created: {page['url']}")
        else:
            _LOG.error(f"Error creating history record from {detailed_task=}")

    # 3.Gather notion maintenance actions [without TodoistTaskId and not OnHold] or [completed from previous step]
    empty_task_id_filter = {"property": todoist_id_text_prop, "text": {"is_empty": True}}
    not_on_hold_filter = {"property": on_hold_bool_prop, "checkbox": {"equals": False}}
    completed_actions_filter = list(
        {"property": "History records", "relation": {"contains": page_id}} for page_id in history_records_ids)
    no_tasks_query = {
        "filter": {"or": [{"and": [empty_task_id_filter, not_on_hold_filter]}, *completed_actions_filter]}}
    actions_to_update = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, no_tasks_query, True)

    # 4.Create task in Todoist for each maintenance action without active link to by task_id
    dummy_task = {'id': '', 'user_id': ''}
    for action in actions_to_update:
        if pparser.generic_prop(action, on_hold_bool_prop):
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
        _LOG.debug(f"{task=}")
        action.update({"created_task": task})
    todoist_api.commit()

    # 5.Save task_id to notion actions
    for atu in actions_to_update:
        # Check that task was created
        if 'created_task' in atu and 'user_id' in atu['created_task']:
            update_task_id(atu['id'], atu['created_task']['id'])


def sync_created_tasks(all_tasks=False, sync_completed=False, todoist_id_text_prop='TodoistTaskId'):
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()

    # 1.Get tasks with notes from Todoist
    all_tasks = todoist_api.items.all(
        lambda t: sync_completed or t['checked'] == 0) if all_tasks else get_recently_added_tasks(
        todoist_api, get_checked=sync_completed)

    append_notes_to_tasks(all_tasks, todoist_api)

    # 2. Get already created linked actions not to create dupes
    linked_actions_query = {"filter": {"property": todoist_id_text_prop, "text": {"is_not_empty": True}}}
    linked_actions = notion.read_database(secrets.MASTER_TASKS_DB_ID, linked_actions_query)
    linked_task_ids = list(pparser.rich_text(action, todoist_id_text_prop) for action in linked_actions)

    # 3. Create not yet linked actions/tasks in Notion
    try:
        for task in all_tasks:
            if str(task['id']) in linked_task_ids:
                continue
            create_action_entry(todoist_api, task)
    finally:
        # 4. Save Notion page reference to Todoist tasks' description
        todoist_api.commit()


def sync_deleted_tasks(todoist_id_text_prop='TodoistTaskId',
                       last_synced_date_prop='Synced'):
    notion_tasks_to_delete = get_notion_tasks_to_delete(todoist_id_text_prop)

    synced_time = datetime.datetime.now(LOCAL_TIMEZONE).isoformat()
    update_to_delete = {last_synced_date_prop: pformat.date(synced_time)}

    for task in notion_tasks_to_delete:
        success, page = notion.update_page(task['id'], archive=True, **update_to_delete)
        if success:
            _LOG.info(f"Notion task '{pparser.title(task, 'Name')}' was marked ToDelete: {page['url']}")
        else:
            _LOG.error(f"Error marking Notion task '{pparser.title(task, 'Name')}' ToDelete: {task['url']=}")


def chunks(lst, n):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def sync_updated_tasks(sync_created=True, sync_completed=True,
                       todoist_id_text_prop='TodoistTaskId',
                       last_synced_date_prop='Synced'):
    # get relevant prop updates mappings
    updated_tasks, updated_events = get_updated_tasks(sync_created, sync_completed)
    append_notes_to_tasks(updated_tasks)

    entries_to_update = []
    for upd_tasks_chunk in chunks(updated_tasks, 100):
        by_task_id_and_after_sync_filter = [
            {"and": [{"property": todoist_id_text_prop, "text": {"equals": str(upd_id['id'])}},
                     {"property": last_synced_date_prop,
                      "date": {"before": updated_events[upd_id['id']]}}]} for upd_id in upd_tasks_chunk]
        query = {"filter": {"or": by_task_id_and_after_sync_filter}}
        entries_to_update.extend(notion.read_database(secrets.MASTER_TASKS_DB_ID, query))

    metadata = notion.read_database_metadata(secrets.MASTER_TASKS_DB_ID)['properties']
    for entry in entries_to_update:
        todoist_task = next(
            filter(lambda x: str(x['id']) == pparser.rich_text(entry, todoist_id_text_prop), updated_tasks))
        props_to_check_for_upd = ['content', 'due.date', 'checked', 'priority']
        props_to_upd = todoist_utils.update_properties(entry, todoist_task, props_to_check_for_upd, metadata)

        if props_to_upd:
            props_to_upd[last_synced_date_prop] = pformat.date(datetime.datetime.now(LOCAL_TIMEZONE).isoformat())
            success, page = notion.update_page(entry['id'], **props_to_upd)
            if success:
                _LOG.info(f"Notion task '{pparser.title(entry, 'Name')}' was updated: {page['url']}")
            else:
                _LOG.error(
                    f"Error updating Notion task '{pparser.title(entry, 'Name')}', {props_to_upd=}: {entry['url']=}")


def get_updated_tasks(sync_created=True, sync_completed=True):
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()
    events = todoist_utils.get_events(object_type='item', event_type='updated')
    if sync_completed:
        events.extend(todoist_utils.get_events(object_type='item', event_type='completed'))
        # sort to have latest event_date after reducing to unique dict entry
        events.sort(key=lambda k: k['event_date'])
    updated_tasks_id = {x['object_id']: LOCAL_TIMEZONE.normalize(
        pytz.timezone("UTC").localize(datetime.datetime.strptime(x['event_date'], "%Y-%m-%dT%H:%M:%SZ"))).isoformat()
                        for x in events}

    tasks_to_exclude = []
    if not sync_created:
        events = todoist_utils.get_events(object_type='item', event_type='created')
        tasks_to_exclude.extend([x['object_id'] for x in events])
    tasks_to_exclude = list(set(tasks_to_exclude))
    for task_id in tasks_to_exclude:
        if not tasks_to_exclude or task_id in updated_tasks_id.keys():
            updated_tasks_id.pop(task_id)

    updated_tasks = todoist_api.items.all(
        lambda x: x['id'] in updated_tasks_id.keys() and (sync_completed or x['checked'] == 0))
    _LOG.debug(f"Received {len(updated_tasks)} updated tasks")
    return updated_tasks, updated_tasks_id


def get_notion_tasks_to_delete(todoist_id_text_prop):
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()
    events = todoist_utils.get_events(object_type='item', event_type='deleted')
    deleted_tasks_id = [str(x['object_id']) for x in events]
    by_deleted_id_filter = [{"property": todoist_id_text_prop, "text": {"equals": del_id}} for del_id in
                            deleted_tasks_id]
    query = {"filter": {"or": by_deleted_id_filter}}
    entries_to_delete = notion.read_database(secrets.MASTER_TASKS_DB_ID, query)
    return entries_to_delete
