"""
Punto de entrada WSGI para PythonAnywhere.

En PythonAnywhere, configura tu web app con:
  Source code: /home/TU_USUARIO/cinemacity/backend
  Working directory: /home/TU_USUARIO/cinemacity/backend
  WSGI configuration file: este archivo (o apunta a él)
  Python version: 3.11+

El fichero que PythonAnywhere carga es /var/www/xxx_wsgi.py
Pon dentro:
    import sys
    sys.path.insert(0, '/home/TU_USUARIO/cinemacity/backend')
    from wsgi import application
"""
import sys
import os

# Asegura que el directorio backend esté en el path
sys.path.insert(0, os.path.dirname(__file__))

from app import create_app

application = create_app()
