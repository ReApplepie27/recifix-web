"""Create the Recifix tables:  python init_db.py"""
from app import create_app

app = create_app()
with app.app_context():
    app.extensions["db"].init_schema()
print("Tables are ready.")
