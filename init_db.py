# init_db.py
import json
import os

from core.config import database
from core.db.models.project import (
    Project,
    ProjectInvitation,
    ProjectMember,
    ProjectRole,
)
from core.db.models.task import (
    DependencyAction,
    DependencyActionType,
    Note,
    ScheduledAction,
    Task,
    TaskDependency,
    TaskEvent,
    TaskStatus,
)
from core.db.models.team import Team, TeamInvitation, TeamMember, TeamMemberRole
from core.db.models.user import AuthLog, AuthSession, RecoveryCode, User, UserRole


def create_tables():
    """Создание всех таблиц в базе данных в правильном порядке"""
    print('=' * 60)
    print('Creating database tables...')
    print('=' * 60)

    # Порядок важен из-за внешних ключей!
    all_models = [
        # 1. Справочники и независимые таблицы
        UserRole,
        TeamMemberRole,
        ProjectRole,
        TaskStatus,
        DependencyActionType,
        # 2. Основные сущности
        User,
        Team,
        Project,
        # 3. Связи многие-ко-многим и зависимые таблицы
        AuthSession,
        RecoveryCode,
        AuthLog,
        TeamMember,
        TeamInvitation,
        ProjectMember,
        ProjectInvitation,
        Task,
        TaskDependency,
        DependencyAction,
        TaskEvent,
        Note,
        ScheduledAction,
    ]

    try:
        database.create_tables(all_models)
        print('All tables created successfully!')
    except Exception as e:
        print(f'Error creating tables: {e}')
        raise


def drop_tables():
    """Удаление всех таблиц (для чистой инициализации)"""
    print('=' * 60)
    print('Dropping all tables...')
    print('=' * 60)

    all_models = [
        ScheduledAction,
        Note,
        TaskEvent,
        DependencyAction,
        TaskDependency,
        Task,
        ProjectInvitation,
        ProjectMember,
        TeamInvitation,
        TeamMember,
        AuthSession,
        RecoveryCode,
        AuthLog,
        Project,
        Team,
        User,
        TaskStatus,
        DependencyActionType,
        ProjectRole,
        TeamMemberRole,
        UserRole,
    ]

    try:
        database.drop_tables(all_models)
        print('All tables dropped successfully!')
    except Exception as e:
        print(f'Error dropping tables: {e}')
        raise


# ------------------- USER ROLES -------------------


def create_user_roles():
    """Создание начальных глобальных ролей пользователей"""
    print('\n' + '=' * 60)
    print('Creating initial user roles...')
    print('=' * 60)

    roles = [
        {
            'name': 'Работник',
            'description': 'Стандартный пользователь системы',
            'priority': 1,
            'permissions': json.dumps(
                {
                    'view_tasks': True,
                    'view_own_tasks': True,
                    'update_own_tasks': True,
                    'add_comments': True,
                }
            ),
        },
        {
            'name': 'Менеджер проекта',
            'description': 'Управляет задачами и участниками проектов',
            'priority': 50,
            'permissions': json.dumps(
                {
                    'view_tasks': True,
                    'edit_all_tasks': True,
                    'manage_team': True,
                    'create_projects': True,
                }
            ),
        },
        {
            'name': 'Хозяин',
            'description': 'Полный доступ к системе',
            'priority': 100,
            'permissions': json.dumps({'all': True}),
        },
        {
            'name': 'Тестировщик',
            'description': 'Доступ к тестовым функциям',
            'priority': 25,
            'permissions': json.dumps({'view_tasks': True, 'test_features': True}),
        },
    ]

    created_count = 0
    for role_data in roles:
        role, created = UserRole.get_or_create(
            name=role_data['name'], defaults=role_data
        )
        if created:
            print(f'  Created user role: {role.name}')
            created_count += 1
        else:
            print(f'  User role already exists: {role.name}')

    print(f'\nTotal user roles created: {created_count}')
    return created_count


# ------------------- TEAM ROLES -------------------


def create_team_roles():
    """Создание начальных ролей в командах"""
    print('\n' + '=' * 60)
    print('Creating initial team member roles...')
    print('=' * 60)

    roles = [
        {
            'name': 'owner',
            'description': 'Владелец команды - полный доступ',
            'priority': 100,
            'can_manage_team': True,
            'can_manage_projects': True,
            'can_invite_members': True,
            'can_remove_members': True,
        },
        {
            'name': 'admin',
            'description': 'Администратор команды - управление проектами и участниками',
            'priority': 80,
            'can_manage_team': False,
            'can_manage_projects': True,
            'can_invite_members': True,
            'can_remove_members': True,
        },
        {
            'name': 'member',
            'description': 'Участник команды - только работа в проектах',
            'priority': 50,
            'can_manage_team': False,
            'can_manage_projects': False,
            'can_invite_members': False,
            'can_remove_members': False,
        },
    ]

    created_count = 0
    for role_data in roles:
        role, created = TeamMemberRole.get_or_create(
            name=role_data['name'], defaults=role_data
        )
        if created:
            print(f'  Created team role: {role.name}')
            created_count += 1
        else:
            print(f'  Team role already exists: {role.name}')

    print(f'\nTotal team roles created: {created_count}')
    return created_count


