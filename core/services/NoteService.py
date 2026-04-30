from typing import List

from ..db.models.project import Project
from ..db.models.task import Note, Task
from ..db.models.user import User
from .ProjectService import ProjectService


class NoteService:
    """Сервис для заметок проектов и задач."""

    def __init__(self):
        self.note_model = Note
        self.task_model = Task
        self.project_service = ProjectService()
        self.ensure_table()

    def ensure_table(self) -> None:
        """Создать таблицу заметок для существующих локальных БД без миграции."""
        try:
            self.note_model.create_table(safe=True)
        except Exception:
            # В тестах или миграциях таблица может управляться отдельно.
            pass

    def ensure_can_read(self, project: Project, user: User) -> None:
        if not self.project_service.is_member(user, project):
            raise PermissionError("You don't have permission to view notes")

    def ensure_can_create(self, project: Project, user: User) -> None:
        if not self.project_service.is_member(user, project):
            raise PermissionError("You don't have permission to create notes")

    def ensure_can_modify(self, note: Note, user: User) -> None:
        is_author = note.author_id == user.id
        can_manage = self.project_service.can_manage_tasks(user, note.project)
        if not (is_author or can_manage):
            raise PermissionError("You don't have permission to modify this note")

    def get_task_or_raise(self, project: Project, task_id: int) -> Task:
        try:
            return self.task_model.get(
                (self.task_model.project == project) & (self.task_model.id == task_id)
            )
        except self.task_model.DoesNotExist:
            raise ValueError('Task not found in this project')

    def get_note_or_raise(self, project: Project, note_id: int) -> Note:
        try:
            return self.note_model.get(
                (self.note_model.project == project) & (self.note_model.id == note_id)
            )
        except self.note_model.DoesNotExist:
            raise ValueError('Note not found')

    def list_project_notes(self, project: Project, user: User) -> List[Note]:
        self.ensure_can_read(project, user)
        return list(
            self.note_model.select()
            .where(
                (self.note_model.project == project)
                & (self.note_model.scope_type == 'project')
                & (self.note_model.task.is_null(True))
            )
            .order_by(self.note_model.created_at.desc(), self.note_model.id.desc())
        )

    def list_task_notes(self, project: Project, task_id: int, user: User) -> List[Note]:
        self.ensure_can_read(project, user)
        task = self.get_task_or_raise(project, task_id)
        return list(
            self.note_model.select()
            .where(
                (self.note_model.project == project)
                & (self.note_model.task == task)
                & (self.note_model.scope_type == 'task')
            )
            .order_by(self.note_model.created_at.desc(), self.note_model.id.desc())
        )

    def create_project_note(self, project: Project, author: User, content: str) -> Note:
        self.ensure_can_create(project, author)
        return self.note_model.create(
            scope_type='project',
            project=project,
            task=None,
            author=author,
            content=content.strip(),
        )

    def create_task_note(
        self, project: Project, task_id: int, author: User, content: str
    ) -> Note:
        self.ensure_can_create(project, author)
        task = self.get_task_or_raise(project, task_id)
        return self.note_model.create(
            scope_type='task',
            project=project,
            task=task,
            author=author,
            content=content.strip(),
        )

    def update_note(
        self, project: Project, note_id: int, user: User, content: str
    ) -> Note:
        note = self.get_note_or_raise(project, note_id)
        self.ensure_can_modify(note, user)
        note.content = content.strip()
        note.save()
        return note

    def delete_note(self, project: Project, note_id: int, user: User) -> bool:
        note = self.get_note_or_raise(project, note_id)
        self.ensure_can_modify(note, user)
        note.delete_instance()
        return True
