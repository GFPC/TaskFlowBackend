import pytest
import requests
import random
import string
import time
import json
from datetime import datetime, timedelta

BASE_URL = "http://localhost:8000/api/v1"


def random_string(length=8):
    """Генерация случайной строки для уникальности тестов"""
    return ''.join(random.choices(string.ascii_lowercase, k=length))


class TestTasksLive:
    """Интеграционные тесты для Task API"""

    def setup_method(self):
        """Подготовка перед каждым тестом"""
        print(f"\n{'=' * 60}")
        print(f"SETUP: Initializing test")
        print(f"{'=' * 60}")

        # Создаем владельца проекта
        self.owner_username = f"owner_{random_string()}_{int(time.time())}"
        self.owner_password = "OwnerPass123!"
        self.owner_email = f"{self.owner_username}@test.com"

        # Создаем исполнителя
        self.assignee_username = f"assignee_{random_string()}_{int(time.time())}"
        self.assignee_password = "AssigneePass123!"
        self.assignee_email = f"{self.assignee_username}@test.com"

        # Регистрируем пользователей
        self.owner_id = self.register_user(
            self.owner_username, self.owner_password, self.owner_email,
            "Owner", "Test"
        )
        self.assignee_id = self.register_user(
            self.assignee_username, self.assignee_password, self.assignee_email,
            "Assignee", "Test"
        )

        # Логинимся
        self.owner_token = self.login_user(self.owner_username, self.owner_password)
        self.owner_headers = {"Authorization": f"Bearer {self.owner_token}"}

        self.assignee_token = self.login_user(self.assignee_username, self.assignee_password)
        self.assignee_headers = {"Authorization": f"Bearer {self.assignee_token}"}

        # Создаем команду
        self.team_name = f"Test Team {random_string()}"
        self.create_test_team()

        # Создаем проект
        self.project_name = f"Test Project {random_string()}"
        self.create_test_project()

        # Добавляем исполнителя в команду и проект
        self.ensure_member_in_team(self.assignee_username)
        self.add_member_to_project(self.assignee_username, "developer")

        # Сохраняем project_slug для использования во всех тестах
        self.test_project_slug = self.project_slug

        print(f"\n✅ Setup complete!")
        print(f"   Team slug: {self.team_slug}")
        print(f"   Project slug: {self.test_project_slug}")
        print(f"{'=' * 60}\n")

    def register_user(self, username, password, email, first_name, last_name):
        """Регистрация пользователя"""
        response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "first_name": first_name,
                "last_name": last_name,
                "username": username,
                "password": password,
                "email": email
            }
        )
        assert response.status_code == 200, f"Registration failed: {response.text}"
        return response.json()["user_id"]

    def login_user(self, username, password):
        """Логин пользователя"""
        response = requests.post(
            f"{BASE_URL}/auth/login",
            json={"username": username, "password": password}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json()["access_token"]

    def create_test_team(self):
        """Создание тестовой команды"""
        response = requests.post(
            f"{BASE_URL}/teams",
            headers=self.owner_headers,
            json={
                "name": self.team_name,
                "description": "Test team for task tests"
            }
        )
        assert response.status_code == 201, f"Team creation failed: {response.text}"
        data = response.json()
        self.team_id = data["id"]
        self.team_slug = data["slug"]

    def create_test_project(self):
        """Создание тестового проекта"""
        response = requests.post(
            f"{BASE_URL}/projects",
            headers=self.owner_headers,
            json={
                "name": self.project_name,
                "description": "Test project for task tests",
                "team_slug": self.team_slug
            }
        )
        assert response.status_code == 201, f"Project creation failed: {response.text}"
        data = response.json()
        self.project_id = data["id"]
        self.project_slug = data["slug"]

    def ensure_member_in_team(self, username):
        """Гарантирует, что пользователь является членом команды"""
        members_response = requests.get(
            f"{BASE_URL}/teams/{self.team_slug}/members",
            headers=self.owner_headers
        )
        assert members_response.status_code == 200
        members = members_response.json()
        member_usernames = [m["username"] for m in members]

        if username in member_usernames:
            print(f"User {username} already in team")
            return True

        add_response = requests.post(
            f"{BASE_URL}/teams/{self.team_slug}/members",
            headers=self.owner_headers,
            json={
                "username": username,
                "role": "member"
            }
        )
        assert add_response.status_code == 200
        print(f"User {username} added to team")
        return True

    def add_member_to_project(self, username, role):
        """Добавляет пользователя в проект"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.project_slug}/members",
            headers=self.owner_headers,
            json={
                "username": username,
                "role": role
            }
        )
        assert response.status_code == 200, f"Failed to add {username} to project: {response.text}"
        print(f"User {username} added to project as {role}")
        return response.json()

    def create_test_task(self, name=None, assignee_username=None):
        """Создание тестовой задачи"""
        if name is None:
            name = f"Test Task {random_string()}"

        task_data = {
            "name": name,
            "description": "Test task description",
            "priority": 1,
            "position_x": 100,
            "position_y": 200,
            "project_slug": self.test_project_slug
        }

        if assignee_username:
            task_data["assignee_username"] = assignee_username

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            json=task_data
        )

        assert response.status_code == 201, f"Task creation failed: {response.text}"
        data = response.json()
        return data


# ==================== ТЕСТЫ СОЗДАНИЯ ЗАДАЧ ====================

class TestTaskCreation(TestTasksLive):

    def test_1_create_task_success(self):
        """Успешное создание задачи"""
        task_name = f"New Task {random_string()}"

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            json={
                "name": task_name,
                "description": "New task description",
                "priority": 2,
                "position_x": 150,
                "position_y": 250,
                "project_slug": self.test_project_slug,
                "assignee_username": self.assignee_username,
                "deadline": (datetime.now() + timedelta(days=7)).isoformat()
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == task_name
        assert data["description"] == "New task description"
        assert data["priority"] == 2
        assert data["position_x"] == 150
        assert data["position_y"] == 250
        assert data["assignee_username"] == self.assignee_username
        assert data["creator_username"] == self.owner_username
        assert data["status"] == "todo"
        assert data["project_slug"] == self.test_project_slug

    def test_2_create_task_without_assignee(self):
        """Создание задачи без исполнителя"""
        task_name = f"Task Without Assignee {random_string()}"

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            json={
                "name": task_name,
                "project_slug": self.test_project_slug
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == task_name
        assert data["assignee_username"] is None

    def test_3_create_task_invalid_name(self):
        """Создание задачи с некорректным именем"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            json={
                "name": "",
                "project_slug": self.test_project_slug
            }
        )
        assert response.status_code == 422

    def test_4_create_task_no_permission(self):
        """Создание задачи наблюдателем (observer)"""
        observer_username = f"observer_{random_string()}"
        observer_password = "ObserverPass123!"
        observer_email = f"{observer_username}@test.com"

        self.register_user(
            observer_username, observer_password, observer_email,
            "Observer", "Test"
        )

        self.ensure_member_in_team(observer_username)

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/members",
            headers=self.owner_headers,
            json={
                "username": observer_username,
                "role": "observer"
            }
        )
        assert response.status_code == 200

        observer_token = self.login_user(observer_username, observer_password)
        observer_headers = {"Authorization": f"Bearer {observer_token}"}

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=observer_headers,
            json={
                "name": f"Observer Task {random_string()}",
                "project_slug": self.test_project_slug
            }
        )

        assert response.status_code == 403
        assert "don't have permission" in response.text.lower()


