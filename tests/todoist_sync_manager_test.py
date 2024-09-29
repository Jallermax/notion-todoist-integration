import unittest
from unittest.mock import patch, MagicMock

from todoist_sync_manager import TodoistSyncManager
from todoist_utils import TodoistTask


class TestTodoistSyncManager(unittest.TestCase):

    @patch('todoist_utils.load_todoist_to_notion_mapper', return_value = {})
    def setUp(self, mock_load_mapper):
        self.manager = TodoistSyncManager()
        self.manager.todoist_fetcher = MagicMock()
        self.manager.todoist_fetcher.todoist_api = MagicMock()

    def test_update_task_no_notion_url(self):
        task = TodoistTask(MagicMock(content="Test Task", description=""))
        task.notion_url = None

        with self.assertLogs(level='WARNING') as log:
            self.manager._update_todoist_task_with_notion_link(task)

        self.assertIn("Task 'Test Task' has no Notion page reference", log.output[0])
        self.manager.todoist_fetcher.todoist_api.update_task.assert_not_called()

    def test_update_task_no_existing_description(self):
        task = TodoistTask(MagicMock(id="123", content="Test Task", description=""))
        task.notion_url = "https://notion.so/page"

        self.manager._update_todoist_task_with_notion_link(task)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/page)"
        )

    def test_update_task_existing_description_no_notion_link(self):
        task = TodoistTask(MagicMock(id="123", content="Test Task", description="Existing description"))
        task.notion_url = "https://notion.so/page"

        self.manager._update_todoist_task_with_notion_link(task)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/page)\nExisting description"
        )

    def test_update_task_existing_description_with_notion_link(self):
        task = TodoistTask(MagicMock(id="123", content="Test Task",
                                     description="[Notion](https://notion.so/page)\nExisting description"))
        task.notion_url = "https://notion.so/page"

        self.manager._update_todoist_task_with_notion_link(task)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/page)\nExisting description"
        )

    def test_update_task_overwrite_existing(self):
        task = TodoistTask(MagicMock(id="123", content="Test Task", description="[Notion]"
        "(https://www.notion.so/Old-Page-21ada7d4-5a93-45d1-ada7-d45a9305d182)\nExisting description\nThird line.  \n"))
        task.notion_url = "https://www.notion.so/newpage"

        self.manager._update_todoist_task_with_notion_link(task, overwrite_existing=True)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://www.notion.so/newpage)\nExisting description\nThird line."
        )

    def test_update_task_overwrite_existing_no_previous_link(self):
        task = TodoistTask(MagicMock(id="123", content="Test Task", description="Existing description"))
        task.notion_url = "https://notion.so/newpage"

        self.manager._update_todoist_task_with_notion_link(task, overwrite_existing=True)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/newpage)\nExisting description"
        )

    # @patch('todoist_utils.NOTION_SHORTHAND_LINK_PATTERN', re.compile(r'\[Notion\]\(.*?\)'))
    def test_update_task_overwrite_existing_with_shorthand_link(self):
        task = TodoistTask(
            MagicMock(id="123", content="Test Task", description="[Notion]"
            "(https://www.notion.so/username/Page-21ada7d4-5a93-45d1-ada7-d45a9305d182) Existing description"))
        task.notion_url = "https://notion.so/newpage"

        self.manager._update_todoist_task_with_notion_link(task, overwrite_existing=True)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/newpage)\nExisting description"
        )


    def test_update_task_overwrite_existing_with_shorthand_invalid_link(self):
        task = TodoistTask(
            MagicMock(id="123", content="Test Task", description="[Notion](not notion link)\nExisting description"))
        task.notion_url = "https://notion.so/newpage"

        self.manager._update_todoist_task_with_notion_link(task, overwrite_existing=True)

        self.manager.todoist_fetcher.todoist_api.update_task.assert_called_once_with(
            "123", description="[Notion](https://notion.so/newpage)\n[Notion](not notion link)\nExisting description"
        )


if __name__ == '__main__':
    unittest.main()