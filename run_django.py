# django_manage.py
import subprocess

def runserver():
    makemigrations()
    migrate()
    subprocess.run(["python", "repairshopr_sync/manage.py", "runserver"])

def makemigrations():
    subprocess.run(["python", "repairshopr_sync/manage.py", "makemigrations"])

def migrate():
    subprocess.run(["python", "repairshopr_sync/manage.py", "migrate"])

def import_from_repairshopr():
    makemigrations()
    migrate()
    subprocess.run(["python", "repairshopr_sync/manage.py", "import_from_repairshopr"])

