# setup.py
from setuptools import find_packages, setup

setup(
    name='taskflow',
    version='0.1.0',
    packages=find_packages(),
    install_requires=[
        'fastapi',
        'peewee',
        'bcrypt',
        'python-dotenv',
        'pytest',
        'requests',
    ],
)
