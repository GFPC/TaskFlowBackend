# run_test.py
import sys
import os
import pytest

if __name__ == '__main__':
    # Добавляем текущую директорию в PYTHONPATH
    sys.path.insert(0, os.path.dirname(__file__))
    os.environ['TESTING'] = '1'

    # Запускаем тест
    sys.exit(pytest.main(['tests/test_api/test_auth.py', '-v']))