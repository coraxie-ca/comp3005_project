from classes import *

### Member functions
# 1.User Registration
def register_new_member(session, name, email, dob_str, gender):
    try:
        dob = datetime.strptime(dob_str, '%Y-%m-%d').date()
        new_member = Member(name=name, email=email, date_of_birth=dob, gender=gender)
        session.add(new_member)
        session.commit()
        return {"status": "success", "message": f"Member {name} registered successfully with ID: {new_member.member_id}"}
    except ValueError:
        session.rollback()
        return {"status": "error", "message": "Invalid date format. Use YYYY-MM-DD."}
    except IntegrityError: # Catch IntegrityError for constraint violations (like unique email)
        session.rollback()
        return {"status": "error", "message": f"Registration failed: The email address '{email}' is already in use. Please use a different email."}
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"An unexpected error occurred during registration: {e}"}

# 2.Profile Management
def update_member_profile(session, member_id, **kwargs):
    member = session.get(Member, member_id)
    if not member:
        return {"status": "error", "message": f"Member ID {member_id} not found."}

    # Handle date conversion for date_of_birth string input
    if 'date_of_birth' in kwargs and kwargs['date_of_birth']:
        try:
            kwargs['date_of_birth'] = datetime.strptime(kwargs['date_of_birth'], '%Y-%m-%d').date()
        except ValueError:
            session.rollback()
            return {"status": "error", "message": "Invalid date format for date_of_birth. Use YYYY-MM-DD."}

    for key, value in kwargs.items():
        if hasattr(member, key) and key not in ['member_id']:
            setattr(member, key, value)
    try:
        session.commit()
        return {"status": "success", "message": f"Profile for member {member_id} updated."}
    except Exception as e:
        session.rollback()
        if 'duplicate key value violates unique constraint' in str(e):
            return {"status": "error", "message": "Update failed: The new email address is already in use by another member."}
        return {"status": "error", "message": f"An unexpected error occurred during update: {e}"}

def set_member_fitness_goal(session, member_id, target_weight, target_fat, status='Active'):
    new_goal = FitnessGoal(
        member_id=member_id,
        target_body_weight=target_weight,
        target_body_fat=target_fat,
        status=status,
        date=date.today()
    )
    session.add(new_goal)
    session.commit()
    return {"status": "success", "message": f"New fitness goal set for member {member_id}."}

# 3.Health History
def log_health_metric(session, member_id, weight, height, heart_rate):
    new_metric = HealthMetric(
        member_id=member_id,
        weight=weight,
        height=height,
        heart_rate=heart_rate,
        date=date.today()
    )
    session.add(new_metric)
    session.commit()
    return {"status": "success", "message": f"Health metric logged for member {member_id}. Goal status checked by trigger."}

# 4. PT Session Scheduling
def book_pt_session(session, member_id, trainer_id, date_str, start_hour):
    # The room assignment is deferred to the Admin via the assign_room_for_session function
    # Session duration is assumed to be 1 hour, starting exactly on the hour (0-23)
    try:
        slot_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time_int = int(start_hour)

        if not (0 <= start_time_int <= 23):
            return {"status": "error", "message": "Invalid start_hour. Must be an integer between 0 and 23."}
    except ValueError:
        return {"status": "error", "message": "Invalid date format (Use YYYY-MM-DD) or start_hour (Must be integer)."}

    # find the AVAILABLE slot using date and integer hour
    slot_stmt = select(AvailableTime).where(
        AvailableTime.trainer_id == trainer_id,
        AvailableTime.date == slot_date,
        AvailableTime.start_time == start_time_int,
        AvailableTime.member_id.is_(None) # slot is available if member_id is NULL
    )
    available_slot = session.execute(slot_stmt).scalar_one_or_none()

    if not available_slot:
        return {"status": "error", "message": f"Trainer {trainer_id} is not available on {date_str} at {start_time_int:02d}:00 for a 1-hour session, or the slot is already booked."}

    try:
        # book the slot in AvailableTime (setting member_id books it)
        available_slot.member_id = member_id
        # add new slot_id to SchedulePT for admin to assign room
        existing_sched = session.get(SchedulePT, available_slot.slot_id)
        if not existing_sched:
            new_sched = SchedulePT(slot_id=available_slot.slot_id, room_id=None)
            session.add(new_sched)
        session.commit()

        return {"status": "success", "message": f"PT session booked for member {member_id} with Trainer {trainer_id} on {date_str} at {start_time_int:02d}:00 (Slot ID: {available_slot.slot_id}). Room assignment pending."}

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Booking failed due to a database error: {e}"}


