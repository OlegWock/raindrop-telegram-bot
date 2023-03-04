from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import sqlite3
import uuid
import secrets
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

# Connect to SQLite database
conn = sqlite3.connect('html_database.db')
c = conn.cursor()

# Create table if it does not exist
c.execute('''CREATE TABLE IF NOT EXISTS html_records 
             (id TEXT PRIMARY KEY, html TEXT, password TEXT)''')
conn.commit()

# Endpoint to upload HTML string and password
@app.post("/html")
def upload_html(html_request: HtmlUploadRequest):
    # Generate unique ID for the record
    record_id = str(uuid.uuid4())

    # Insert record into database
    c.execute("INSERT INTO html_records VALUES (?, ?, ?)", (record_id, html_request.html, html_request.password))
    conn.commit()

    # Return ID to user
    return HtmlUploadResponse(id=record_id)

# Endpoint to delete record by ID and password
@app.delete("/html/{id}")
def delete_html(id: str, password: str):
    # Check if record exists and get password
    c.execute("SELECT password FROM html_records WHERE id=?", (id,))
    record = c.fetchone()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    stored_password = record[0]

    # Use constant-time comparison algorithm to check password
    if not hmac.compare_digest(password, stored_password):
        raise HTTPException(status_code=401, detail="Unauthorized")

    # Delete record from database
    c.execute("DELETE FROM html_records WHERE id=?", (id,))
    conn.commit()

    # Return success response
    return {"message": "Record deleted"}

# Endpoint to retrieve HTML content by ID
@app.get("/html/{id}")
def get_html(id: str):
    # Check if record exists
    c.execute("SELECT html FROM html_records WHERE id=?", (id,))
    record = c.fetchone()

    if record is None:
        raise HTTPException(status_code=404, detail="Record not found")

    # Return HTML content to user
    return HtmlGetResponse(html=record[0])