import unittest
from unittest.mock import patch, MagicMock
from todoist_utils import TodoistToNotionMapper, TodoistTask

class TestTodoistToNotionMapper(unittest.TestCase):

    @patch('todoist_utils.load_todoist_to_notion_mapper')
    @patch('todoist_utils.TodoistAPI')
    def setUp(self, mock_api, mock_load_mapper):
        mock_load_mapper.return_value = {}  # Return an empty dict for mappings
        self.mapper = TodoistToNotionMapper()
        self.mock_api = mock_api

    def test_extract_parent_notion_uuid_no_parent(self):
        task = TodoistTask(MagicMock(parent_id=None))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertIsNone(result)

    def test_extract_parent_notion_uuid_no_notion_link(self):
        parent_task = MagicMock(description="No Notion link here")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertIsNone(result)

    def test_extract_parent_notion_uuid_full_link(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/username/Page-bf98f999c90a41e198f999c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999c90a41e198f999c90a01e1d2")

    def test_extract_parent_notion_uuid_no_username(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/Page-bf98f999c90a41e198f999c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999c90a41e198f999c90a01e1d2")

    def test_extract_parent_notion_uuid_no_page_name(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/bf98f999c90a41e198f999c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999c90a41e198f999c90a01e1d2")

    def test_extract_parent_notion_uuid_with_query_params(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/username/Page-bf98f999c90a41e198f999c90a01e1d2?pvs=4)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999c90a41e198f999c90a01e1d2")

    def test_extract_parent_notion_uuid_without_notion_host(self):
        parent_task = MagicMock(description="[Page](/username/Page-bf98f999c90a41e198f999c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999c90a41e198f999c90a01e1d2")

    def test_extract_parent_notion_uuid_with_dashes(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/username/Page-bf98f999-c90a-41e1-98f9-99c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999-c90a-41e1-98f9-99c90a01e1d2")

    def test_extract_parent_notion_uuid_only(self):
        parent_task = MagicMock(description="[Page](/bf98f999-c90a-41e1-98f9-99c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999-c90a-41e1-98f9-99c90a01e1d2")

    def test_extract_parent_notion_uuid_without_page_name(self):
        parent_task = MagicMock(description="[Page](https://www.notion.so/username/bf98f999-c90a-41e1-98f9-99c90a01e1d2)")
        self.mock_api.return_value.get_task.return_value = parent_task
        task = TodoistTask(MagicMock(parent_id="parent_id"))
        result = self.mapper.extract_parent_notion_uuid(task)
        self.assertEqual(result, "bf98f999-c90a-41e1-98f9-99c90a01e1d2")

if __name__ == '__main__':
    unittest.main()