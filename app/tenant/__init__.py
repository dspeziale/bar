from flask import Blueprint

bp = Blueprint('tenant', __name__)

from app.tenant import routes  # noqa: F401, E402