# ------------------- PROJECT ROLES -------------------


def create_project_roles():
    """Создание начальных ролей в проектах"""
    print('\n' + '=' * 60)
    print('Creating initial project roles...')
    print('=' * 60)

    roles = [
        {
            'name': 'owner',
            'description': 'Владелец проекта - полный доступ',
            'priority': 100,
            'can_create_tasks': True,
            'can_edit_any_task': True,
            'can_delete_any_task': True,
            'can_edit_own_task': True,
            'can_delete_own_task': True,
            'can_create_dependencies': True,
            'can_delete_dependencies': True,
            'can_manage_members': True,
            'can_edit_project': True,
            'can_delete_project': True,
        },
        {
            'name': 'manager',
            'description': 'Менеджер проекта - управление задачами и участниками',
            'priority': 80,
            'can_create_tasks': True,
            'can_edit_any_task': True,
            'can_delete_any_task': True,
            'can_edit_own_task': True,
            'can_delete_own_task': True,
            'can_create_dependencies': True,
            'can_delete_dependencies': True,
            'can_manage_members': True,
            'can_edit_project': True,
            'can_delete_project': False,
        },
        {
            'name': 'developer',
            'description': 'Разработчик - просмотр и смена статусов задач',
            'priority': 60,
            'can_create_tasks': False,
            'can_edit_any_task': False,
            'can_delete_any_task': False,
            'can_edit_own_task': False,
            'can_delete_own_task': False,
            'can_create_dependencies': False,
            'can_delete_dependencies': False,
            'can_manage_members': False,
            'can_edit_project': False,
            'can_delete_project': False,
        },
        {
            'name': 'observer',
            'description': 'Наблюдатель - только просмотр',
            'priority': 40,
            'can_create_tasks': False,
            'can_edit_any_task': False,
            'can_delete_any_task': False,
            'can_edit_own_task': False,
            'can_delete_own_task': False,
            'can_create_dependencies': False,
            'can_delete_dependencies': False,
            'can_manage_members': False,
            'can_edit_project': False,
            'can_delete_project': False,
        },
    ]

    created_count = 0
    for role_data in roles:
        role, created = ProjectRole.get_or_create(
            name=role_data['name'], defaults=role_data
        )
        if created:
            print(f'  Created project role: {role.name}')
            created_count += 1
        else:
            print(f'  Project role already exists: {role.name}')

    print(f'\nTotal project roles created: {created_count}')
    return created_count


# ------------------- TASK STATUSES -------------------


def create_task_statuses():
    """Создание начальных статусов задач"""
    print('\n' + '=' * 60)
    print('Creating initial task statuses...')
    print('=' * 60)

    statuses = [
        {
            'name': 'todo',
            'display_name': 'К выполнению',
            'color': '#757575',
            'order': 10,
            'is_final': False,
            'is_blocking': False,
        },
        {
            'name': 'in_progress',
            'display_name': 'В работе',
            'color': '#1976d2',
            'order': 20,
            'is_final': False,
            'is_blocking': False,
        },
        {
            'name': 'review',
            'display_name': 'На проверке',
            'color': '#ed6c02',
            'order': 30,
            'is_final': False,
            'is_blocking': False,
        },
        {
            'name': 'completed',
            'display_name': 'Выполнена',
            'color': '#2e7d32',
            'order': 40,
            'is_final': True,
            'is_blocking': False,
        },
        {
            'name': 'blocked',
            'display_name': 'Заблокирована',
            'color': '#d32f2f',
            'order': 5,
            'is_final': False,
            'is_blocking': True,
        },
    ]

    created_count = 0
    for status_data in statuses:
        status, created = TaskStatus.get_or_create(
            name=status_data['name'], defaults=status_data
        )
        if created:
            print(f'  Created task status: {status.display_name}')
            created_count += 1
        else:
            print(f'  Task status already exists: {status.display_name}')

    print(f'\nTotal task statuses created: {created_count}')
    return created_count


# ------------------- DEPENDENCY ACTION TYPES -------------------