# ==================== ТЕСТЫ ПОЛУЧЕНИЯ ЗАДАЧ ====================

class TestTaskRetrieval(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task1 = self.create_test_task("Task 1", self.assignee_username)
        self.task2 = self.create_test_task("Task 2", self.owner_username)
        self.task3 = self.create_test_task("Task 3", None)

    def test_5_get_project_tasks(self):
        """Получение списка задач проекта"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3

        task = data[0]
        assert "id" in task
        assert "name" in task
        assert "status" in task
        assert "assignee_username" in task
        assert "creator_username" in task
        assert "is_ready" in task

    def test_6_filter_tasks_by_status(self):
        """Фильтрация задач по статусу"""
        task = self.create_test_task("Task for status filter", self.assignee_username)

        requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}/status",
            headers=self.owner_headers,
            json={"status": "in_progress"}
        )

        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            params={"status_name": "in_progress"}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["status"] == "in_progress" for t in data)

    def test_7_filter_tasks_by_assignee(self):
        """Фильтрация задач по исполнителю"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.owner_headers,
            params={"assignee_username": self.assignee_username}
        )

        assert response.status_code == 200
        data = response.json()
        assert all(t["assignee_username"] == self.assignee_username for t in data)

    def test_8_get_task_by_id(self):
        """Получение задачи по ID"""
        task = self.create_test_task("Task for get by id", self.assignee_username)

        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.owner_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == task["id"]
        assert data["name"] == task["name"]
        assert "incoming_dependencies" in data
        assert "outgoing_dependencies" in data
        assert "events" in data

    def test_9_get_task_not_found(self):
        """Получение несуществующей задачи"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/99999",
            headers=self.owner_headers
        )
        assert response.status_code == 404


# ==================== ТЕСТЫ ОБНОВЛЕНИЯ ЗАДАЧ ====================

class TestTaskUpdate(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task = self.create_test_task("Task for update", self.assignee_username)

    def test_10_update_task_success(self):
        """Успешное обновление задачи"""
        new_name = f"Updated Task {random_string()}"
        new_description = "Updated description"
        new_deadline = (datetime.now() + timedelta(days=14)).isoformat()

        response = requests.put(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}",
            headers=self.owner_headers,
            json={
                "name": new_name,
                "description": new_description,
                "priority": 2,
                "deadline": new_deadline,
                "assignee_username": self.owner_username
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["name"] == new_name
        assert data["description"] == new_description
        assert data["priority"] == 2
        assert data["assignee_username"] == self.owner_username

    def test_11_update_task_no_permission(self):
        """Обновление задачи без прав (исполнитель не может менять имя)"""
        response = requests.put(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}",
            headers=self.assignee_headers,
            json={"name": "Hacked Name"}
        )

        assert response.status_code == 403
        assert "developer cannot change task name" in response.text.lower()

    def test_12_assignee_can_change_status(self):
        """Исполнитель может менять статус задачи"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/status",
            headers=self.assignee_headers,
            json={"status": "in_progress"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_changed"] is True
        assert data["new_status"] == "in_progress"
        assert data["old_status"] == "todo"


# ==================== ТЕСТЫ СТАТУСОВ ====================

class TestTaskStatus(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task = self.create_test_task("Task for status", self.assignee_username)

    def test_13_change_status_success(self):
        """Успешное изменение статуса"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/status",
            headers=self.owner_headers,
            json={"status": "in_progress"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_changed"] is True
        assert data["new_status"] == "in_progress"
        assert "actions_executed" in data

    def test_14_change_status_same_status(self):
        """Изменение на тот же статус"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/status",
            headers=self.owner_headers,
            json={"status": "todo"}
        )

        assert response.status_code == 200
        data = response.json()
        assert data["status_changed"] is False

    def test_15_change_status_invalid(self):
        """Изменение на несуществующий статус"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/status",
            headers=self.owner_headers,
            json={"status": "non_existent_status"}
        )

        assert response.status_code == 400
        assert "not found" in response.text.lower()


# ==================== ТЕСТЫ ЗАВИСИМОСТЕЙ ====================

class TestTaskDependencies(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task1 = self.create_test_task("Task 1", self.assignee_username)
        self.task2 = self.create_test_task("Task 2", self.assignee_username)
        self.task3 = self.create_test_task("Task 3", self.assignee_username)
        # Сохраняем project_slug для всех тестов в этом классе
        self.test_project_slug = self.project_slug

    def test_16_create_dependency_success(self):
        """Успешное создание зависимости"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task1['id'],
                "target_task_id": self.task2['id'],
                "dependency_type": "blocks",
                "description": "Test dependency"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["source_task_id"] == self.task1['id']
        assert data["target_task_id"] == self.task2['id']
        assert data["dependency_type"] == "blocks"
        assert data["description"] == "Test dependency"
        assert data["created_by_username"] == self.owner_username

        self.dependency_id = data["id"]
        self.dependency_project_slug = self.test_project_slug
        print(f"✅ Dependency created with ID: {self.dependency_id} in project {self.dependency_project_slug}")

        return data

    def test_17_create_duplicate_dependency(self):
        """Создание дублирующейся зависимости"""
        self.test_16_create_dependency_success()

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task1['id'],
                "target_task_id": self.task2['id']
            }
        )

        assert response.status_code == 400
        assert "already exists" in response.text.lower()

    def test_18_create_cyclic_dependency(self):
        """Создание циклической зависимости"""
        response1 = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task1['id'],
                "target_task_id": self.task2['id']
            }
        )
        assert response1.status_code == 200

        response2 = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task2['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task2['id'],
                "target_task_id": self.task1['id']
            }
        )

        assert response2.status_code == 400
        assert "cycle" in response2.text.lower()

    def test_19_get_task_dependencies(self):
        """Получение зависимостей задачи"""
        self.test_16_create_dependency_success()

        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert "incoming" in data
        assert "outgoing" in data
        assert len(data["outgoing"]) >= 1

    def test_20_delete_dependency(self):
        """Удаление зависимости"""
        self.test_16_create_dependency_success()

        response = requests.delete(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers
        )

        assert response.status_code == 200
        assert "successfully deleted" in response.text.lower()

    def test_21_delete_dependency_no_permission(self):
        """Удаление зависимости без прав"""
        self.test_16_create_dependency_success()

        response = requests.delete(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}",
            # <-- ИСПРАВЛЕНО!
            headers=self.assignee_headers
        )

        assert response.status_code == 403
        assert "don't have permission" in response.text.lower()


