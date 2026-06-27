# IBU Operations Schedule - Architecture

## Data Storage Architecture

### Single Source of Truth: GitHub JSON (json_store.py)

All application data is stored in GitHub JSON files on the `data` branch:
- `employees.json` - Employee records
- `schedules.json` - Weekly schedules with shifts
- `availability_requests.json` - Employee availability requests
- `availabilities.json` - Approved availability records
- `notifications.json` - User notifications
- `system_config.json` - System configuration (including staffing targets, events)
- `events.json` - Event definitions
- `coverage_requirements.json` - Hourly coverage requirements
- `passwords.json` - Manager password hashes

The `json_store.py` module provides the canonical API for reading/writing these files with:
- GitHub API integration with optimistic locking (SHA-based retry)
- Cache invalidation via SHA tracking
- Rate limit protection

### Excel: Export-Only

Excel files are **NOT** a data source. They are used **only** for:
- Daily `.xlsx` download/export for reporting
- Legacy data migration (historical)

The `/api/excel/...` endpoints generate Excel files from JSON data for download purposes only.

### Forbidden: Excel as Data Source

**DO NOT** import or use the following for data operations:
- `data_store_excel.py` - The Excel data layer wrapper
- `excel_store.py` - The Excel file operations

These modules are legacy and should only be used for export generation, never for reading/writing application state.

### Guardrails

1. **Code banners**: `main.py` and `scheduler.py` have top-of-file banners warning against Excel data-source imports.
2. **Memory rule**: A persistent Cascade memory flags this rule to prevent recurrence.
3. **Test guard**: `tests/test_no_excel_data_source.py` validates that `main.py` and `scheduler.py` do not import Excel data-source functions.

## Data Flow

### Write Path
```
Frontend → API endpoint → json_store function → GitHub JSON file
```

### Read Path
```
GitHub JSON file → json_store function → API endpoint → Frontend
```

### Export Path
```
GitHub JSON files → json_store read → Excel generation → .xlsx download
```

## Migration History

The Excel layer was introduced by a prior session without authorization, creating a split-brain where:
- Events were written to JSON but read from Excel config
- Staffing targets were read from Excel config
- Schedules/employees/availabilities had mixed sources

This migration (June 2026) consolidates all data operations to `json_store` and restricts Excel to export-only.
