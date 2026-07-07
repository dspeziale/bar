import sys
import os

# Aggiunge la root del progetto al path così "from app import ..." funziona
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix

# Vercel cerca una variabile "app" di tipo WSGI callable
app = create_app()
# Necessario perché Vercel è un reverse proxy: senza questo Flask genera
# url_for(..., _external=True) con http:// invece di https://, rompendo OAuth.
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