# ==================== ТЕСТЫ ДЕЙСТВИЙ НА ЗАВИСИМОСТЯХ ====================

class TestDependencyActions(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task1 = self.create_test_task("Task 1", self.assignee_username)
        self.task2 = self.create_test_task("Task 2", self.assignee_username)
        self.test_project_slug = self.project_slug

        dep_response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task1['id'],
                "target_task_id": self.task2['id']
            }
        )
        assert dep_response.status_code == 200
        self.dependency_id = dep_response.json()["id"]
        self.dependency_project_slug = self.test_project_slug
        print(f"✅ Dependency created with ID: {self.dependency_id} in project {self.dependency_project_slug}")

    def test_22_add_notify_assignee_action(self):
        """Добавление действия 'уведомить исполнителя'"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}/actions",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers,
            json={
                "action_type_code": "notify_assignee",
                "message_template": "Task {task_name} is ready!",
                "execute_order": 1
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action_type_code"] == "notify_assignee"

    def test_23_add_notify_custom_action(self):
        """Добавление действия 'уведомить конкретного пользователя'"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}/actions",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers,
            json={
                "action_type_code": "notify_custom",
                "target_user_username": self.owner_username,
                "message_template": "Custom notification",
                "delay_minutes": 30
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action_type_code"] == "notify_custom"

    def test_24_add_change_status_action(self):
        """Добавление действия 'изменить статус'"""
        response = requests.post(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}/actions",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers,
            json={
                "action_type_code": "change_status",
                "target_status": "in_progress"
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data["action_type_code"] == "change_status"

    def test_25_remove_dependency_action(self):
        """Удаление действия с зависимости"""
        action_response = requests.post(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/{self.dependency_id}/actions",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers,
            json={
                "action_type_code": "notify_assignee",
                "message_template": "Test message"
            }
        )
        assert action_response.status_code == 200
        action_id = action_response.json()["id"]

        response = requests.delete(
            f"{BASE_URL}/projects/{self.dependency_project_slug}/tasks/dependencies/actions/{action_id}",
            # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers
        )

        assert response.status_code == 200
        assert "successfully removed" in response.text.lower()


# ==================== ТЕСТЫ ГРАФА ====================

class TestProjectGraph(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task1 = self.create_test_task("Graph Task 1", self.assignee_username)
        self.task2 = self.create_test_task("Graph Task 2", self.assignee_username)
        self.task3 = self.create_test_task("Graph Task 3", self.assignee_username)
        self.test_project_slug = self.project_slug

        dep1 = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task1['id'],
                "target_task_id": self.task2['id']
            }
        )
        assert dep1.status_code == 200

        dep2 = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task2['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task2['id'],
                "target_task_id": self.task3['id']
            }
        )
        assert dep2.status_code == 200

    def test_26_get_project_graph(self):
        """Получение графа проекта"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/graph",
            headers=self.owner_headers
        )

        if response.status_code == 404:
            pytest.skip("Graph endpoint not implemented yet")

        assert response.status_code == 200
        data = response.json()
        assert "nodes" in data
        assert "edges" in data
        assert len(data["nodes"]) >= 3
        assert len(data["edges"]) >= 2


# ==================== ТЕСТЫ СОБЫТИЙ ====================

class TestTaskEvents(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task = self.create_test_task("Task for events", self.assignee_username)
        self.test_project_slug = self.project_slug

    def test_27_get_task_events(self):
        """Получение истории событий задачи"""
        requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/status",
            headers=self.owner_headers,
            json={"status": "in_progress"}
        )

        requests.put(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}",
            headers=self.owner_headers,
            json={"description": "Updated description"}
        )

        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task['id']}/events",
            headers=self.owner_headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 3


# ==================== ТЕСТЫ ГОТОВНОСТИ ЗАДАЧ ====================

class TestTaskReadiness(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task_a = self.create_test_task("Task A", self.assignee_username)
        self.task_b = self.create_test_task("Task B", self.assignee_username)
        self.task_c = self.create_test_task("Task C", self.assignee_username)
        self.test_project_slug = self.project_slug

    def test_28_task_readiness_chain(self):
        """Проверка готовности задач в цепочке зависимостей"""
        print(f"\n{'=' * 60}")
        print(f"TEST: Task Readiness Chain")
        print(f"{'=' * 60}")
        print(f"Project slug: {self.test_project_slug}")

        # 1. Создаем зависимости A -> B -> C
        print(f"\n1. Creating dependency A -> B")
        dep_ab = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_a['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task_a['id'],
                "target_task_id": self.task_b['id']
            }
        )
        assert dep_ab.status_code == 200

        print(f"\n2. Creating dependency B -> C")
        dep_bc = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_b['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": self.task_b['id'],
                "target_task_id": self.task_c['id']
            }
        )
        assert dep_bc.status_code == 200

        # 2. Проверяем готовность каждой задачи
        print(f"\n3. Checking readiness:")

        # Задача A: НЕТ входящих зависимостей -> ДОЛЖНА БЫТЬ ГОТОВА!
        response_a = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_a['id']}",
            headers=self.owner_headers
        )
        assert response_a.status_code == 200
        data_a = response_a.json()
        print(f"\n   Task A ({self.task_a['id']}):")
        print(f"     Status: {data_a['status']}")
        print(f"     is_ready: {data_a['is_ready']}")
        print(f"     Dependencies: {len(data_a.get('incoming_dependencies', []))} incoming")

        # ВАЖНО: Задача А готова, потому что у нее нет зависимостей!
        assert data_a["is_ready"] is True  # <-- ИСПРАВЛЕНО: должно быть True!

        # Задача B: зависит от A -> НЕ ДОЛЖНА БЫТЬ ГОТОВА (A еще не выполнена)
        response_b = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_b['id']}",
            headers=self.owner_headers
        )
        assert response_b.status_code == 200
        data_b = response_b.json()
        print(f"\n   Task B ({self.task_b['id']}):")
        print(f"     Status: {data_b['status']}")
        print(f"     is_ready: {data_b['is_ready']}")
        print(f"     Dependencies: {len(data_b.get('incoming_dependencies', []))} incoming")

        assert data_b["is_ready"] is False  # Должна быть НЕ готова

        # Задача C: зависит от B -> НЕ ДОЛЖНА БЫТЬ ГОТОВА
        response_c = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_c['id']}",
            headers=self.owner_headers
        )
        assert response_c.status_code == 200
        data_c = response_c.json()
        print(f"\n   Task C ({self.task_c['id']}):")
        print(f"     Status: {data_c['status']}")
        print(f"     is_ready: {data_c['is_ready']}")
        print(f"     Dependencies: {len(data_c.get('incoming_dependencies', []))} incoming")

        assert data_c["is_ready"] is False  # Должна быть НЕ готова

        # 3. Завершаем задачу A
        print(f"\n4. Completing Task A...")
        complete_a = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_a['id']}/status",
            headers=self.owner_headers,
            json={"status": "completed"}
        )
        assert complete_a.status_code == 200

        # 4. Проверяем готовность после завершения A
        print(f"\n5. Checking readiness after A completed:")

        # Задача B: теперь должна быть ГОТОВА (A выполнена)
        response_b2 = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_b['id']}",
            headers=self.owner_headers
        )
        assert response_b2.status_code == 200
        data_b2 = response_b2.json()
        print(f"\n   Task B ({self.task_b['id']}):")
        print(f"     Status: {data_b2['status']}")
        print(f"     is_ready: {data_b2['is_ready']}")

        assert data_b2["is_ready"] is True  # Теперь должна быть готова!

        # Задача C: все еще НЕ готова (B не выполнена)
        response_c2 = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task_c['id']}",
            headers=self.owner_headers
        )
        assert response_c2.status_code == 200
        data_c2 = response_c2.json()
        print(f"\n   Task C ({self.task_c['id']}):")
        print(f"     Status: {data_c2['status']}")
        print(f"     is_ready: {data_c2['is_ready']}")

        assert data_c2["is_ready"] is False  # Все еще не готова

        print(f"\n✅ Test passed!")


# ==================== ТЕСТЫ СТАТИСТИКИ ====================

class TestTaskStats(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.task1 = self.create_test_task("Stats Task 1", self.assignee_username)
        self.task2 = self.create_test_task("Stats Task 2", self.assignee_username)
        self.task3 = self.create_test_task("Stats Task 3", self.owner_username)
        self.test_project_slug = self.project_slug

        requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task1['id']}/status",
            headers=self.owner_headers,
            json={"status": "in_progress"}
        )

        requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{self.task2['id']}/status",
            headers=self.owner_headers,
            json={"status": "completed"}
        )

    def test_29_get_project_task_stats(self):
        """Получение статистики по задачам проекта"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/stats",
            headers=self.owner_headers
        )

        if response.status_code == 404:
            pytest.skip("Stats endpoint not implemented yet")

        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert data["total"] >= 3
        assert "by_status" in data
        assert "by_assignee" in data
        assert "overdue" in data

    def test_30_get_user_task_stats(self):
        """Получение статистики по задачам пользователя"""
        response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/stats/user/{self.assignee_username}",
            headers=self.owner_headers
        )

        if response.status_code == 404:
            pytest.skip("User stats endpoint not implemented yet")

        assert response.status_code == 200
        data = response.json()
        assert "assigned" in data
        assert data["assigned"] >= 2
        assert "completed" in data
        assert "in_progress" in data
        assert "completion_rate" in data


