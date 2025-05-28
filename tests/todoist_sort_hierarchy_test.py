"""
Test suite for TodoistTask hierarchy sorting algorithms.

This module contains comprehensive tests for task sorting that maintains
proper parent-child hierarchy ordering using actual Todoist data models.
"""

import random
import time
import unittest
from typing import List, Optional
from unittest.mock import MagicMock

import pytest
# Import your actual models and function
from todoist_api_python.models import Task, Comment

from models import TodoistTask
from todoist_sync_manager import sort_tasks_by_hierarchy


class TestTodoistTaskHierarchy:
    """Pytest-based test suite for TodoistTask hierarchy sorting."""

    # Test data fixtures
    @pytest.fixture
    def mock_task_factory(self):
        """Factory for creating mock Todoist Task objects."""

        def _create_mock_task(task_id: str, parent_id: Optional[str] = None,
                              content: str = None, **kwargs) -> Task:
            mock_task = MagicMock(spec=Task)
            mock_task.id = task_id
            mock_task.parent_id = parent_id
            mock_task.content = content or f"Task {task_id}"

            # Set any additional attributes
            for key, value in kwargs.items():
                setattr(mock_task, key, value)

            return mock_task

        return _create_mock_task

    @pytest.fixture
    def todoist_task_factory(self, mock_task_factory):
        """Factory for creating TodoistTask objects with mock Task."""

        def _create_todoist_task(task_id: str, parent_id: Optional[str] = None,
                                 content: str = None, notion_url: str = None,
                                 comments: List[Comment] = None) -> TodoistTask:
            mock_task = mock_task_factory(task_id, parent_id, content)
            return TodoistTask(
                task=mock_task,
                comments=comments or [],
                notion_url=notion_url
            )

        return _create_todoist_task

    @pytest.fixture
    def simple_hierarchy(self, todoist_task_factory):
        """Simple parent-child hierarchy."""
        return [
            todoist_task_factory("child", "parent", "Child Task"),
            todoist_task_factory("parent", None, "Parent Task"),
        ]

    @pytest.fixture
    def complex_hierarchy(self, todoist_task_factory):
        """Complex multi-level hierarchy with multiple roots."""
        return [
            todoist_task_factory("grandchild", "child1", "Grandchild"),
            todoist_task_factory("child1", "root1", "Child 1 of Root 1"),
            todoist_task_factory("root1", None, "Root Task 1"),
            todoist_task_factory("child2", "root1", "Child 2 of Root 1"),
            todoist_task_factory("root2", None, "Root Task 2"),
            todoist_task_factory("child3", "root2", "Child of Root 2"),
            todoist_task_factory("great_grandchild", "grandchild", "Great Grandchild"),
        ]

    @pytest.fixture
    def orphaned_tasks(self, todoist_task_factory):
        """Tasks with non-existent parent references."""
        return [
            todoist_task_factory("root", None, "Root Task"),
            todoist_task_factory("valid_child", "root", "Valid Child"),
            todoist_task_factory("orphan1", "nonexistent", "Orphaned Task 1"),
            todoist_task_factory("orphan2", "another_nonexistent", "Orphaned Task 2"),
        ]

    @pytest.fixture
    def linear_chain(self, todoist_task_factory):
        """Linear chain of tasks (worst case for some algorithms)."""
        return [
            todoist_task_factory("task5", "task4", "Task 5"),
            todoist_task_factory("task3", "task2", "Task 3"),
            todoist_task_factory("task1", None, "Task 1"),
            todoist_task_factory("task4", "task3", "Task 4"),
            todoist_task_factory("task2", "task1", "Task 2"),
        ]

    # Utility methods
    def verify_hierarchy_constraint(self, tasks: List[TodoistTask]) -> tuple[bool, str]:
        """Verify that parents always come before their children."""
        task_positions = {task.task.id: i for i, task in enumerate(tasks)}

        for task in tasks:
            if task.task.parent_id and task.task.parent_id in task_positions:
                parent_pos = task_positions[task.task.parent_id]
                child_pos = task_positions[task.task.id]
                if parent_pos >= child_pos:
                    return False, f"Parent '{task.task.parent_id}' (pos {parent_pos}) comes after child '{task.task.id}' (pos {child_pos})"

        return True, "Hierarchy constraint satisfied"

    def get_task_ids(self, tasks: List[TodoistTask]) -> List[str]:
        """Extract task IDs from TodoistTask list."""
        return [task.task.id for task in tasks]

    # Basic functionality tests
    def test_empty_list(self):
        """Test handling of empty task list."""
        result = sort_tasks_by_hierarchy([])
        assert result == []

    def test_single_task(self, todoist_task_factory):
        """Test handling of single task."""
        single_task = [todoist_task_factory("single", None, "Single Task")]
        result = sort_tasks_by_hierarchy(single_task)

        assert len(result) == 1
        assert result[0].task.id == "single"

    def test_simple_hierarchy(self, simple_hierarchy):
        """Test basic parent-child relationship."""
        result = sort_tasks_by_hierarchy(simple_hierarchy)

        assert len(result) == 2
        result_ids = self.get_task_ids(result)

        # Parent should come before child
        parent_idx = result_ids.index("parent")
        child_idx = result_ids.index("child")
        assert parent_idx < child_idx

        # Verify hierarchy constraint
        is_valid, message = self.verify_hierarchy_constraint(result)
        assert is_valid, message

    def test_complex_hierarchy(self, complex_hierarchy):
        """Test multi-level hierarchy with multiple roots."""
        result = sort_tasks_by_hierarchy(complex_hierarchy)

        assert len(result) == 7

        # Verify hierarchy constraint
        is_valid, message = self.verify_hierarchy_constraint(result)
        assert is_valid, message

        # Check specific relationships
        result_ids = self.get_task_ids(result)

        # Root1 before its children
        root1_idx = result_ids.index("root1")
        child1_idx = result_ids.index("child1")
        child2_idx = result_ids.index("child2")
        assert root1_idx < child1_idx
        assert root1_idx < child2_idx

        # Child1 before grandchild
        grandchild_idx = result_ids.index("grandchild")
        assert child1_idx < grandchild_idx

        # Grandchild before great_grandchild
        great_grandchild_idx = result_ids.index("great_grandchild")
        assert grandchild_idx < great_grandchild_idx

    def test_orphaned_tasks(self, orphaned_tasks):
        """Test handling of orphaned tasks (parent doesn't exist)."""
        result = sort_tasks_by_hierarchy(orphaned_tasks)

        assert len(result) == 4

        # Verify hierarchy constraint for valid relationships
        is_valid, message = self.verify_hierarchy_constraint(result)
        assert is_valid, message

        # Check that orphaned tasks are included
        result_ids = self.get_task_ids(result)
        assert "orphan1" in result_ids
        assert "orphan2" in result_ids

    def test_linear_chain(self, linear_chain):
        """Test linear chain of dependencies."""
        result = sort_tasks_by_hierarchy(linear_chain)

        assert len(result) == 5

        # Verify hierarchy constraint
        is_valid, message = self.verify_hierarchy_constraint(result)
        assert is_valid, message

        # Check the chain order
        result_ids = self.get_task_ids(result)
        expected_order = ["task1", "task2", "task3", "task4", "task5"]

        # Verify each task comes before its dependent
        for i in range(len(expected_order) - 1):
            current_idx = result_ids.index(expected_order[i])
            next_idx = result_ids.index(expected_order[i + 1])
            assert current_idx < next_idx

    def test_all_tasks_preserved(self, complex_hierarchy):
        """Test that all input tasks are preserved in output."""
        result = sort_tasks_by_hierarchy(complex_hierarchy)

        # Same number of tasks
        assert len(result) == len(complex_hierarchy)

        # Same task IDs
        input_ids = {task.task.id for task in complex_hierarchy}
        output_ids = {task.task.id for task in result}
        assert input_ids == output_ids

    def test_with_comments_and_notion_url(self, todoist_task_factory):
        """Test that TodoistTask attributes are preserved."""
        mock_comment = MagicMock(spec=Comment)
        mock_comment.content = "Test comment"

        tasks = [
            todoist_task_factory("parent", None, "Parent Task",
                                 notion_url="https://notion.so/parent",
                                 comments=[mock_comment]),
            todoist_task_factory("child", "parent", "Child Task",
                                 notion_url="https://notion.so/child"),
        ]

        result = sort_tasks_by_hierarchy(tasks)

        assert len(result) == 2
        # Find parent task in result
        parent_task = next(t for t in result if t.task.id == "parent")
        assert parent_task.notion_url == "https://notion.so/parent"
        assert len(parent_task.comments) == 1
        assert parent_task.comments[0].content == "Test comment"

    @pytest.mark.performance
    def test_performance_large_dataset(self, todoist_task_factory):
        """Test performance with large dataset."""
        # Generate large hierarchy
        tasks = []

        # Create root tasks
        num_roots = 10
        for i in range(num_roots):
            tasks.append(todoist_task_factory(f"root_{i}", None))

        # Create child tasks
        for i in range(num_roots, 1000):
            if random.random() < 0.8 and tasks:
                parent = random.choice(tasks)
                tasks.append(todoist_task_factory(f"task_{i}", parent.task.id))
            else:
                tasks.append(todoist_task_factory(f"task_{i}", None))

        # Shuffle to test algorithm robustness
        random.shuffle(tasks)

        start_time = time.perf_counter()
        result = sort_tasks_by_hierarchy(tasks)
        execution_time = time.perf_counter() - start_time

        # Should complete quickly
        assert execution_time < 1.0, f"Sorting 1000 tasks took {execution_time:.2f}s"

        # Verify correctness
        assert len(result) == 1000
        is_valid, message = self.verify_hierarchy_constraint(result)
        assert is_valid, message


