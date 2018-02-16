import models

def migrate():
    models.db.connect()
    models.db.create_tables([
        models.User,
        models.Quote,
        models.Collection,
        models.QuoteCollection,
    ])
    models.db.close()

if __name__ == '__main__':
    migrate()
