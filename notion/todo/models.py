
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional

class TodoPriority(Enum):
    DAILY_TOP_TASK = "Daily Top Task"
    HIGH = "Hoch"
    MEDIUM = "Mittel"
    LOW = "Niedrig"
    
    @classmethod
    def get_order(cls) -> Dict[str, int]:
        return {
            cls.DAILY_TOP_TASK.value: 1,
            cls.HIGH.value: 2,
            cls.MEDIUM.value: 3,
            cls.LOW.value: 4
        }


class TodoStatus(Enum):
    NOT_STARTED = "Nicht begonnen"
    IN_PROGRESS = "In Bearbeitung"
    DONE = "Erledigt"


@dataclass
class Todo:
    id: str
    title: str
    priority: str
    status: str
    done: bool
    project_ids: List[str]
    project_names: List[str]
    
    def format(self, index: Optional[int] = None) -> str:
        prefix = f"{index + 1}. " if index is not None else ""
        result = f"{prefix}{self.title} (Priorität: {self.priority}, Status: {self.status}"
        
        if self.project_names:
            projects_str = ", ".join(self.project_names)
            result += f", Projekte: {projects_str}"
        
        result += ")"
        return result