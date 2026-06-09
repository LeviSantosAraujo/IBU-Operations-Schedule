#!/usr/bin/env python3
"""
Analyze past 4 weeks of schedule data to determine average employees per location
Excludes events from the analysis
"""

import sys
sys.path.insert(0, '.')

from excel_store import get_workbook
from collections import defaultdict
from datetime import date

# Past 4 weeks sheet names
WEEKS_TO_ANALYZE = [
    'June 1-7',
    'May 25-31',
    'May 18-24',
    'May 11-17'
]

# Location mappings to normalize different variations
LOCATION_MAPPINGS = {
    'event': 'event',
    'ground': 'ground floor',
    'ground floor': 'ground floor',
    'gf': 'ground floor',
    'gr': 'ground floor',
    'second': '2nd floor',
    '2nd floor': '2nd floor',
    '2f': '2nd floor',
    'f2': '2nd floor',
    'sixth': '6th floor',
    '6th floor': '6th floor',
    '6f': '6th floor',
    'f6': '6th floor',
    'call center': 'call center',
    'cc': 'call center',
    '80 bloor': '80 bloor',
    'bloor': '80 bloor',
    'wfh': 'working from home',
    'working from home': 'working from home',
    'day off': 'day off',
    'day_off': 'day off',
}

def normalize_location(loc):
    """Normalize location name to standard format"""
    if not loc:
        return None
    loc_lower = loc.lower().strip()
    return LOCATION_MAPPINGS.get(loc_lower, loc_lower)

def parse_shift_text(shift_text):
    """Parse shift text to extract location and time"""
    if not shift_text:
        return None, None, None
    
    shift_text = str(shift_text).strip()
    if not shift_text or shift_text.lower() in ['off', '']:
        return None, None, None
    
    # Normalize the text for easier parsing
    text_lower = shift_text.lower()
    
    # Check for event-related content (exclude these)
    event_keywords = ['event', 'events', 'lieu', 'admin', 'offsite', 'niche visit', 'internship', 'up-to']
    for keyword in event_keywords:
        if keyword in text_lower:
            return None, None, shift_text  # Return as event/other
    
    # Extract core location using patterns
    # Priority order for location detection
    location_patterns = [
        ('80 bloor', ['80 bloor', 'bloor']),
        ('working from home', ['wfh', 'working from home', 'wfh/']),
        ('call center', ['cc', 'call center', 'cc gr', 'gr cc', 'f6 cc', 'cc f6', 'f6cc', 'cc f6']),
        ('6th floor', ['6th floor', 'f6', '6f', 'f6 cc', 'f6cc']),
        ('2nd floor', ['2nd floor', 'f2', '2f', 'f2 cc', 'f2/']),
        ('ground floor', ['ground floor', 'gr', 'gf', 'ground']),
    ]
    
    detected_location = None
    for location, patterns in location_patterns:
        for pattern in patterns:
            if pattern in text_lower:
                detected_location = location
                break
        if detected_location:
            break
    
    # If no location detected, check if it's just a time range (no location specified)
    if not detected_location:
        # Check if it looks like just a time range
        if '-' in shift_text and len(shift_text.split()) <= 3:
            return None, None, shift_text  # No location specified
    
    return None, detected_location, shift_text

def analyze_sheet(sheet_name, wb):
    """Analyze a single week's schedule sheet"""
    if sheet_name not in wb.sheetnames:
        print(f"Sheet '{sheet_name}' not found")
        return None
    
    sheet = wb[sheet_name]
    
    # Location counts for this week
    location_counts = defaultdict(int)
    
    # Detect format by checking row 1
    row1_col2 = str(sheet.cell(row=1, column=2).value or '').lower()
    is_native_format = 'monday' in row1_col2 or 'mon' in row1_col2
    
    if is_native_format:
        # Native format: Name, Mon shift, Mon hrs, Tue shift, Tue hrs, ...
        # Row 3 is EVENTS, Row 4+ are employees
        for row_idx in range(4, sheet.max_row + 1):
            name = sheet.cell(row=row_idx, column=1).value
            if not name:
                continue
            
            # Skip if this is a summary row
            name_str = str(name).strip().lower()
            if 'total' in name_str or 'summary' in name_str:
                continue
            
            # Check each day's shift (columns 2, 4, 6, 8, 10, 12, 14 for Mon-Sun)
            day_columns = [2, 4, 6, 8, 10, 12, 14]
            for col in day_columns:
                shift_text = sheet.cell(row=row_idx, column=col).value
                time_range, location, raw_text = parse_shift_text(shift_text)
                
                if location and location != 'event':
                    location_counts[location] += 1
    else:
        # Legacy format - skip for now or implement if needed
        print(f"Sheet '{sheet_name}' uses legacy format, skipping")
    
    return dict(location_counts)

def main():
    wb = get_workbook()
    if not wb:
        print("Could not load workbook")
        return
    
    print("Analyzing past 4 weeks of schedule data...")
    print("=" * 60)
    
    # Store weekly data
    weekly_data = {}
    
    for week in WEEKS_TO_ANALYZE:
        print(f"\nAnalyzing week: {week}")
        counts = analyze_sheet(week, wb)
        if counts:
            weekly_data[week] = counts
            print(f"  Location counts: {counts}")
        else:
            print(f"  No data found")
    
    wb.close()
    
    # Calculate averages
    print("\n" + "=" * 60)
    print("AVERAGE EMPLOYEES PER LOCATION (PAST 4 WEEKS)")
    print("=" * 60)
    
    # Aggregate all location counts
    location_totals = defaultdict(list)
    
    for week, counts in weekly_data.items():
        for location, count in counts.items():
            location_totals[location].append(count)
    
    # Calculate and display averages
    if location_totals:
        for location in sorted(location_totals.keys()):
            counts = location_totals[location]
            avg = sum(counts) / len(counts)
            print(f"{location:20s}: {avg:.1f} employees/week (range: {min(counts)}-{max(counts)})")
    else:
        print("No location data found")

if __name__ == '__main__':
    main()