# Integration helpers for existing unittest code
class TodoistTaskHierarchyTestMixin:
    """Mixin to add hierarchy testing capabilities to existing test classes."""

    def assert_hierarchy_valid(self, tasks: List[TodoistTask], msg: str = None):
        """Assert that task hierarchy constraint is satisfied."""
        task_positions = {task.task.id: i for i, task in enumerate(tasks)}

        for task in tasks:
            if task.task.parent_id and task.task.parent_id in task_positions:
                parent_pos = task_positions[task.task.parent_id]
                child_pos = task_positions[task.task.id]
                if parent_pos >= child_pos:
                    error_msg = f"Parent '{task.task.parent_id}' comes after child '{task.task.id}'"
                    if msg:
                        error_msg = f"{msg}: {error_msg}"
                    self.fail(error_msg)

    def assert_tasks_preserved(self, input_tasks: List[TodoistTask],
                               output_tasks: List[TodoistTask], msg: str = None):
        """Assert that all input tasks are preserved in output."""
        input_ids = {task.task.id for task in input_tasks}
        output_ids = {task.task.id for task in output_tasks}

        self.assertEqual(len(input_tasks), len(output_tasks),
                         msg or "Task count mismatch")
        self.assertEqual(input_ids, output_ids,
                         msg or "Task IDs don't match")


if __name__ == "__main__":
    # Run both pytest and unittest
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "pytest":
        pytest.main([__file__, "-v"])
    else:
        unittest.main()