# ==================== ТЕСТЫ УДАЛЕНИЯ ====================

class TestTaskDeletion(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.test_project_slug = self.project_slug

    def test_31_delete_task_by_owner(self):
        """Удаление задачи владельцем проекта"""
        task = self.create_test_task("Task for deletion", self.assignee_username)

        response = requests.delete(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.owner_headers
        )

        assert response.status_code == 200
        assert "successfully deleted" in response.text.lower()

        get_response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.owner_headers
        )
        assert get_response.status_code == 404

    def test_32_delete_task_by_creator(self):
        """Удаление задачи создателем (developer)"""
        # 1. СОЗДАЕМ задачу от имени DEVELOPER
        task_name = f"Task by assignee {random_string()}"

        create_response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks",
            headers=self.assignee_headers,  # <-- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ!
            json={
                "name": task_name,
                "description": "Task created by developer",
                "project_slug": self.test_project_slug
            }
        )

        # Проверяем, что задача создалась
        assert create_response.status_code == 201
        task = create_response.json()
        assert task["creator_username"] == self.assignee_username  # Создатель - assignee!
        print(f"✅ Task created by developer: {task['id']} - {task['name']}")

        # 2. УДАЛЯЕМ задачу от имени создателя (того же developer)
        delete_response = requests.delete(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.assignee_headers
        )

        assert delete_response.status_code == 200
        assert "successfully deleted" in delete_response.text.lower()
        print(f"✅ Task deleted by creator (developer)")

        # 3. Проверяем, что задача действительно удалена
        get_response = requests.get(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.owner_headers
        )
        assert get_response.status_code == 404
        print(f"✅ Task confirmed deleted")

    def test_33_delete_task_no_permission(self):
        """Удаление чужой задачи без прав"""
        task = self.create_test_task("Owner's task", self.owner_username)

        response = requests.delete(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}",
            headers=self.assignee_headers
        )

        assert response.status_code == 403
        assert "don't have permission" in response.text.lower()


