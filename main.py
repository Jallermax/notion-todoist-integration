import logging
import datetime
import time
import pytz
import secrets
import notion
import todoist
from notion import PropertyFormatter as pformat

LOCAL_TIMEZONE = pytz.timezone("Europe/Moscow")

_LOG = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.INFO)


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    notion.update_page(page_id, TodoistTaskId=pformat.rich_text_link(str(task_id), task_link))


def create_history_record(action_id, task):
    task_id = str(task['id'])
    dt = task['date_completed']
    desc = task['description']

    if dt:
        dt = LOCAL_TIMEZONE.normalize(
            pytz.timezone("UTC").localize(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ")))
    else:
        dt = LOCAL_TIMEZONE.localize(datetime.datetime.now())
    title = dt.strftime('%y.%m.%d') + ('' if desc == '' else ' ' + desc)
    task_link = f"https://todoist.com/showTask?id={task_id}"

    return notion.create_page(secrets.HISTORY_DATABASE_ID,
                              Record=pformat.title(title),
                              Completed=pformat.date(dt.isoformat()),
                              Action=pformat.relation(action_id),
                              TodoistTaskId=pformat.rich_text_link(task_id, task_link))


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


def main():
    todoist_api = todoist.api.TodoistAPI(token=secrets.TODOIST_TOKEN)
    todoist_api.sync()
    # gather_metadata(todoist_api)

    # 1.Get completed tasks from Todoist
    completed_tasks = todoist_api.completed.get_all(project_id=secrets.MAINTENANCE_PROJECT_ID)['items']
    or_filter_conditions = list(
        {"property": "TodoistTaskId", "text": {"equals": str(task['task_id'])}} for task in completed_tasks)

    # 2.Create history records in Notion for each completed task
    query = {"filter": {"or": or_filter_conditions}}
    completed_actions = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, query, log_to_file=True)

    history_records_ids = []
    for action in completed_actions['results']:
        completed_task = list(filter(
            lambda ct: str(ct['task_id']) == action['properties']['TodoistTaskId']['rich_text'][0]['plain_text'],
            completed_tasks))[0]  # TODO find a better way to reduce to complete_date
        detailed_task = todoist_api.items.get_by_id(completed_task['task_id'])
        history_records_ids.append(create_history_record(action['id'], detailed_task)['id'])

    # 3.Gather notion maintenance actions without Todoist task_id
    empty_task_id_condition = {"property": "TodoistTaskId", "text": {"is_empty": True}}
    completed_actions_filter = list(
        {"property": "History records", "relation": {"contains": page_id}} for page_id in history_records_ids)
    no_tasks_query = {"filter": {"or": [empty_task_id_condition, *completed_actions_filter]}}
    actions_to_update = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, no_tasks_query, True)

    # 4.Create task in Todoist for each maintenance action without active link to by task_id
    for action in actions_to_update['results']:
        try:
            title = action['properties']['Sub-Topic']['title'][0]['plain_text']
            _LOG.debug(f"creating task for action {title}")
            try:
                # Notion bug? where it doesn't put date in Next action if formula result is 'now()'
                due_date = {"string": action['properties']['Next action']['formula']['date']['start']}
            except TypeError as e:
                _LOG.error(f"Error during parsing Next Action date property of {title}:", str(e))
                due_date = {"string": "today"}
        except Exception as e:
            _LOG.error("Error during parsing action action properties:", str(e))
            continue
        task = todoist_api.items.add(title, project_id=secrets.MAINTENANCE_PROJECT_ID, due=due_date)
        _LOG.debug(task)
        action.update({"created_task": task})
    todoist_api.commit()

    # 5.Save task_id to notion actions
    for atu in actions_to_update['results']:
        # Check that task was created
        if 'created_task' in atu and 'user_id' in atu['created_task']:
            update_task_id(atu['id'], atu['created_task']['id'])


if __name__ == '__main__':
    while True:
        main()
        time.sleep(20)
