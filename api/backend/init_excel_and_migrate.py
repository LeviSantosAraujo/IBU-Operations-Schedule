#!/usr/bin/env python3
"""
Initialize Excel file and migrate data from JSON
"""

import json
import os
from datetime import date
from pathlib import Path

# First, create an empty Excel file
from excel_store import ensure_excel_structure, set_excel_file, get_excel_file

# Initialize Excel file
excel_path = Path(__file__).parent / "uploads" / "ibu_schedule.xlsx"
ensure_excel_structure(str(excel_path))
set_excel_file(str(excel_path))
print(f"Created Excel file at: {excel_path}")

# Now import and migrate data
from data_store import (
    get_all_employees as json_get_employees,
    get_all_schedules as json_get_schedules,
    get_availabilities as json_get_availabilities,
    get_system_config as json_get_system_config,
    get_availability_requests as json_get_availability_requests,
    get_events as json_get_events,
)
from excel_store import (
    save_employee,
    save_schedule,
    save_availability,
    save_system_config,
    save_availability_request,
    save_event,
    set_manager_password,
)

def migrate_data():
    """Migrate all data from JSON to Excel"""
    print("\n=== Starting migration from JSON to Excel ===")
    
    # 1. Migrate employees
    print("\n1. Migrating employees...")
    employees = json_get_employees()
    print(f"   Found {len(employees)} employees in JSON")
    for emp in employees:
        save_employee(emp)
        print(f"   Migrated employee: {emp.name}")
    
    # 2. Migrate schedules
    print("\n2. Migrating schedules...")
    schedules = json_get_schedules()
    print(f"   Found {len(schedules)} schedules in JSON")
    for schedule in schedules:
        save_schedule(schedule)
        print(f"   Migrated schedule for week: {schedule.week_start_date}")
    
    # 3. Migrate availabilities
    print("\n3. Migrating availabilities...")
    availabilities = json_get_availabilities()
    print(f"   Found {len(availabilities)} availabilities in JSON")
    for avail in availabilities:
        save_availability(avail)
        print(f"   Migrated availability for: {avail.employee_id} ({avail.week_start_date})")
    
    # 4. Migrate system config
    print("\n4. Migrating system config...")
    config = json_get_system_config()
    if config:
        # Convert to dict for Excel storage
        config_dict = config.model_dump() if hasattr(config, 'model_dump') else dict(config)
        save_system_config(config_dict)
        print(f"   Migrated system config")
    else:
        print("   No system config found")
    
    # 5. Migrate availability requests
    print("\n5. Migrating availability requests...")
    requests = json_get_availability_requests()
    print(f"   Found {len(requests)} availability requests in JSON")
    for req in requests:
        save_availability_request(req)
        print(f"   Migrated request: {req.id}")
    
    # 6. Migrate events
    print("\n6. Migrating events...")
    events = json_get_events()
    print(f"   Found {len(events)} events in JSON")
    for event in events:
        save_event(event)
        print(f"   Migrated event: {event.name}")
    
    # 7. Migrate passwords
    print("\n7. Migrating manager passwords...")
    passwords_path = Path(__file__).parent / "data" / "passwords.json"
    if passwords_path.exists():
        with open(passwords_path, 'r') as f:
            passwords = json.load(f)
            for pwd in passwords:
                employee_id = pwd.get('employee_id')
                # Get employee name from the employees list
                employee_name = "Unknown"
                for emp in employees:
                    if emp.id == employee_id:
                        employee_name = emp.name
                        break
                set_manager_password(
                    employee_id,
                    employee_name,
                    pwd['password_hash']  # Already hashed
                )
                print(f"   Migrated password for: {employee_name}")
    else:
        print("   No passwords file found")
    
    print("\n=== Migration complete! ===")
    print("All data has been migrated from JSON to Excel format.")
    print(f"Excel file saved at: {excel_path}")

if __name__ == "__main__":
    migrate_data()