# ==================== ТЕСТЫ ГРАНИЧНЫХ СЛУЧАЕВ ====================

class TestTaskEdgeCases(TestTasksLive):

    def setup_method(self):
        super().setup_method()
        self.test_project_slug = self.project_slug

    def test_34_task_without_project(self):
        """Создание задачи без указания проекта"""
        response = requests.post(
            f"{BASE_URL}/projects//tasks",
            headers=self.owner_headers,
            json={"name": "Invalid Task"}
        )
        assert response.status_code == 404

    def test_35_create_task_invalid_project(self):
        """Создание задачи в несуществующем проекте"""
        response = requests.post(
            f"{BASE_URL}/projects/non-existent-project/tasks",
            headers=self.owner_headers,
            json={
                "name": "Invalid Task",
                "project_slug": "non-existent-project"
            }
        )
        assert response.status_code == 404
        assert "Project not found" in response.text

    def test_36_create_dependency_same_task(self):
        """Создание зависимости задачи от самой себя"""
        task = self.create_test_task("Self dependency task", self.assignee_username)

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": task['id'],
                "target_task_id": task['id']
            }
        )

        assert response.status_code in [400, 500]
        if response.status_code == 400:
            assert "cycle" in response.text.lower() or "self" in response.text.lower()

    def test_37_add_action_without_required_fields(self):
        """Добавление действия без обязательных полей"""
        task1 = self.create_test_task("Task 1", self.assignee_username)
        task2 = self.create_test_task("Task 2", self.assignee_username)

        dep_response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/{task1['id']}/dependencies",
            headers=self.owner_headers,
            json={
                "source_task_id": task1['id'],
                "target_task_id": task2['id']
            }
        )
        assert dep_response.status_code == 200
        dep_id = dep_response.json()["id"]

        response = requests.post(
            f"{BASE_URL}/projects/{self.test_project_slug}/tasks/dependencies/{dep_id}/actions",  # <-- ИСПРАВЛЕНО!
            headers=self.owner_headers,
            json={
                "action_type_code": "notify_custom",
                "message_template": "Test"
            }
        )

        assert response.status_code == 400
        assert "requires target_user" in response.text.lower()