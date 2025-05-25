import logging

from todoist_sync_manager import TodoistSyncManager

logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.INFO)

if __name__ == '__main__':
    scenarios = TodoistSyncManager()
    print('Started scenarios...')
    # gather_metadata(todoist_api)
    scenarios.sync_created_tasks(all_tasks=True, sync_completed=False, overwrite_existing_backlinks=True)  # One time migration of all tasks to Notion
    # while True:
    #     scenarios.sync_deleted_tasks()
    #     scenarios.sync_updated_tasks()
    #     scenarios.sync_created_tasks(sync_completed=True)
    #     # sync_periodic_actions()
    #     time.sleep(60)
