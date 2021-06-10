import logging
import datetime
import pytz
import secrets
import notion
import todoist
from notion import PropertyFormatter as pformat

_LOG = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.INFO)


def update_task_id(page_id, task_id):
    notion.update_page(page_id, {"properties": {"TodoistTaskId": pformat.rich_text(str(task_id))}})


def create_history_record(action_id, dt=None):
    if not dt:
        dt = pytz.timezone("Europe/Moscow").localize(datetime.datetime.now()).isoformat()
    notion.create_page(secrets.HISTORY_DATABASE_ID,
                       Name=pformat.title('Api'),
                       Completed={"date": {"start": dt}},
                       Action={"relation": [{"id": action_id}]})


def gather_metadata(todoist_api):
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
    for task1 in completed_tasks:
        or_filter_conditions.append({"property": "TodoistTaskId", "text": {"equals": str(task1['task_id'])}})

    # 2.Create history records in Notion for each completed task
    query = {"filter": {"or": or_filter_conditions}}
    completed_records = notion.read_database(secrets.MAINTENANCE_DATABASE_ID, query, log_to_file=True)
    for record in completed_records['results']:
        completed_dt = list(filter(
            lambda ct: str(ct['task_id']) == record['properties']['TodoistTaskId']['rich_text'][0]['plain_text'],
            completed_tasks))[0]['completed_date']  # TODO find a better way to reduce to complete_date
        # TODO produce completed_dt from UTC to Moscow time
        create_history_record(record['id'], dt=completed_dt)

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
            due_date = {"string": record['properties']['Next action']['formula']['date']['start']}
            # Sometimes Next action may be without date even though there's date in Notion GUI for this record
        except Exception as e:
            _LOG.error("Error during parsing record properties:", str(e))
            continue
        task = todoist_api.items.add(task_content, project_id=secrets.MAINTENANCE_PROJECT_ID, due=due_date)
        _LOG.debug(task)
        actions_to_update.append({"action_id": record['id'], "task": task})
    todoist_api.commit()

    # 5.Save task_id to notion actions
    for atu in actions_to_update:
        update_task_id(atu['action_id'], atu['task']['id'])


if __name__ == '__main__':
    main()
