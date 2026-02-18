# core/db/base.py
from peewee import Model
from ..config import database

class BaseModel(Model):
    """Базовая модель для всех моделей БД"""
    class Meta:
        database = database