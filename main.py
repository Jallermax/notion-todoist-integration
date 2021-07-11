import logging
import time

from scenarios import sync_periodic_actions, sync_created_tasks

logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.INFO)

if __name__ == '__main__':
    print('Started scenarios...')
    # sync_created_tasks(True)  # One time migration of all tasks to Notion
    while True:
        sync_created_tasks()
        sync_periodic_actions()
        time.sleep(60)
