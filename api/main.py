#!/usr/bin/env python3
"""
Minimal entrypoint for Vercel deployment on data branch.
This branch only stores the Excel file, but Vercel requires a Python entrypoint.
"""
import sys

print("[DATA BRANCH] This branch only stores the Excel data file.")
print("[DATA BRANCH] No API functionality is available on this branch.")
sys.exit(0)
