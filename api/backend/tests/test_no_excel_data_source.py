"""
Test guard to prevent Excel data-source imports in main.py and scheduler.py.

This test ensures that Excel is NOT used as a data source, only for export.
"""

import os
import re
from pathlib import Path


def test_main_py_no_excel_data_source_imports():
    """main.py should not import data_store_excel or excel_store for data operations."""
    main_py_path = Path(__file__).parent.parent / "main.py"
    content = main_py_path.read_text()

    # Remove comments to avoid false positives in banner comments
    lines_without_comments = []
    for line in content.split('\n'):
        # Remove inline comments
        line = line.split('#')[0]
        lines_without_comments.append(line)
    content_no_comments = '\n'.join(lines_without_comments)

    # Forbidden patterns (data-source imports)
    forbidden_patterns = [
        r"from data_store_excel import",
        r"import data_store_excel",
    ]

    violations = []
    for pattern in forbidden_patterns:
        matches = re.findall(pattern, content_no_comments)
        if matches:
            violations.append(f"Found forbidden pattern: {pattern} ({len(matches)} times)")

    # Check if any excel_store import is for export-only functions
    # If we find excel_store imports, verify they're only for export helpers
    if "from excel_store import" in content_no_comments:
        # Extract the import line (handle multi-line imports with parentheses)
        import_match = re.search(r"from excel_store import \(([^)]+)\)", content_no_comments)
        if import_match:
            import_text = import_match.group(1)
            # Remove newlines and extra whitespace
            import_text = import_text.replace('\n', ' ')
            imported_funcs = [f.strip() for f in import_text.split(",")]
            # Allow only export-related functions
            allowed_export_funcs = {"_get_workbook", "_save_workbook", "_invalidate_cache", "set_blob_key", "_clear_workbook_cache"}
            forbidden_funcs = set(imported_funcs) - allowed_export_funcs
            if forbidden_funcs:
                violations.append(f"excel_store imports non-export functions: {forbidden_funcs}")

    if violations:
        raise AssertionError(
            f"main.py contains forbidden Excel data-source imports:\n" + "\n".join(violations)
        )


def test_scheduler_py_no_excel_data_source_imports():
    """scheduler.py should not import data_store_excel or excel_store for data operations."""
    scheduler_py_path = Path(__file__).parent.parent / "scheduler.py"
    content = scheduler_py_path.read_text()

    # Remove comments to avoid false positives in banner comments
    lines_without_comments = []
    for line in content.split('\n'):
        # Remove inline comments
        line = line.split('#')[0]
        lines_without_comments.append(line)
    content_no_comments = '\n'.join(lines_without_comments)

    # Forbidden patterns (data-source imports)
    forbidden_patterns = [
        r"from data_store_excel import",
        r"import data_store_excel",
    ]

    violations = []
    for pattern in forbidden_patterns:
        matches = re.findall(pattern, content_no_comments)
        if matches:
            violations.append(f"Found forbidden pattern: {pattern} ({len(matches)} times)")

    # Check excel_store imports - only get_location_color is allowed
    if "from excel_store import" in content_no_comments:
        import_match = re.search(r"from excel_store import ([^\n]+)", content_no_comments)
        if import_match:
            imported_funcs = [f.strip() for f in import_match.group(1).split(",")]
            allowed_helpers = {"get_location_color"}
            forbidden_funcs = set(imported_funcs) - allowed_helpers
            if forbidden_funcs:
                violations.append(f"scheduler.py imports non-helper from excel_store: {forbidden_funcs}")

    if violations:
        raise AssertionError(
            f"scheduler.py contains forbidden Excel data-source imports:\n" + "\n".join(violations)
        )


if __name__ == "__main__":
    # Run tests
    print("Running Excel data-source import guard tests...")
    try:
        test_main_py_no_excel_data_source_imports()
        print("✓ main.py: No forbidden Excel data-source imports")
    except AssertionError as e:
        print(f"✗ main.py: {e}")

    try:
        test_scheduler_py_no_excel_data_source_imports()
        print("✓ scheduler.py: No forbidden Excel data-source imports")
    except AssertionError as e:
        print(f"✗ scheduler.py: {e}")

    print("\nGuard tests complete.")
