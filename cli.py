from operations import *

### helper functions
def get_db_session():
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = SessionLocal()
    return db

def setup_database_schema(engine):
    Base.metadata.create_all(engine)
    with engine.connect() as connection:
        connection.execute(SQL_VIEW)

        # helper function to reset sequences (CRITICAL for development/rollback state)
        def reset_sequence(table_name, pk_column):
            reset_sql = text(f"""
                SELECT setval(pg_get_serial_sequence('{table_name}', '{pk_column}'),
                              COALESCE((SELECT MAX({pk_column}) FROM {table_name}), 0) + 1,
                              false);
            """)
            connection.execute(reset_sql)

        # reset sequences for main entities with auto-incrementing primary keys
        reset_sequence('member', 'member_id')
        reset_sequence('trainer', 'trainer_id')
        reset_sequence('admin', 'admin_id')
        reset_sequence('room', 'room_id')
        reset_sequence('equipmentmaintain', 'equipment_id')

        connection.commit()

def clear_screen():
    print('\n' * 3)

def display_result(result):
    status = result.get('status', 'info')
    message = result.get('message', 'No message provided.')
    if status == 'success':
        print(f"\n✅ SUCCESS: {message}")
    elif status == 'error':
        print(f"\n❌ ERROR: {message}")
    else:
        print(f"\n▶️ INFO: {message}")
    input("\nPress Enter to return to menu...")
    clear_screen()

def authenticate_user(session, name, email):
    clear_screen()
    print("--- 👤 Login ---")

    # 1. Check Admin
    admin_user = session.query(Admin).filter(Admin.name == name, Admin.email == email).first()
    if admin_user:
        return ('admin', admin_user)

    # 2. Check Trainer
    trainer_user = session.query(Trainer).filter(Trainer.name == name, Trainer.email == email).first()
    if trainer_user:
        return ('trainer', trainer_user)

    # 3. Check Member
    member_user = session.query(Member).filter(Member.name == name, Member.email == email).first()
    if member_user:
        return ('member', member_user)

    return (None, None)


### role-specific menus
def member_menu(session, user):
    while True:
        print(f"\n--- Member Menu: {user.name} (ID: {user.member_id}) ---")
        print("1. Book a PT Session")
        print("2. Log Health Metrics")
        print("3. Set Fitness Goal")
        print("4. Update Profile")
        print("5. Logout")

        choice = input("Enter choice (1-5): ").strip()
        clear_screen()

        if choice == '1':
            print("--- Book a PT Session ---")
            trainer_id = input("Trainer ID: ").strip()
            date_str = input("Date (YYYY-MM-DD): ").strip()
            start_hour = input("Start Hour (0-23): ").strip()
            result = book_pt_session(session, user.member_id, trainer_id, date_str, start_hour)
            display_result(result)

        elif choice == '2':
            print("--- Log Health Metrics ---")
            try:
                weight = float(input("Weight (kg): ").strip())
                height = float(input("Height (cm): ").strip())
                hr = int(input("Heart Rate (bpm): ").strip())
                result = log_health_metric(session, user.member_id, weight, height, hr)
                display_result(result)
            except ValueError:
                display_result({"status": "error", "message": "Invalid numeric input."})

        elif choice == '3':
            print("--- Set Fitness Goal ---")
            try:
                target_weight = float(input("Target Weight (kg): ").strip())
                target_fat = float(input("Target Body Fat (%): ").strip())
                result = set_member_fitness_goal(session, user.member_id, target_weight, target_fat)
                display_result(result)
            except ValueError:
                display_result({"status": "error", "message": "Invalid numeric input."})

        elif choice == '4':
            print("--- Update Profile ---")
            # Refresh user object to ensure current values are displayed in prompts
            session.refresh(user)

            # Prompt for all possible fields
            new_name = input(f"New Name (Current: {user.name}, leave blank to skip): ").strip()
            new_dob_str = input(f"New Date of Birth (Current: {user.date_of_birth.isoformat() if user.date_of_birth else 'N/A'}, format YYYY-MM-DD, leave blank to skip): ").strip()
            new_gender = input(f"New Gender (Current: {user.gender}, leave blank to skip): ").strip()
            new_email = input(f"New Email (Current: {user.email}, leave blank to skip): ").strip()

            updates = {}
            if new_name:
                updates['name'] = new_name
            if new_dob_str:
                updates['date_of_birth'] = new_dob_str
            if new_gender:
                updates['gender'] = new_gender
            if new_email:
                updates['email'] = new_email

            if updates:
                result = update_member_profile(session, user.member_id, **updates)
                # If update was successful, refresh the user object to update menu header/prompts for next iteration
                if result['status'] == 'success':
                    session.refresh(user)
                display_result(result)
            else:
                display_result({"status": "info", "message": "No changes requested."})

        elif choice == '5':
            print(f"\nLogging out {user.name}...")
            break
        else:
            print("\nInvalid choice. Please try again.")
            input("Press Enter to continue...")
            clear_screen()

