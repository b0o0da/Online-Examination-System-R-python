from database import engine, Base
import models

Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)

print("Tables recreated successfully")

print("Tables:")
for table in Base.metadata.tables.keys():
    print(table)