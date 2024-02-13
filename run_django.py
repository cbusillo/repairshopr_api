from pathlib import Path
import subprocess

def runserver():
    manage_py_path = Path(__file__).parent / "repairshopr_sync/manage.py"
    try:
        subprocess.run(["python", manage_py_path.as_posix(), "runserver"], check=True)
    except subprocess.CalledProcessError as e:
        print(f"Error running the Django server: {e}")
