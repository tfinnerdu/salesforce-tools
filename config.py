import os
from dotenv import load_dotenv

load_dotenv()


def get_org_config(org: str = 'dev') -> dict:
    """Return SF credential dict for the given org name."""
    prefix = f"SF_{org.upper()}_"
    return {
        'username': os.environ.get(f'{prefix}USERNAME', ''),
        'password': os.environ.get(f'{prefix}PASSWORD', ''),
        'security_token': os.environ.get(f'{prefix}TOKEN', ''),
        'domain': os.environ.get(f'{prefix}DOMAIN', 'login'),
    }


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-change-in-prod')
    DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/sf_mission_control')
    CONDUCTOR_URL = os.environ.get('CONDUCTOR_URL', 'http://conductor:8080')
    CONDUCTOR_API_KEY = os.environ.get('CONDUCTOR_API_KEY', '')
    CONDUCTOR_MOCK = os.environ.get('CONDUCTOR_MOCK', 'true').lower() == 'true'
    SF_MOCK = os.environ.get('SF_MOCK', 'true').lower() == 'true'
    DEFAULT_ORG = os.environ.get('DEFAULT_ORG', 'dev')
    SCHEDULER_ENABLED = os.environ.get('SCHEDULER_ENABLED', 'false').lower() == 'true'
    SQLSERVER_CONN = os.environ.get('SQLSERVER_CONN', '')
    PORT = int(os.environ.get('PORT', 5000))
    VERSION = '1.0.0'
