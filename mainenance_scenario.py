# import datetime
# import itertools
# import logging
#
# import pytz
# from todoist_api_python.api import TodoistAPI
#
# import notion
# import config
# import todoist_utils
# from models import TodoistTask
# from notion import PropertyFormatter as PFormat
# from notion import PropertyParser as PParser
# from notion_filters import Filter
# from todoist_sync_manager import TodoistSyncManager
#
# _LOG = logging.getLogger(__name__)
# LOCAL_TIMEZONE = pytz.timezone(config.T_ZONE)
#
# scenarios = TodoistSyncManager()
#
# def sync_periodic_actions(todoist_id_text_prop='TodoistTaskId', on_hold_bool_prop="OnHold"):
#     todoist_api = TodoistAPI(token=config.TODOIST_TOKEN)
#     todoist_fetcher = todoist_utils.TodoistFetcher()
#
#     # 1.Get completed tasks from Todoist
#     completed_tasks = todoist_api.get_completed_items(project_id=config.MAINTENANCE_PROJECT_ID).items
#     by_task_id_filter = list(Filter.RichText(todoist_id_text_prop).equals(task.id) for task in completed_tasks)
#
#     # 2.Create history records in Notion for each completed task
#     query = Filter.Or(*by_task_id_filter)
#     completed_actions = notion.read_database(config.MAINTENANCE_DATABASE_ID, query, log_to_file=True)
#
#     history_records_ids = []
#     for action in completed_actions:
#         completed_task = list(filter(
#             lambda ct: ct.id == PParser.rich_text(action, todoist_id_text_prop), completed_tasks))[0]
#         detailed_task = todoist_api.get_task(completed_task.id)  # Get detailed task with completed date from events
#         todoist_fetcher.append_comments([TodoistTask(task=detailed_task)])
#         success, page = create_history_entry(action['id'], detailed_task)
#         if success:
#             history_records_ids.append(page['id'])
#             _LOG.info(f"History record created: {page['url']}")
#         else:
#             _LOG.error(f"Error creating history record from {detailed_task=}")
#
#     # 3.Gather notion maintenance actions [without TodoistTaskId and not OnHold] or [completed from previous step]
#     empty_task_id_filter = Filter.RichText(todoist_id_text_prop).is_empty()
#     not_on_hold_filter = Filter.Checkbox(on_hold_bool_prop).equals(False)
#     completed_actions_filter = [Filter.Relation('History records').contains(page_id) for page_id in history_records_ids]
#     no_tasks_query = Filter.Or(Filter.And(empty_task_id_filter, not_on_hold_filter), *completed_actions_filter)
#     actions_to_update = notion.read_database(config.MAINTENANCE_DATABASE_ID, no_tasks_query, True)
#
#     # 4.Create task in Todoist for each maintenance action without active link to by task_id
#     dummy_task = {'id': '', 'user_id': ''}
#     for action in actions_to_update:
#         if PParser.generic_prop(action, on_hold_bool_prop):
#             action.update({"created_task": dummy_task})
#             continue
#         labels = []
#         try:
#             title = PParser.title(action, 'Sub-Topic')
#             if len(PParser.generic_prop(action, 'Master Tags')) > 0:
#                 temp_list = list(tag['text'] for tag in PParser.generic_prop(action, 'TodoistTags')['array'])
#                 labels = list(x['plain_text'] for x in itertools.chain(*temp_list))
#             _LOG.debug(f"creating task for action {title}")
#             try:
#                 # Notion bug where it doesn't put date in Next action in some cases(e.x. if formula result is 'now()')
#                 due_date = {"string": PParser.formula_start_date(action, 'Next action')}
#             except TypeError as e:
#                 _LOG.error(f"Error during parsing Next Action date property of {title}:", str(e))
#                 due_date = {"string": "today"}
#         except Exception as e:
#             _LOG.error("Error during parsing action action properties:", str(e))
#             continue
#
#         label_ids = [label.id for label in todoist_api.get_labels() if label.name in labels]
#         task = todoist_api.items.add(title, project_id=config.MAINTENANCE_PROJECT_ID, labels=label_ids, due=due_date)
#         _LOG.debug(f"{task=}")
#         action.update({"created_task": task})
#     todoist_api.commit()
#
#     # 5.Save task_id to notion actions
#     for atu in actions_to_update:
#         # Check that task was created
#         if 'created_task' in atu and 'user_id' in atu['created_task']:
#             update_task_id(atu['id'], atu['created_task']['id'])
#
#
# def create_history_entry(action_id, task) -> (bool, object):
#     task_id = str(task['id'])
#     dt = task['date_completed']
#     child_blocks = []
#     if task['notes']:
#         child_blocks.append(PFormat.heading_block("Notes", 2))
#         child_blocks.append(PFormat.paragraph_text_block(*task['notes']))
#
#     if dt:
#         dt = LOCAL_TIMEZONE.normalize(
#             pytz.timezone("UTC").localize(datetime.datetime.strptime(dt, "%Y-%m-%dT%H:%M:%SZ")))
#     else:
#         dt = LOCAL_TIMEZONE.localize(datetime.datetime.now())
#     title = dt.strftime('%y.%m.%d')
#     task_link = f"https://todoist.com/showTask?id={task_id}"
#
#     return notion.create_page(config.HISTORY_DATABASE_ID,
#                               *child_blocks,
#                               Record=PFormat.single_title(title),
#                               Completed=PFormat.date(dt.date().isoformat(), localize=False),
#                               Action=PFormat.single_relation(action_id),
#                               TodoistTaskId=PFormat.rich_text([PFormat.link(task_id, task_link)]))
