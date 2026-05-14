from database import SessionLocal
from models import User
from auth import hash_password

db = SessionLocal()

existing_admin = db.query(User).filter(User.username == "admin").first()

if existing_admin:
    print("Admin already exists")
else:
    admin = User(
        username="admin",
        email="admin@test.com",
        hashed_password=hash_password("123"),
        role="admin"
    )
    db.add(admin)
    db.commit()
    print("Admin created successfully")

db.close()