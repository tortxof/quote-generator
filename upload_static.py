import flask_s3

from app import app

def main():
    flask_s3.create_all(app)
