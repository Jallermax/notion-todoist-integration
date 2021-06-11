import logging
import datetime
import time
import pytz
import secrets
import notion
import todoist
from notion import PropertyFormatter as pformat

TIMEZONE = "Europe/Moscow"

_LOG = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.INFO)


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    notion.update_page(page_id, TodoistTaskId=pformat.rich_text_link(str(task_id), task_link))


def create_history_record(action_id, task):
    dt = task['date_completed']
    if not dt:
        dt = pytz.timezone(TIMEZONE).localize(datetime.datetime.now()).isoformat()
    else:
        dt = pytz.timezone(TIMEZONE).normalize(
            pytz.timezone("UTC").localize(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ"))).isoformat()
    task_link = f"https://todoist.com/showTask?id={task['id']}"
    notion.create_page(secrets.HISTORY_DATABASE_ID,
                       Name=pformat.title('Api' if task['description'] == '' else task['description']),
                       Completed=pformat.date(dt),
                       Action=pformat.relation(action_id),
                       TodoistTaskId=pformat.rich_text_link(str(task['id']), task_link))


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
    or_filter_conditions = []
    for task in completed_tasks:
        or_filter_conditions.append({"property": "TodoistTaskId", "text": {"equals": str(task['task_id'])}})

    # 2.Create history records in Notion for each completed task
    query = {"filter": {"or": or_filter_conditions}}
    completed_records = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, query, log_to_file=True)
    for record in completed_records['results']:
        completed_task = list(filter(
            lambda ct: str(ct['task_id']) == record['properties']['TodoistTaskId']['rich_text'][0]['plain_text'],
            completed_tasks))[0]  # TODO find a better way to reduce to complete_date
        # TODO produce completed_dt from UTC to Moscow time
        detailed_task = todoist_api.items.get_by_id(completed_task['task_id'])
        create_history_record(record['id'], detailed_task)

    # 3.Gather notion maintenance actions without Todoist task_id
    no_tasks_query = {"filter": {"property": "TodoistTaskId", "text": {"is_empty": True}}}
    no_tasks_records = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, no_tasks_query, True)

    # 4.Create task in Todoist for each maintenance action without active link to by task_id
    no_tasks_records['results'].extend(completed_records['results'])
    actions_to_update = []  # TODO join no_tasks_records and actions_to_update into dict maybe?
    for record in no_tasks_records['results']:
        try:
            task_content = record['properties']['Sub-Topic']['title'][0]['plain_text']
            _LOG.debug(f"creating task for record {task_content}")
            try:
                # Sometimes Next action may be without date even though there's date in Notion GUI for this record
                due_date = {"string": record['properties']['Next action']['formula']['date']['start']}
            except TypeError as e:
                _LOG.error("Error during parsing Next Action date property:", str(e))
                due_date = {"string": "today"}
        except Exception as e:
            _LOG.error("Error during parsing action record properties:", str(e))
            continue
        task = todoist_api.items.add(task_content, project_id=secrets.MAINTENANCE_PROJECT_ID, due=due_date)
        _LOG.debug(task)
        actions_to_update.append({"action_id": record['id'], "task": task})
    todoist_api.commit()

    # 5.Save task_id to notion actions
    for atu in actions_to_update:
        # Check that task was created
        if atu['task']['user_id']:
            update_task_id(atu['action_id'], atu['task']['id'])


if __name__ == '__main__':
    while True:
        main()
        time.sleep(20)
