from peewee import SqliteDatabase
import pytest

from core.db.models.user import AuthLog, AuthSession, RecoveryCode, User, UserRole
from core.services.UserService import UserService


@pytest.fixture
def user_db():
    db = SqliteDatabase(':memory:')
    models = [UserRole, User, AuthSession, RecoveryCode, AuthLog]
    db.bind(models, bind_refs=False, bind_backrefs=False)
    db.connect()
    db.create_tables(models)
    yield db
    db.drop_tables(models)
    db.close()


@pytest.fixture
def user_service(user_db):
    return UserService()


def test_email_registration_verify_and_login(user_service):
    registered = user_service.register(
        first_name='Григорий',
        last_name='Федулов',
        username='greg',
        password='Password123!',
        email='greg@test.local',
    )

    user = registered['user']
    assert registered['requires_verification'] is True
    assert registered['verification_code']
    assert user.email == 'greg@test.local'
    assert user.email_verified is False

    unverified_login = user_service.login('greg', 'Password123!')
    assert unverified_login['requires_verification'] is True
    assert unverified_login['verification_code']

    verified = user_service.verify_email_code(
        user_id=user.id, code=unverified_login['verification_code']
    )
    assert verified['success'] is True
    assert verified['access_token']

    login = user_service.login(
        username='greg',
        password='Password123!',
        ip='127.0.0.1',
        user_agent='pytest',
        device_id='web',
    )
    assert login['requires_verification'] is False
    assert login['session'] is not None
    assert login['access_token']
    assert AuthLog.select().where(AuthLog.action == 'login').count() >= 1


def test_email_registration_validation(user_service):
    with pytest.raises(ValueError, match='Email is required'):
        user_service.register(
            first_name='No',
            last_name='Email',
            username='noemail',
            password='Password123!',
            email='',
        )

    with pytest.raises(ValueError, match='Invalid password'):
        user_service.register(
            first_name='Weak',
            last_name='Password',
            username='weakpass',
            password='weak',
            email='weak@test.local',
        )

    user_service.register(
        first_name='First',
        last_name='User',
        username='first',
        password='Password123!',
        email='first@test.local',
    )

    with pytest.raises(ValueError, match='Username already taken'):
        user_service.register(
            first_name='Duplicate',
            last_name='User',
            username='first',
            password='Password123!',
            email='other@test.local',
        )

    with pytest.raises(ValueError, match='Email already registered'):
        user_service.register(
            first_name='Duplicate',
            last_name='Email',
            username='other',
            password='Password123!',
            email='first@test.local',
        )
