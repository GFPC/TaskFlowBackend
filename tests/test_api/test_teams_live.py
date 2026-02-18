# tests/test_api/test_teams_live.py - последние правки

import pytest
import requests
import random
import string
import time
import json

BASE_URL = "http://localhost:8000/api/v1"


def random_string(length=8):
    return ''.join(random.choices(string.ascii_lowercase, k=length))


class TestTeamsLive:
    """Интеграционные тесты для Team API"""

    def setup_method(self):
        """Подготовка перед каждым тестом"""
        # Создаем уникального пользователя для этого теста
        self.username = f"testuser_{random_string()}_{int(time.time())}"
        self.password = "TestPass123!"
        self.email = f"{self.username}@test.com"

        # Регистрируем пользователя
        reg_response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "first_name": "Test",
                "last_name": "User",
                "username": self.username,
                "password": self.password,
                "email": self.email
            }
        )
        assert reg_response.status_code == 200, f"Registration failed: {reg_response.text}"
        self.user_id = reg_response.json()["user_id"]

        time.sleep(0.1)

        # Логинимся
        login_response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "username": self.username,
                "password": self.password
            }
        )

        assert login_response.status_code == 200, f"Login failed: {login_response.text}"

        data = login_response.json()
        self.access_token = data["access_token"]
        self.headers = {"Authorization": f"Bearer {self.access_token}"}

        # Создаем тестовую команду
        self.team_name = f"Test Team {random_string()}"
        self.create_test_team()

    def create_test_team(self):
        """Создание тестовой команды"""
        response = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={
                "name": self.team_name,
                "description": "Test team for integration tests"
            }
        )

        # Добавим детальный вывод ошибки
        if response.status_code != 201:
            print(f"\nTeam creation failed:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            print(f"URL: {BASE_URL}/teams")
            print(f"Headers: {self.headers}")
            print(f"Payload: {self.team_name}")

        assert response.status_code == 201, f"Team creation failed: {response.text}"
        data = response.json()
        self.team_id = data["id"]
        self.team_slug = data["slug"]

    def test_1_create_team_success(self):
        """Успешное создание команды"""
        team_name = f"New Team {random_string()}"

        response = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={
                "name": team_name,
                "description": "New team description"
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data["name"] == team_name
        assert data["description"] == "New team description"
        assert data["slug"] == team_name.lower().replace(" ", "-")
        assert data["members_count"] == 1
        assert data["owner_id"] == self.user_id

    def test_2_create_team_invalid_name(self):
        """Создание команды с некорректным именем"""
        # Слишком короткое имя - Pydantic возвращает 422
        response = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={"name": "A"}
        )
        assert response.status_code == 422

        # Слишком длинное имя - 422
        response = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={"name": "A" * 101}
        )
        assert response.status_code == 422

    def test_3_create_team_unauthorized(self):
        """Создание команды без авторизации"""
        response = requests.post(
            f"{BASE_URL}/teams",
            json={"name": "Test Team"}
        )
        assert response.status_code == 401

    def test_4_create_team_duplicate_name(self):
        """Создание команды с дублирующимся именем"""
        team_name = f"Unique Name {random_string()}"

        # Первое создание
        response1 = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={"name": team_name}
        )
        assert response1.status_code == 201
        slug1 = response1.json()["slug"]

        # Второе создание с тем же именем
        response2 = requests.post(
            f"{BASE_URL}/teams",
            headers=self.headers,
            json={"name": team_name}
        )
        assert response2.status_code == 201
        slug2 = response2.json()["slug"]

        assert slug1 != slug2
        assert slug2 == f"{slug1}-1"

    def test_5_get_my_teams(self):
        """Получение списка своих команд"""
        response = requests.get(
            f"{BASE_URL}/teams",
            headers=self.headers
        )

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        assert any(team["slug"] == self.team_slug for team in data)

    def test_6_get_team_by_slug_success(self):
        """Успешное получение команды по slug"""
        response = requests.get(
            f"{BASE_URL}/teams/{self.team_slug}",
            headers=self.headers
        )

        if response.status_code != 200:
            print(f"\nError getting team:")
            print(f"Status: {response.status_code}")
            print(f"Response: {response.text}")
            print(f"Team slug: {self.team_slug}")

        assert response.status_code == 200
        data = response.json()
        assert data["id"] == self.team_id
        assert data["slug"] == self.team_slug
        assert data["name"] == self.team_name
        assert "members" in data
        assert len(data["members"]) >= 1
        assert data["members"][0]["username"] == self.username

    def test_7_get_team_by_slug_not_found(self):
        """Получение несуществующей команды"""
        response = requests.get(
            f"{BASE_URL}/teams/non-existent-team-12345",
            headers=self.headers
        )
        assert response.status_code == 404

    def test_8_get_team_by_slug_not_member(self):
        """Получение команды, в которой пользователь не состоит"""
        # Создаем другого пользователя
        other_username = f"other_{random_string()}_{int(time.time())}"
        other_password = "OtherPass123!"
        other_email = f"{other_username}@test.com"

        # Регистрируем
        reg_response = requests.post(
            f"{BASE_URL}/auth/register",
            json={
                "first_name": "Other",
                "last_name": "User",
                "username": other_username,
                "password": other_password,
                "email": other_email
            }
        )
        assert reg_response.status_code == 200

        time.sleep(0.1)

        # Логинимся
        login_response = requests.post(
            f"{BASE_URL}/auth/login",
            json={
                "username": other_username,
                "password": other_password
            }
        )
        assert login_response.status_code == 200

        other_token = login_response.json()["access_token"]
        other_headers = {"Authorization": f"Bearer {other_token}"}

        # Пытаемся получить команду
        response = requests.get(
            f"{BASE_URL}/teams/{self.team_slug}",
            headers=other_headers
        )
        assert response.status_code == 403