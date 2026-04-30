from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator


class NoteCreate(BaseModel):
    """Создание заметки"""

    content: str = Field(..., min_length=1)


class NoteUpdate(BaseModel):
    """Обновление заметки"""

    content: str = Field(..., min_length=1)


class NoteResponse(BaseModel):
    """Ответ с заметкой"""

    id: int
    scope_type: str
    project_id: int
    task_id: Optional[int] = None
    author_username: str
    author_name: str
    content: str
    created_at: datetime
    updated_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)

    @model_validator(mode='before')
    @classmethod
    def validate_note(cls, data):
        """Преобразует объект Note в контракт API."""
        if hasattr(data, '__dict__'):
            author = data.author
            author_name = f'{author.first_name} {author.last_name}'.strip()
            return {
                'id': data.id,
                'scope_type': data.scope_type,
                'project_id': data.project_id,
                'task_id': data.task_id,
                'author_username': author.username,
                'author_name': author_name,
                'content': data.content,
                'created_at': data.created_at,
                'updated_at': data.updated_at,
            }
        return data
