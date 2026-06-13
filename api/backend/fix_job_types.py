import json

with open('data/schedules.json', 'r') as f:
    schedules = json.load(f)

location_to_job_type = {
    'ground floor': 'ground_floor',
    'second floor': 'second_floor',
    'sixth floor': 'sixth_floor',
    'call center': 'call_center',
    'classroom': 'classroom',
    'event': 'event',
    'elevator': 'elevator',
    'ibu ops': 'ibu_ops',
    'desk': 'desk',
    'management': 'management'
}

fixed_count = 0
for schedule in schedules:
    for shift in schedule['shifts']:
        if shift['job_type'] == 'employee':
            location = shift.get('location') or ''
            location = location.lower()
            for loc_key, job_type in location_to_job_type.items():
                if loc_key in location:
                    shift['job_type'] = job_type
                    fixed_count += 1
                    break
            else:
                shift['job_type'] = 'ibu_ops'
                fixed_count += 1

with open('data/schedules.json', 'w') as f:
    json.dump(schedules, f, indent=2)

print(f'Fixed {fixed_count} job_type values')