### Trainer Functions
# 1.Set Availability
def set_trainer_availability(session, trainer_id, date_str, start_hour, weekly=False):
    # Expects start_hour to be an integer (0-23).
    # If weekly=True, sets availability for the starting date and the following 4 weeks (5 total sessions).
    # Availability slot is assumed to be 1 hour long, starting exactly on the hour.
    try:
        start_date = datetime.strptime(date_str, '%Y-%m-%d').date()
        start_time_int = int(start_hour)

        if not (0 <= start_time_int <= 23):
            return {"status": "error", "message": "Invalid start_hour. Must be an integer between 0 and 23."}

    except ValueError:
        return {"status": "error", "message": "Invalid date format (Use YYYY-MM-DD) or start_hour (Must be integer)."}

    slots_added = 0
    total_slots = 5 if weekly else 1

    results = []
    new_slot = None

    for i in range(total_slots):
        slot_date = start_date + timedelta(weeks=i)

        # check for existing slots starting at the same hour on this date
        overlap = session.query(AvailableTime).filter(
            AvailableTime.trainer_id == trainer_id,
            AvailableTime.date == slot_date,
            AvailableTime.start_time == start_time_int
        ).first()

        if overlap:
            results.append(f"Overlap detected: Slot for {slot_date} at {start_time_int:02d}:00 already exists.")
            continue # skip adding this slot but continue loop

        # add the new slot
        new_slot = AvailableTime(
            trainer_id=trainer_id,
            date=slot_date,
            start_time=start_time_int,
            member_id=None
        )
        session.add(new_slot)
        slots_added += 1
        results.append(f"Slot added for {slot_date} (ID: {new_slot.slot_id if new_slot.slot_id else 'pending'})") # slot_id might be pending commit

    try:
        session.commit()
    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Database error during commit: {e}"}

    if weekly:
        if slots_added == total_slots:
            return {"status": "success", "message": f"Weekly availability set for trainer {trainer_id}. {slots_added} sessions added starting from {date_str}."}
        else:
            return {"status": "success", "message": f"Weekly availability attempted for trainer {trainer_id}. {slots_added} of {total_slots} sessions added. \nDetails:\n {'\n'.join(results)}"}
    else:
        if slots_added == 1:
            return {"status": "success", "message": f"Availability set for trainer {trainer_id} on {date_str} at {start_time_int:02d}:00 (Slot ID: {new_slot.slot_id})."}
        else:
            # This handles the case where the single slot was an overlap or other error
            return {"status": "error", "message": f"Failed to add single slot for trainer {trainer_id}. Reason: {results[0] if results else 'Unknown error.'}"}

# 2. Schedule View
def get_active_pt_sessions(session, trainer_id):
    # fetches all booked PT sessions for a specific trainer using the ActivePTSessions View
    try:
        view_query = text("SELECT slot_id, member_name, trainer_name, start_time, end_time, status FROM ActivePTSessions WHERE trainer_id = :tid")

        # Execute the query, passing the trainer_id as a parameter
        results = session.execute(view_query, {"tid": trainer_id}).fetchall()

        session_list = []
        for row in results:
            # Row structure: slot_id, member_name, trainer_name, start_time, end_time, status
            start_time_str = row[3].isoformat() if row[3] else None
            end_time_str = row[4].isoformat() if row[4] else None

            session_list.append({
                'slot_id': row[0],
                'member_name': row[1],
                'trainer_name': row[2],
                'start_time': start_time_str,
                'end_time': end_time_str,
                'status': row[5]
            })

        return {"status": "success", "sessions": session_list}

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Failed to retrieve active PT sessions: {e}"}


### Administrative Staff Functions
# 1. Room Booking
def assign_room_for_session(session, slot_id, room_id):
    try:
        booked_slot = session.get(SchedulePT, slot_id)
        if not booked_slot:
            return {"status": "error", "message": f"SchedulePT slot {slot_id} not found."}

        slot_room_id = booked_slot.room_id

        if slot_room_id is not None:
            return {"status": "error", "message": f"Available time slot {slot_id} is already assigned with room {slot_room_id}."}

        # check if room_id exists in Room table
        room_check = session.get(Room, room_id)
        if not room_check:
            return {"status": "error", "message": f"Room ID {room_id} does not exist in the database."}

        available_slot = session.get(AvailableTime, slot_id)
        if not available_slot:
            return {"status": "error", "message": f"AvailableTime slot {slot_id} not found."}

        available_date = available_slot.date
        available_time = available_slot.start_time

        # get all booked SchedulePT slots for the day/room
        existing_slots = session.query(SchedulePT).join(AvailableTime).filter(
            SchedulePT.room_id == room_id,
            AvailableTime.date == available_date,
            AvailableTime.start_time == available_time,
        ).all()

        # check if room_id is already booked at the date/time
        if existing_slots:
            return {"status": "error", "message": f"Room {room_id} is not AVAILABLE at {available_time} on {available_date}."}

        booked_slot.room_id = room_id
        session.commit()

        return {"status": "success", "message": f"Room {room_id} is AVAILABLE for booking at {available_time} on {available_date}."}

    except Exception as e:
        session.rollback()
        return {"status": "error", "message": f"Database error while assigning room: {e}"}

# 2. Equipment Management
def log_equipment_issue(session, equipment_id, room_id, issue):
    new_issue = EquipmentMaintain(
        equipment_id=equipment_id,
        room_id=room_id,
        issue=issue,
        status='Needs Repair'
    )
    session.add(new_issue)
    session.commit()
    return {"status": "success", "message": f"Issue logged for equipment {equipment_id} in room {room_id}. Status: Needs Repair."}

def update_equipment_status(session, equipment_id, new_status):
    equipment = session.get(EquipmentMaintain, equipment_id)
    if not equipment:
        return {"status": "error", "message": f"Equipment ID {equipment_id} not found."}

    equipment.status = new_status
    session.commit()
    return {"status": "success", "message": f"Status for equipment {equipment_id} updated to: {new_status}."}