def trainer_menu(session, user):
    while True:
        print(f"\n--- Trainer Menu: {user.name} (ID: {user.trainer_id}) ---")
        print("1. Set Availability (Single Slot)")
        print("2. Set Availability (Weekly - 5 sessions)")
        print("3. View My Active Sessions")
        print("4. Logout")

        choice = input("Enter choice (1-4): ").strip()
        clear_screen()

        if choice == '1' or choice == '2':
            weekly = (choice == '2')
            print(f"--- Set Availability ({'Weekly' if weekly else 'Single'}) ---")
            date_str = input("Start Date (YYYY-MM-DD): ").strip()
            start_hour = input("Start Hour (0-23): ").strip()
            result = set_trainer_availability(session, user.trainer_id, date_str, start_hour, weekly=weekly)
            display_result(result)

        elif choice == '3':
            print("--- My Active Sessions ---")
            result = get_active_pt_sessions(session, user.trainer_id)
            if result['status'] == 'success':
                sessions = result['sessions']
                if sessions:
                    print(f"Found {len(sessions)} active sessions:")
                    print("-" * 80)
                    print(f"| {'Slot ID':<7} | {'Member Name':<15} | {'Start Time':<20} | {'End Time':<20} |")
                    print("-" * 80)
                    for s in sessions:
                        print(f"| {s['slot_id']:<7} | {s['member_name']:<15} | {s['start_time'][:19]:<20} | {s['end_time'][:19]:<20} |")
                    print("-" * 80)
                else:
                    print("No active sessions booked.")
            else:
                print(result['message'])
            input("\nPress Enter to return to menu...")
            clear_screen()

        elif choice == '4':
            print(f"\nLogging out {user.name}...")
            break
        else:
            print("\nInvalid choice. Please try again.")
            input("Press Enter to continue...")
            clear_screen()

def admin_menu(session, user):
    while True:
        print(f"\n--- Admin Menu: {user.name} (ID: {user.admin_id}) ---")
        print("1. Assign Room to PT Session")
        print("2. Log Equipment Issue")
        print("3. Update Equipment Status")
        print("4. Logout")

        choice = input("Enter choice (1-4): ").strip()
        clear_screen()

        if choice == '1':
            print("--- Assign Room ---")
            slot_id = input("PT Session Slot ID to assign: ").strip()
            room_id = input("Room ID to assign: ").strip()
            try:
                result = assign_room_for_session(session, int(room_id), int(slot_id))
                display_result(result)
            except ValueError:
                display_result({"status": "error", "message": "Room ID and Slot ID must be integers."})

        elif choice == '2':
            print("--- Log Equipment Issue ---")
            equipment_id = input("Equipment ID: ").strip()
            room_id = input("Room ID: ").strip()
            issue = input("Issue Description: ").strip()
            try:
                result = log_equipment_issue(session, int(equipment_id), int(room_id), issue)
                display_result(result)
            except ValueError:
                display_result({"status": "error", "message": "Equipment ID and Room ID must be integers."})

        elif choice == '3':
            print("--- Update Equipment Status ---")
            equipment_id = input("Equipment ID to update: ").strip()
            new_status = input("New Status (e.g., 'In Progress', 'Repaired'): ").strip()
            try:
                result = update_equipment_status(session, int(equipment_id), new_status)
                display_result(result)
            except ValueError:
                display_result({"status": "error", "message": "Equipment ID must be an integer."})

        elif choice == '4':
            print(f"\nLogging out {user.name}...")
            break
        else:
            print("\nInvalid choice. Please try again.")
            input("Press Enter to continue...")
            clear_screen()


###
def main_menu():
    engine = create_engine(DATABASE_URL)
    setup_database_schema(engine)
    clear_screen()
    print("Welcome to the Fitness Center Management CLI!")

    while True:
        db = get_db_session()
        try:
            print("\n==============================================")
            print("                MAIN MENU                     ") # Changed from LOGIN to MAIN
            print("==============================================")
            print("1. Member/Trainer/Admin Login")
            print("2. Register as a New Member") # New option for self-registration
            print("3. Exit")

            main_choice = input("Enter choice (1-3): ").strip()
            clear_screen()

            if main_choice == '1':
                # Existing login logic
                print("--- Login ---")
                name = input("Name: ").strip()
                email = input("Email: ").strip()

                role, user = authenticate_user(db, name, email)

                if role == 'admin':
                    print(f"\n✅ Admin login successful. Welcome, {user.name}!")
                    input("Press Enter to continue to the Admin Menu...")
                    clear_screen()
                    admin_menu(db, user)
                elif role == 'trainer':
                    print(f"\n✅ Trainer login successful. Welcome, {user.name}!")
                    input("Press Enter to continue to the Trainer Menu...")
                    clear_screen()
                    trainer_menu(db, user)
                elif role == 'member':
                    print(f"\n✅ Member login successful. Welcome, {user.name}!")
                    input("Press Enter to continue to the Member Menu...")
                    clear_screen()
                    member_menu(db, user)
                else:
                    print("\n❌ Login failed. No user found with that Name and Email combination.")
                    input("Press Enter to try again...")
                    clear_screen()

            elif main_choice == '2':
                # New member registration logic
                print("--- Register as a New Member ---")
                name = input("Name: ").strip()
                email = input("Email: ").strip()
                dob_str = input("Date of Birth (YYYY-MM-DD): ").strip()
                gender = input("Gender (M/F/Other): ").strip()
                result = register_new_member(db, name, email, dob_str, gender)
                display_result(result)

            elif main_choice == '3' or main_choice.lower() == 'exit':
                print("Exiting application. Goodbye!")
                break

            else:
                print("\nInvalid choice. Please try again.")
                input("Press Enter to continue...")
                clear_screen()

        except Exception as e:
            print(f"\nAn unrecoverable application error occurred: {e}")
            print("Please check your database connection and try restarting the CLI.")
            break
        finally:
            db.close()


if __name__ == '__main__':
    main_menu()