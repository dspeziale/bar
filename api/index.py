import sys
import os

# Aggiunge la root del progetto al path così "from app import ..." funziona
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app

# Vercel cerca una variabile "app" di tipo WSGI callable
app = create_app()
