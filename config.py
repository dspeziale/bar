import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()

# Neon (e Heroku) usano "postgres://" ma SQLAlchemy richiede "postgresql://"
_db_url = os.environ.get('DATABASE_URL', 'sqlite:///bar.db')
if _db_url.startswith('postgres://'):
    _db_url = _db_url.replace('postgres://', 'postgresql://', 1)

_is_postgres = _db_url.startswith('postgresql')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'cambiamiinproduzione-32caratteri!')
    SQLALCHEMY_DATABASE_URI = _db_url
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)

    # Pool ottimizzato per serverless (Vercel) con PostgreSQL
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_pre_ping': True,
        **({'pool_size': 1, 'max_overflow': 0} if _is_postgres else {}),
    }

    # Fedeltà
    LOYALTY_POINTS_PER_EURO = 10
    LOYALTY_REWARD_POINTS   = 100
    LOYALTY_REWARD_AMOUNT   = 1.0

    # Builder prezzi base
    BUILDER_PRICES = {
        'panino':   3.50,
        'insalata': 3.00,
    }

    # Slot di ritiro
    PICKUP_SLOTS = [
        "11:45", "12:00", "12:15", "12:30",
        "12:45", "13:00", "13:15", "13:30"
    ]

    # Google OAuth2
    GOOGLE_CLIENT_ID     = os.environ.get('GOOGLE_CLIENT_ID', '')
    GOOGLE_CLIENT_SECRET = os.environ.get('GOOGLE_CLIENT_SECRET', '')
    # In produzione (HTTPS) non impostare questa variabile → default 0
    AUTHLIB_INSECURE_TRANSPORT = os.environ.get('AUTHLIB_INSECURE_TRANSPORT', '0')
