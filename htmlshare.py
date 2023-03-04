import time
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
from fastapi.responses import HTMLResponse, JSONResponse
from threading import local
import sqlite3
import uuid
import os
import hmac

app = FastAPI()

# Define schema for incoming requests
class HtmlUploadRequest(BaseModel):
    html: str
    password: str

# Define schema for outgoing response
class HtmlUploadResponse(BaseModel):
    id: str

# Define schema for outgoing HTML content
class HtmlGetResponse(BaseModel):
    html: str

RATE_LIMIT_TIMES = 30
RATE_LIMIT_SECONDS = 60
rate_limits = {}

sqlite_storage = local()

def get_sqlite_conn():
    if not hasattr(sqlite_storage, "conn"):
        sqlite_storage.conn = sqlite3.connect("html_database.db")
    return sqlite_storage.conn

@app.on_event("shutdown")
async def shutdown_event():
    if hasattr(sqlite_storage, "conn"):
        sqlite_storage.conn.close()

@app.on_event("startup")
async def shutdown_event():
    conn = get_sqlite_conn()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS html_records 
             (id TEXT PRIMARY KEY, html TEXT)''')
    conn.commit()

@app.middleware("http")
async def rate_limiter_middleware(request: Request, call_next):
    ip_address = request.client.host
    now = time.time()
    window_start = int(now - RATE_LIMIT_SECONDS)

    # Remove expired entries from rate_limits
    expired_ips = []
    for ip, windows in rate_limits.items():
        for window in windows:
            if window < window_start:
                windows.remove(window)
        if not windows:
            expired_ips.append(ip)
    for ip in expired_ips:
        rate_limits.pop(ip, None)

    # Check if the IP is within the rate limit
    if ip_address in rate_limits and len(rate_limits[ip_address]) >= RATE_LIMIT_TIMES:
        return JSONResponse(
            status_code=429, 
            content={"detail": "Too many requests. Please try again later."}
        )
    if ip_address not in rate_limits:
        rate_limits[ip_address] = []
    rate_limits[ip_address].append(int(now))

    # Call the next middleware or endpoint
    response = await call_next(request)
    return response

# Endpoint to upload HTML string and generate ID
@app.post("/html")
def upload_html(html_request: HtmlUploadRequest):
    # Generate unique ID for the record
    record_id = str(uuid.uuid4())

    # Get password from environment variable
    password = os.environ.get("HTMLSHARE_PASSWORD")

    if not password:
        raise ValueError("HTMLSHARE_PASSWORD environment variable not set")

    # Check if provided password matches stored password
    if not hmac.compare_digest(html_request.password, password):
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_sqlite_conn()
    c = conn.cursor()
    # Insert record into database
    c.execute("INSERT INTO html_records VALUES (?, ?)", (record_id, html_request.html))
    conn.commit()

    # Return ID to user
    return HtmlUploadResponse(id=record_id)

# Endpoint to retrieve HTML content by ID
@app.get("/html/{id}", response_class=HTMLResponse)
def get_html(id: str):
    conn = get_sqlite_conn()
    c = conn.cursor()
    # Check if record exists
    c.execute("SELECT html FROM html_records WHERE id=?", (id,))
    record = c.fetchone()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    # Return HTML content as a response body with content type text/html
    return record[0]

# Endpoint to delete record by ID and password
@app.delete("/html/{id}")
def delete_html(id: str, password: str):
    # Get password from environment variable
    stored_password = os.environ.get("HTMLSHARE_PASSWORD")

    if not stored_password:
        raise ValueError("HTMLSHARE_PASSWORD environment variable not set")

    # Use constant-time comparison algorithm to check password
    if not hmac.compare_digest(password, stored_password):
        raise HTTPException(status_code=401, detail="Unauthorized")

    conn = get_sqlite_conn()
    c = conn.cursor()
    # Check if record exists
    c.execute("SELECT * FROM html_records WHERE id=?", (id,))
    record = c.fetchone()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    # Delete record from database
    c.execute("DELETE FROM html_records WHERE id=?", (id,))
    conn.commit()

    # Return success response
    return {"message": "Record deleted"}

print('App loaded')