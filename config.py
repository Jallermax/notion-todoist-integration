import os

from dotenv import load_dotenv

load_dotenv()

T_ZONE = os.getenv("T_ZONE", "UTC")

# Notion configuration
NOTION_TOKEN = os.getenv("NOTION_TOKEN")
MASTER_TAG_DB = os.getenv("MASTER_TAG_DB")
MASTER_TASKS_DB_ID = os.getenv("MASTER_TASKS_DB_ID")

# Todoist configuration
TODOIST_TOKEN = os.getenv("TODOIST_TOKEN")
