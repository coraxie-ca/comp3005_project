from operations import *

### Initialization
if __name__ == '__main__':
    engine = create_engine(DATABASE_URL)

    with engine.connect() as connection:
        connection.execute(text("DROP VIEW IF EXISTS ActivePTSessions;"))
        connection.execute(text("DROP TRIGGER IF EXISTS check_goal_completion ON healthmetric;"))
        connection.execute(text("DROP FUNCTION IF EXISTS check_goal_completion_func();"))
        connection.commit() # Commit the DDL drops

    Base.metadata.drop_all(engine) # Clear previous table data for a clean run
    Base.metadata.create_all(engine) # CREATE TABLE

    with engine.connect() as connection:
        connection.execute(SQL_VIEW)
        connection.commit()
        print("Database schema, Index, PostgreSQL Trigger, and View created successfully.")

    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    def get_db():
        db = SessionLocal()
        try:
            return db
        finally:
            db.close()

    db = get_db()

    print("\n---  Setting up initial data (Member, Trainer, Rooms, Admin) ---")
    db.add_all([
        Member(member_id=1, name='Alice Smith', email='alice@club.com', date_of_birth=date(1990, 1, 1), gender='F'),
        Member(member_id=2, name='Jane Doe', email='jane@club.com', date_of_birth=date(1995, 5, 5), gender='F'),
        Trainer(trainer_id=101, name='Bob Johnson', email='bob@club.com'),
        Trainer(trainer_id=102, name='Sarah Connor', email='sarah@club.com'),
        Room(room_id=201, capacity=10),
        Room(room_id=202, capacity=5),
        Admin(admin_id=1, name='Cora', email='cora@club.com')
    ])
    db.commit()
    db.close()