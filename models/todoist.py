from dataclasses import dataclass, field

from todoist_api_python.models import (Task, Comment)


@dataclass
class TodoistTask:
    task: Task
    comments: list[Comment] = field(default_factory=list)
    notion_url: str | None = None
