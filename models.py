import os
import secrets

from peewee import *

def gen_id():
    return secrets.token_urlsafe(8)

db = PostgresqlDatabase(
    os.environ.get('PG_NAME', 'quote_generator'),
    host = os.environ.get('PG_HOST', 'localhost'),
    user = os.environ.get('PG_USER', 'postgres'),
    password = os.environ.get('PG_PASSWORD', 'postgres'),
)

class BaseModel(Model):
    class Meta:
        database = db

class User(BaseModel):
    id = CharField(primary_key=True, default=gen_id)
    email = CharField(max_length=255, unique=True)
    password = CharField(max_length=255)

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return True

    @property
    def is_anonymous(self):
        return False

class Quote(BaseModel):
    id = CharField(primary_key=True, default=gen_id)
    content = TextField(default='')
    author = CharField(max_length=255, default='')
    user = ForeignKeyField(User)

class Collection(BaseModel):
    name = CharField(max_length=255, unique=True)
    user = ForeignKeyField(User)

class QuoteCollection(BaseModel):
    quote = ForeignKeyField(Quote)
    collection = ForeignKeyField(Collection)

    class Meta:
        indexes = (
            (('quote', 'collection'), True),
        )
