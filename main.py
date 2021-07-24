import logging
import time

from scenarios import sync_periodic_actions, sync_created_tasks, sync_deleted_tasks, sync_updated_tasks

logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.DEBUG)
logging.getLogger('urllib3').setLevel(logging.INFO)

if __name__ == '__main__':
    print('Started scenarios...')
    # gather_metadata(todoist_api)
    sync_created_tasks(all_tasks=True, sync_completed=True)  # One time migration of all tasks to Notion
    while True:
        sync_deleted_tasks()
        sync_updated_tasks()
        sync_created_tasks(sync_completed=True)
        sync_periodic_actions()
        time.sleep(60)
