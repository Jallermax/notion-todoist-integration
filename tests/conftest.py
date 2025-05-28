"""
Pytest configuration and shared fixtures for TodoistTask hierarchy tests.
"""

import pytest
import random
from typing import List, Optional
from unittest.mock import MagicMock
from todoist_api_python.models import Task, Comment
from models import TodoistTask


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "performance: mark test as a performance test"
    )
    config.addinivalue_line(
        "markers", "slow: mark test as slow running"
    )
    config.addinivalue_line(
        "markers", "integration: mark test as integration test"
    )


@pytest.fixture(scope="session")
def seed_random():
    """Set random seed for reproducible tests."""
    random.seed(42)


@pytest.fixture
def mock_task_factory():
    """Factory for creating mock Todoist Task objects."""
    def _create_mock_task(task_id: str, parent_id: Optional[str] = None,
                         content: str = None, **kwargs) -> Task:
        mock_task = MagicMock(spec=Task)
        mock_task.id = task_id
        mock_task.parent_id = parent_id
        mock_task.content = content or f"Task {task_id}"

        # Set additional attributes
        for key, value in kwargs.items():
            setattr(mock_task, key, value)

        return mock_task
    return _create_mock_task


@pytest.fixture
def todoist_task_factory(mock_task_factory):
    """Factory for creating TodoistTask objects."""
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
def hierarchy_builder(todoist_task_factory):
    """Builder for creating TodoistTask hierarchies."""
    def _build_hierarchy(structure: dict) -> List[TodoistTask]:
        """
        Build hierarchy from structure dict.

        Example:
            structure = {
                "root1": ["child1", "child2"],
                "child1": ["grandchild1"],
                "root2": [],
            }
        """
        tasks = []

        # Create all tasks first
        all_task_ids = set(structure.keys())
        for children in structure.values():
            all_task_ids.update(children)

        # Determine roots (tasks not mentioned as children)
        children_ids = set()
        for children in structure.values():
            children_ids.update(children)

        root_ids = all_task_ids - children_ids

        # Create tasks
        for task_id in all_task_ids:
            parent_id = None
            # Find parent
            for potential_parent, children in structure.items():
                if task_id in children:
                    parent_id = potential_parent
                    break

            tasks.append(todoist_task_factory(task_id, parent_id))

        return tasks

    return _build_hierarchy


# Performance testing configuration
@pytest.fixture(scope="session")
def performance_config():
    """Configuration for performance tests."""
    return {
        "small_size": 100,
        "medium_size": 1000,
        "large_size": 5000,
        "max_execution_time": 1.0,  # seconds
    }
