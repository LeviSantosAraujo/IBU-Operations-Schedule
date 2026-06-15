#!/usr/bin/env python3
"""
Minimal entrypoint for Vercel deployment on data branch.
This branch only stores the Excel file, but Vercel requires a Python entrypoint.
"""
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {"message": "Data branch - only stores Excel file, no API functionality"}
