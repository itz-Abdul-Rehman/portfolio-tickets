import os
import uuid
import json
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

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


def send_email(to_email: str, to_name: str, reply_message: str, ticket_id: str):
    gmail_user = os.environ["GMAIL_USER"]
    gmail_pass = os.environ["GMAIL_APP_PASSWORD"]

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Re: Your message to Abdul Rehman"
    msg["From"] = f"Abdul Rehman <{gmail_user}>"
    msg["To"] = to_email

    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:580px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;">
      <div style="background:#0f172a;padding:28px 36px;border-bottom:3px solid #6366f1;">
        <p style="color:#94a3b8;font-size:11px;letter-spacing:2px;text-transform:uppercase;margin:0 0 6px;">Abdul Rehman</p>
        <h1 style="color:#ffffff;margin:0;font-size:20px;font-weight:600;">Re: Your message to Abdul Rehman</h1>
      </div>
      <div style="padding:36px;">
        <p style="color:#1e293b;font-size:15px;line-height:1.8;margin:0 0 24px;">Dear <strong>{to_name}</strong>,</p>
        <div style="border-left:3px solid #6366f1;padding:16px 20px;background:#f8fafc;margin-bottom:28px;">
          <p style="color:#1e293b;font-size:14px;line-height:1.8;margin:0;white-space:pre-line;">{reply_message}</p>
        </div>
        <p style="color:#94a3b8;font-size:12px;margin:0 0 24px;">Ticket: #{ticket_id}</p>
        <p style="color:#475569;font-size:14px;line-height:1.8;margin:0;">
          Best regards,<br>
          <strong style="color:#0f172a;">Abdul Rehman</strong><br>
          <span style="color:#6366f1;font-size:13px;">AI Automation Developer</span>
        </p>
      </div>
      <div style="padding:16px 36px;background:#f8fafc;border-top:1px solid #e2e8f0;">
        <p style="color:#94a3b8;font-size:11px;margin:0;">Reply to this email to continue the conversation.</p>
      </div>
    </div>
    """

    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, to_email, msg.as_string())


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
