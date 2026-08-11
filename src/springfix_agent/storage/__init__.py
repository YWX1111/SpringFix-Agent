"""Storage layer: persistence Protocol and domain models.

M0 defines only the Protocol and data classes.
``InMemoryTaskRepository`` implementation lands in M1; ``SqliteTaskRepository`` in M4A.
"""

from springfix_agent.storage.models import Report, Task, TaskStatus, Trace
from springfix_agent.storage.repository import TaskRepository

__all__ = ["TaskRepository", "Task", "TaskStatus", "Trace", "Report"]
