from sqlalchemy import create_engine, Column, Integer, String, Date, Float, ForeignKey, DateTime, Boolean, Text, event, text
from sqlalchemy.orm import relationship, sessionmaker, declarative_base
from sqlalchemy.schema import DDL
from datetime import datetime, date, timedelta, time
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
import sys

### Setup
Base = declarative_base()
# URL format: postgresql+psycopg2://postgres:postgres@localhost:5433/project
DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5433/project"

### Entity Definitions
class Admin(Base):
    __tablename__ = 'admin'
    admin_id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True)

class Room(Base):
    __tablename__ = 'room'
    room_id = Column(Integer, primary_key=True)
    capacity = Column(Integer)

    # Relationships
    schedulept = relationship("SchedulePT", back_populates="room")
    equipment_maintains = relationship("EquipmentMaintain", back_populates="room")

class Member(Base):
    __tablename__ = 'member'
    member_id = Column(Integer, primary_key=True)
    name = Column(String)
    date_of_birth = Column(Date)
    gender = Column(String)
    email = Column(String, unique=True)

    # Relationships
    health_metrics = relationship("HealthMetric", back_populates="member")
    fitness_goals = relationship("FitnessGoal", back_populates="member")
    available_times = relationship("AvailableTime", back_populates="member")

class Trainer(Base):
    __tablename__ = 'trainer'
    trainer_id = Column(Integer, primary_key=True)
    name = Column(String)
    email = Column(String, unique=True)

    # Relationships
    available_times = relationship("AvailableTime", back_populates="trainer")

class HealthMetric(Base):
    __tablename__ = 'healthmetric'
    record_id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey('member.member_id'))
    date = Column(Date, default=date.today)
    weight = Column(Float)
    height = Column(Float)
    heart_rate = Column(Integer)

    # Relationship
    member = relationship("Member", back_populates="health_metrics")

class FitnessGoal(Base):
    __tablename__ = 'fitnessgoal'
    goal_id = Column(Integer, primary_key=True)
    member_id = Column(Integer, ForeignKey('member.member_id'))
    date = Column(Date, default=date.today)
    target_body_weight = Column(Float)
    target_body_fat = Column(Float)
    status = Column(String) # 'Active', 'Completed'

    # Relationship
    member = relationship("Member", back_populates="fitness_goals")

class AvailableTime(Base):
    __tablename__ = 'availabletime'
    slot_id = Column(Integer, primary_key=True)
    trainer_id = Column(Integer, ForeignKey('trainer.trainer_id'))
    date = Column(Date)
    start_time = Column(Integer) # stores the starting hour (0-23)
    # member_id is NULL for general availability, set when booked
    member_id = Column(Integer, ForeignKey('member.member_id'), nullable=True)

    # Relationship
    trainer = relationship("Trainer", back_populates="available_times")
    member = relationship("Member", back_populates="available_times")
    schedulept = relationship("SchedulePT", uselist=False, back_populates="available_times") # one-to-one relationship

class SchedulePT(Base):
    __tablename__ = 'schedulept'
    # slot_id is PK and FK to AvailableTime, creating a 1:1 relationship
    slot_id = Column(Integer, ForeignKey('availabletime.slot_id'), primary_key=True)
    room_id = Column(Integer, ForeignKey('room.room_id'))

    # Relationships
    available_times = relationship("AvailableTime", back_populates="schedulept")
    room = relationship("Room", back_populates="schedulept")

class EquipmentMaintain(Base):
    __tablename__ = 'equipmentmaintain'
    equipment_id = Column(Integer, primary_key=True)
    room_id = Column(Integer, ForeignKey('room.room_id'))
    issue = Column(Text)
    status = Column(String) # 'Needs Repair', 'In Progress', 'Repaired'

    # Relationship
    room = relationship("Room", back_populates="equipment_maintains")


### View, Index, Trigger
# --- INDEX Implementation ---
# Create an index on the 'status' column of EquipmentMaintain
idx_equipment_status = DDL("CREATE INDEX idx_equipment_status ON equipmentmaintain (status)")
event.listen(EquipmentMaintain.__table__, 'after_create', idx_equipment_status)

# --- TRIGGER Implementation ---
PG_TRIGGER_DDL = DDL("""
CREATE OR REPLACE FUNCTION check_goal_completion_func()
RETURNS TRIGGER AS $$
BEGIN
    UPDATE fitnessgoal
    SET status = 'Completed'
    WHERE member_id = NEW.member_id
    AND status = 'Active'
    AND NEW.weight <= target_body_weight;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER check_goal_completion
AFTER INSERT ON healthmetric
FOR EACH ROW
EXECUTE FUNCTION check_goal_completion_func();
""")
event.listen(HealthMetric.__table__, 'after_create', PG_TRIGGER_DDL)

# --- VIEW Implementation ---
SQL_VIEW = DDL("""
CREATE OR REPLACE VIEW ActivePTSessions AS
SELECT
    s.slot_id,
    m.name AS member_name,
    t.name AS trainer_name,
    t.trainer_id AS trainer_id,
    (a.date::timestamp + (a.start_time || ' hours')::interval) AS start_time,
    ((a.date::timestamp + (a.start_time || ' hours')::interval) + interval '1 hour') AS end_time,
    'Booked' AS status
FROM
    schedulept s
JOIN
    availabletime a ON s.slot_id = a.slot_id
JOIN
    member m ON a.member_id = m.member_id
JOIN
    trainer t ON a.trainer_id = t.trainer_id;
""")