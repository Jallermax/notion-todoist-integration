import logging
import re
from datetime import datetime

import pytz

import notion
import secrets
import todoist_utils
from notion import PropertyFormatter as PFormat
from notion import PropertyParser as PParser
from notion_filters import Filter
from todoist_utils import TodoistTask

TODOIST_ID_PROP = 'TodoistTaskId'
SYNCED_TIME_PROPERTY_NAME = 'Synced'
PARENT_PROPERTY_NAME = 'Parent item'

_LOG = logging.getLogger(__name__)
LOCAL_TIMEZONE = pytz.timezone(secrets.T_ZONE)


class TodoistSyncManager:
    def __init__(self):
        self.todoist_mapper = todoist_utils.TodoistToNotionMapper()
        self.todoist_fetcher = todoist_utils.TodoistFetcher()
        self.tasks_db_id = secrets.MASTER_TASKS_DB_ID

    def sync_all(self):
        self.sync_created_tasks(all_tasks=False, sync_completed=False)
        self.sync_updated_tasks(sync_created=False, sync_completed=True)
        self.sync_deleted_tasks()

    def create_notion_task(self, task: TodoistTask):
        metadata = notion.read_database_metadata(self.tasks_db_id)['properties']
        notion_props, child_blocks = self.todoist_mapper.map_todoist_to_notion_task(task, metadata, PARENT_PROPERTY_NAME)

        synced_time = datetime.now(LOCAL_TIMEZONE).isoformat()
        notion_props.update({SYNCED_TIME_PROPERTY_NAME: PFormat.date(synced_time)})

        success, page = notion.create_page(self.tasks_db_id, *child_blocks, **notion_props)
        if success:
            _LOG.info(f"Page created: {page['url']}")
            task.notion_url = page['url']
        else:
            _LOG.error(f"Error creating page from {task=}\n\t{notion_props=}\n\t{child_blocks=}\n\t{page}")

    def gather_metadata(self):
        # Todoist
        print("Todoist Projects:")
        for prj in self.todoist_fetcher.todoist_api.get_projects():
            print(f"name: {prj.name}; id: {prj.id}")
        print("Todoist Labels:")
        for label in self.todoist_fetcher.todoist_api.get_labels():
            print(f"name: {label.name}; id: {label.id}")

        # Notion
        # db_list = notion.read_databases_list()
        # print("databases list: ", db_list)
        master_tasks_db_metadata = notion.read_database_metadata(self.tasks_db_id)
        print("Master task DB metadata:")
        p_dict = {k: {'type': v['type'], v['type']: v[v['type']] if len(v[v['type']]) > 0 else None} for k, v in
                  master_tasks_db_metadata['properties'].items()}
        print(f"id: {master_tasks_db_metadata['id']}; name: {master_tasks_db_metadata['title'][0]['plain_text']};\n"
              f"properties: {p_dict}")

    def sync_created_tasks(self, all_tasks=False, sync_completed=False, overwrite_existing_backlinks=False):

        # 1.Get tasks with notes from Todoist
        all_tasks = self.todoist_fetcher.todoist_api.get_tasks() if all_tasks \
            else self.todoist_fetcher.get_recently_added_tasks(get_completed=sync_completed)

        tasks: list[TodoistTask] = [TodoistTask(task=task) for task in all_tasks]
        # Sorting the list in place: Tasks with None parent_id come first to ensure parent linking
        tasks.sort(key=lambda x: (x.task.parent_id is not None, x.task.parent_id))

        self.todoist_fetcher.append_comments(tasks)

        # 2. Get already synced notion tasks not to create dupes
        notion_tasks = notion.get_synced_notion_tasks(self.tasks_db_id, TODOIST_ID_PROP)
        linked_task_ids = list(PParser.rich_text(notion_task, TODOIST_ID_PROP) for notion_task in notion_tasks)

        # 3. Create not yet linked actions/tasks in Notion
        for task in [task for task in tasks if task.task.id not in linked_task_ids]:
            self.create_notion_task(task)
            # 4. Update Todoist task with Notion page reference
            self._update_todoist_task_with_notion_link(task, overwrite_existing=overwrite_existing_backlinks)

    def _update_todoist_task_with_notion_link(self, task: TodoistTask, overwrite_existing: bool = False) -> None:
        if not task.notion_url:
            _LOG.warning(f"Task '{task.task.content}' has no Notion page reference")
            return
        notion_reference = f"[Notion]({task.notion_url})"
        task_description = task.task.description
        if not task_description:
            task_description = notion_reference
        elif notion_reference not in task_description:
            if overwrite_existing:
                task_description = re.sub(todoist_utils.NOTION_SHORTHAND_LINK_PATTERN, "", task_description).strip()
            task_description = f"{notion_reference}\n{task_description}"
        self.todoist_fetcher.todoist_api.update_task(task.task.id, description=task_description)

    def sync_updated_tasks(self, sync_created=True, sync_completed=True):
        # get relevant prop updates mappings
        updated_tasks, updated_events = self.todoist_fetcher.get_updated_tasks(sync_created, sync_completed)
        updated_tasks = [TodoistTask(task=task) for task in updated_tasks]
        self.todoist_fetcher.append_comments(updated_tasks)

        entries_to_update = notion.get_notion_tasks_before_time(self.tasks_db_id, TODOIST_ID_PROP,
                                                                SYNCED_TIME_PROPERTY_NAME, updated_tasks,
                                                                updated_events)
        # Filter notion entries by date and time since api call filters only by date ignoring time
        entries_to_update = [e for e in entries_to_update if
                             PParser.date(e, SYNCED_TIME_PROPERTY_NAME) < updated_events[
                                 PParser.rich_text(e, TODOIST_ID_PROP)]]

        metadata = notion.read_database_metadata(self.tasks_db_id)['properties']
        for entry in entries_to_update:
            todoist_task = next(
                filter(lambda x: str(x['id']) == PParser.rich_text(entry, TODOIST_ID_PROP), updated_tasks))
            props_to_check_for_upd = ['content', 'due.date', 'checked', 'priority', 'notes']
            props_to_upd = self.todoist_mapper.update_properties(entry, todoist_task, props_to_check_for_upd, metadata)

            if props_to_upd:
                props_to_upd[SYNCED_TIME_PROPERTY_NAME] = PFormat.date(datetime.now(LOCAL_TIMEZONE).isoformat())
                success, page = notion.update_page(entry['id'], **props_to_upd)
                if success:
                    _LOG.info(f"Notion task '{PParser.title(entry, 'Name')}' was updated: {page['url']}")
                else:
                    _LOG.error(
                        f"Error updating Notion task '{PParser.title(entry, 'Name')}', {props_to_upd=}: {entry['url']=}")

    def sync_deleted_tasks(self) -> None:
        events = self.todoist_fetcher.get_events(object_type='item', event_type='deleted')
        if not events:
            return
        deleted_tasks_id = [str(x['object_id']) for x in events]
        notion_tasks_to_delete = self._get_notion_tasks_to_delete(TODOIST_ID_PROP, deleted_tasks_id)

        synced_time = datetime.now(LOCAL_TIMEZONE).isoformat()
        update_to_delete = {SYNCED_TIME_PROPERTY_NAME: PFormat.date(synced_time)}

        for task in notion_tasks_to_delete:
            success, page = notion.update_page(task['id'], archive=True, **update_to_delete)
            if success:
                _LOG.info(f"Notion task '{PParser.title(task, 'Name')}' was archived: {page['url']}")
            else:
                _LOG.error(f"Error archiving Notion task '{PParser.title(task, 'Name')}': {task['url']=}")

    def _get_notion_tasks_to_delete(self, prop_name: str, deleted_tasks_id: list[str]):
        by_deleted_id_filter = [Filter.RichText(prop_name).equals(del_id) for del_id in deleted_tasks_id]
        query = Filter.Or(*by_deleted_id_filter)
        entries_to_delete = notion.read_database(self.tasks_db_id, query)
        return entries_to_delete


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    success, page = notion.update_page(page_id, TodoistTaskId=PFormat.rich_text([PFormat.link(task_id, task_link)]))
    if not success:
        _LOG.error(f"Error adding TodoistTaskId={task_id} to notion task '{page['url']}'")

