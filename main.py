import logging
import time

from scenarios import sync_periodic_actions, sync_all_tasks

_LOG = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s', level=logging.INFO)

if __name__ == '__main__':
    print('Started scenarios...')
    sync_all_tasks()
    while True:
        sync_periodic_actions()
        time.sleep(20)
