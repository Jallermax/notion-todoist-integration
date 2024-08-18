import logging
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


class Scenarios:
    def __init__(self):
        self.todoist_mapper = todoist_utils.TodoistToNotionMapper()
        self.todoist_fetcher = todoist_utils.TodoistFetcher()
        self.tasks_db_id = secrets.MASTER_TASKS_DB_ID

    def create_action_entry(self, task: TodoistTask):
        metadata = notion.read_database_metadata(self.tasks_db_id)['properties']

        notion_props, child_blocks = {}, []
        # Map task properties to Notion properties or child blocks
        for prop in todoist_utils.load_todoist_to_notion_mapper().keys():
            self.todoist_mapper.map_property(task, prop, metadata, notion_props, child_blocks, convert_md_links=True)

        # Map task comments to Notion properties or child blocks
        if task.comments:
            props, blocks = self.todoist_mapper.parse_prop_list([comment.content for comment in task.comments],
                                                                'comments', metadata, True)
            notion_props.update(props)
            child_blocks.extend(blocks)

        # Add parent page relation
        # TODO Extract to separate step after task sync to ensure all parent already created in Notion
        parent_page_id = self.todoist_mapper.extract_parent_notion_uuid(task)
        if parent_page_id:
            notion_props.update({PARENT_PROPERTY_NAME: PFormat.single_relation(parent_page_id)})

        synced_time = datetime.now(LOCAL_TIMEZONE).isoformat()
        notion_props.update({SYNCED_TIME_PROPERTY_NAME: PFormat.date(synced_time)})

        success, page = notion.create_page(self.tasks_db_id, *child_blocks, **notion_props)
        if success:
            _LOG.info(f"Page created: {page['url']}")
            task.notion_url = page['url']
        else:
            _LOG.error(f"Error creating page from {task=}\n\t{notion_props=}\n\t{child_blocks=}\n\t{page}")

    def append_comments_to_tasks(self, all_tasks: list[TodoistTask]):

        for task in [task for task in all_tasks if task.task.comment_count > 0]:
            comments = self.todoist_fetcher.todoist_api.get_comments(task_id=task.task.id)
            if comments:
                task.comments = comments

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

    def sync_created_tasks(self, all_tasks=False, sync_completed=False, todoist_id_text_prop=TODOIST_ID_PROP):

        # 1.Get tasks with notes from Todoist
        all_tasks = self.todoist_fetcher.todoist_api.get_tasks() if all_tasks \
            else self.todoist_fetcher.get_recently_added_tasks(get_completed=sync_completed)

        tasks: list[TodoistTask] = [TodoistTask(task=task) for task in all_tasks]
        # Sorting the list in place: Tasks with None parent_id come first to ensure parent linking
        tasks.sort(key=lambda x: (x.task.parent_id is not None, x.task.parent_id))

        self.append_comments_to_tasks(tasks)

        # 2. Get already synced notion tasks not to create dupes
        notion_tasks = notion.get_synced_notion_tasks(self.tasks_db_id, todoist_id_text_prop)
        linked_task_ids = list(PParser.rich_text(notion_task, todoist_id_text_prop) for notion_task in notion_tasks)

        # 3. Create not yet linked actions/tasks in Notion
        for task in [task for task in tasks if task.task.id not in linked_task_ids]:
            self.create_action_entry(task)

            # 4. Update Todoist task with Notion page reference
            notion_reference = f"[Notion]({task.notion_url})"
            task_description = task.task.description
            if not task_description:
                task_description = notion_reference
            elif notion_reference not in task_description:
                task_description = f"{notion_reference}\n{task_description}"
            self.todoist_fetcher.todoist_api.update_task(task.task.id, description=task_description)

    def sync_updated_tasks(self, sync_created=True, sync_completed=True,
                           todoist_id_text_prop=TODOIST_ID_PROP,
                           last_synced_date_prop=SYNCED_TIME_PROPERTY_NAME):
        # get relevant prop updates mappings
        updated_tasks, updated_events = self.todoist_fetcher.get_updated_tasks(sync_created, sync_completed)
        updated_tasks = [TodoistTask(task=task) for task in updated_tasks]
        self.append_comments_to_tasks(updated_tasks)

        entries_to_update = notion.get_notion_tasks_before_time(self.tasks_db_id, todoist_id_text_prop,
                                                                last_synced_date_prop, updated_tasks, updated_events)
        # Filter notion entries by date and time since api call filters only by date ignoring time
        entries_to_update = [e for e in entries_to_update if
                             PParser.date(e, last_synced_date_prop) < updated_events[
                                 PParser.rich_text(e, todoist_id_text_prop)]]

        metadata = notion.read_database_metadata(self.tasks_db_id)['properties']
        for entry in entries_to_update:
            todoist_task = next(
                filter(lambda x: str(x['id']) == PParser.rich_text(entry, todoist_id_text_prop), updated_tasks))
            props_to_check_for_upd = ['content', 'due.date', 'checked', 'priority', 'notes']
            props_to_upd = self.todoist_mapper.update_properties(entry, todoist_task, props_to_check_for_upd, metadata)

            if props_to_upd:
                props_to_upd[last_synced_date_prop] = PFormat.date(datetime.now(LOCAL_TIMEZONE).isoformat())
                success, page = notion.update_page(entry['id'], **props_to_upd)
                if success:
                    _LOG.info(f"Notion task '{PParser.title(entry, 'Name')}' was updated: {page['url']}")
                else:
                    _LOG.error(
                        f"Error updating Notion task '{PParser.title(entry, 'Name')}', {props_to_upd=}: {entry['url']=}")

    def sync_deleted_tasks(self, todoist_id_text_prop=TODOIST_ID_PROP,
                           last_synced_date_prop=SYNCED_TIME_PROPERTY_NAME):
        notion_tasks_to_delete = self.get_notion_tasks_to_delete(todoist_id_text_prop)

        synced_time = datetime.now(LOCAL_TIMEZONE).isoformat()
        update_to_delete = {last_synced_date_prop: PFormat.date(synced_time)}

        for task in notion_tasks_to_delete:
            success, page = notion.update_page(task['id'], archive=True, **update_to_delete)
            if success:
                _LOG.info(f"Notion task '{PParser.title(task, 'Name')}' was archived: {page['url']}")
            else:
                _LOG.error(f"Error archiving Notion task '{PParser.title(task, 'Name')}': {task['url']=}")

    def get_notion_tasks_to_delete(self, todoist_id_text_prop):
        events = self.todoist_fetcher.get_events(object_type='item', event_type='deleted')
        if not events:
            return []
        deleted_tasks_id = [str(x['object_id']) for x in events]
        by_deleted_id_filter = [Filter.RichText(todoist_id_text_prop).equals(del_id) for del_id in deleted_tasks_id]
        query = Filter.Or(*by_deleted_id_filter)
        entries_to_delete = notion.read_database(self.tasks_db_id, query)
        return entries_to_delete


def update_task_id(page_id, task_id):
    task_link = f"https://todoist.com/showTask?id={task_id}"
    success, page = notion.update_page(page_id, TodoistTaskId=PFormat.rich_text([PFormat.link(task_id, task_link)]))
    if not success:
        _LOG.error(f"Error adding TodoistTaskId={task_id} to notion task '{page['url']}'")

