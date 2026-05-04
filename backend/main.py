import os
import uuid
import json
import resend

import gspread
from google.oauth2.service_account import Credentials
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

SCOPES = ["https://www.googleapis.com/auth/spreadsheets"]

# Column order in the sheet: id | name | email | purpose | message | submittedAt | status | reply
COL = {
    "id": 1,
    "name": 2,
    "email": 3,
    "purpose": 4,
    "message": 5,
    "submittedAt": 6,
    "status": 7,
    "reply": 8,
}


def get_sheet():
    creds_dict = json.loads(os.environ["GOOGLE_CREDENTIALS"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(creds)
    return client.open_by_key(os.environ["SHEET_ID"]).sheet1


def send_email(to_email, to_name, reply_message, ticket_id):
    resend.api_key = os.environ.get("RESEND_API_KEY")
    resend.Emails.send({
        "from": "onboarding@resend.dev",
        "to": to_email,
        "subject": "Re: Your message to Abdul Rehman",
        "html": f"<p>Hi {to_name},</p><p>{reply_message}</p><p>Best regards,<br>Abdul Rehman</p>",
    })


# ── Request models ──────────────────────────────────────────────────────────

class TicketPayload(BaseModel):
    name: str
    email: str
    purpose: str
    message: str
    submittedAt: str


class ReplyPayload(BaseModel):
    ticketId: str
    replyMessage: str
    toEmail: str
    toName: str


# ── Endpoints ───────────────────────────────────────────────────────────────

@app.post("/ticket")
async def create_ticket(payload: TicketPayload):
    ticket_id = uuid.uuid4().hex[:8]
    sheet = get_sheet()
    sheet.append_row([
        ticket_id,
        payload.name,
        payload.email,
        payload.purpose,
        payload.message,
        payload.submittedAt,
        "open",
        "",
    ])
    return {"success": True, "ticketId": ticket_id}


@app.post("/reply")
async def reply_ticket(payload: ReplyPayload):
    try:
        sheet = get_sheet()

        try:
            cell = sheet.find(payload.ticketId, in_column=COL["id"])
        except gspread.exceptions.CellNotFound:
            raise HTTPException(status_code=404, detail="Ticket not found")

        row = cell.row
        sheet.update_cell(row, COL["status"], "resolved")
        sheet.update_cell(row, COL["reply"], payload.replyMessage)

        send_email(payload.toEmail, payload.toName, payload.replyMessage, payload.ticketId)

        return {"success": True}
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/tickets")
async def get_tickets():
    sheet = get_sheet()
    records = sheet.get_all_records()
    return records