def create_dependency_action_types():
    """Создание начальных типов действий на ребрах графа"""
    print('\n' + '=' * 60)
    print('Creating initial dependency action types...')
    print('=' * 60)

    action_types = [
        {
            'name': 'Уведомить исполнителя целевой задачи',
            'code': 'notify_assignee',
            'description': 'Отправить уведомление в Telegram исполнителю задачи',
            'requires_target_user': False,
            'requires_template': True,
            'supports_delay': False,
        },
        {
            'name': 'Уведомить создателя исходной задачи',
            'code': 'notify_creator',
            'description': 'Отправить уведомление в Telegram создателю задачи',
            'requires_target_user': False,
            'requires_template': True,
            'supports_delay': False,
        },
        {
            'name': 'Уведомить конкретного пользователя',
            'code': 'notify_custom',
            'description': 'Отправить уведомление конкретному пользователю',
            'requires_target_user': True,
            'requires_template': True,
            'supports_delay': True,
        },
        {
            'name': 'Изменить статус задачи',
            'code': 'change_status',
            'description': 'Автоматически изменить статус целевой задачи',
            'requires_target_user': False,
            'requires_template': False,
            'supports_delay': True,
        },
        {
            'name': 'Создать подзадачу',
            'code': 'create_subtask',
            'description': 'Создать подзадачу в целевой задаче',
            'requires_target_user': True,
            'requires_template': False,
            'supports_delay': False,
        },
    ]

    created_count = 0
    for type_data in action_types:
        action_type, created = DependencyActionType.get_or_create(
            code=type_data['code'], defaults=type_data
        )
        if created:
            print(f'  Created action type: {action_type.name}')
            created_count += 1
        else:
            print(f'  Action type already exists: {action_type.name}')

    print(f'\nTotal action types created: {created_count}')
    return created_count


# ------------------- INITIAL ADMIN USER -------------------


def create_initial_admin():
    """Создание начального администратора (опционально)"""
    print('\n' + '=' * 60)
    print('Creating initial admin user...')
    print('=' * 60)

    from datetime import datetime

    import bcrypt

    admin_username = os.getenv('INITIAL_ADMIN_USERNAME', 'admin')
    admin_password = os.getenv('INITIAL_ADMIN_PASSWORD', 'Admin123!')
    admin_email = os.getenv('INITIAL_ADMIN_EMAIL', 'admin@taskflow.local')

    try:
        # Получаем роль 'Хозяин'
        owner_role = UserRole.get(UserRole.name == 'Хозяин')

        # Проверяем, существует ли уже админ
        existing = (
            User.select()
            .where((User.username == admin_username) | (User.email == admin_email))
            .first()
        )

        if existing:
            print(f'  Admin user already exists: {admin_username}')
            return False

        # Создаем администратора
        salt = bcrypt.gensalt()
        password_hash = bcrypt.hashpw(admin_password.encode('utf-8'), salt).decode(
            'utf-8'
        )

        admin = User.create(
            first_name='System',
            last_name='Administrator',
            username=admin_username,
            password_hash=password_hash,
            email=admin_email,
            role=owner_role,
            is_active=True,
            is_superuser=True,
            email_verified=True,
            theme_preferences=json.dumps(
                {'mode': 'dark', 'primary_color': '#1976d2', 'language': 'ru'}
            ),
            notification_settings=json.dumps(
                {
                    'email': True,
                    'task_assigned': True,
                    'task_completed': True,
                    'dependency_ready': True,
                }
            ),
        )

        print(f'  Created admin user: {admin.username}')
        print(f'     Email: {admin.email}')
        print(f'     Password: {admin_password} (change on first login!)')
        return True

    except UserRole.DoesNotExist:
        print("User role 'Хозяин' not found. Create roles first!")
        return False
    except Exception as e:
        print(f'  Error creating admin user: {e}')
        return False


# ------------------- MAIN -------------------


def init_database(clean=False):
    """
    Полная инициализация базы данных

    Args:
        clean: Если True - сначала удаляет все таблицы
    """
    print('\n' + '*' * 30)
    print('TASKFLOW DATABASE INITIALIZATION')
    print('*' * 30 + '\n')

    # Подключаемся к базе
    try:
        database.connect()
        print('Connected to database')
    except Exception as e:
        print(f'Failed to connect to database: {e}')
        return

    # Опционально: чистая инициализация
    if clean:
        drop_tables()

    # Создаем таблицы
    create_tables()

    # Создаем все справочники
    print('\n' + '*' * 30)
    print('CREATING REFERENCE DATA')
    print('*' * 30)

    create_user_roles()
    create_team_roles()
    create_project_roles()
    create_task_statuses()
    create_dependency_action_types()

    # Опционально: создаем админа
    print('\n' + '*' * 30)
    print('ADMIN USER CREATION')
    print('*' * 30)
    create_initial_admin()

    # Закрываем соединение
    database.close()

    print('\n' + '*' * 30)
    print('DATABASE INITIALIZATION COMPLETE!')
    print('*' * 30 + '\n')

    print('Summary:')
    print('  - Users: User, UserRole, AuthSession, RecoveryCode, AuthLog')
    print('  - Teams: Team, TeamMember, TeamMemberRole, TeamInvitation')
    print('  - Projects: Project, ProjectMember, ProjectRole, ProjectInvitation')
    print(
        '  - Tasks: Task, TaskStatus, TaskDependency, DependencyAction, DependencyActionType, TaskEvent, ScheduledAction'
    )
    print('\nAll done!')


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(description='TaskFlow Database Initialization')
    parser.add_argument(
        '--clean', action='store_true', help='Drop all tables before creation'
    )

    args = parser.parse_args()

    # Запускаем инициализацию
    init_database(clean=args.clean)
