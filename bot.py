import os
import re
import base64
import asyncio
import json

import discord

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

PROCESSED_FILE = "/data/processed_messages.txt"


DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

GOOGLE_TOKEN_JSON = os.getenv("GOOGLE_TOKEN_JSON")

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


def gmail_service():
    if not GOOGLE_TOKEN_JSON:
        raise RuntimeError("GOOGLE_TOKEN_JSON is not configured.")

    token_data = json.loads(GOOGLE_TOKEN_JSON)

    creds = Credentials.from_authorized_user_info(
        token_data,
        SCOPES
    )

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds.valid:
        raise RuntimeError(
            "Gmail credentials are invalid or expired."
        )

    return build(
        "gmail",
        "v1",
        credentials=creds
    )


def decode_body(data):
    if not data:
        return ""

    padding = "=" * (-len(data) % 4)

    return base64.urlsafe_b64decode(
        data + padding
    ).decode("utf-8", errors="ignore")


def extract_text(payload):
    text = ""

    if "body" in payload:
        data = payload["body"].get("data")

        if data:
            text += decode_body(data)

    for part in payload.get("parts", []):
        text += extract_text(part)

    return text

def load_processed_messages():
    if not os.path.exists(PROCESSED_FILE):
        return set()

    with open(PROCESSED_FILE, "r") as f:
        return {
            line.strip()
            for line in f
            if line.strip()
        }


def save_processed_message(message_id):
    os.makedirs(
        os.path.dirname(PROCESSED_FILE),
        exist_ok=True
    )

    with open(PROCESSED_FILE, "a") as f:
        f.write(message_id + "\n")


def extract_code(text):
    patterns = [
        r"\b(\d{6})\b",
        r"\b(\d{8})\b",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return match.group(1)

    return None


def get_new_messages(service):
    result = service.users().messages().list(
        userId="me",
        q="from:(riotgames.com) newer_than:1d",
        maxResults=10
    ).execute()

    return result.get("messages", [])


def get_message(service, message_id):
    return service.users().messages().get(
        userId="me",
        id=message_id,
        format="full"
    ).execute()


class CodeBot(discord.Client):

    async def setup_hook(self):
        self.gmail = gmail_service()
        self.seen = load_processed_messages()

        asyncio.create_task(
            self.check_gmail()
        )

    async def check_gmail(self):

        await self.wait_until_ready()

        channel = self.get_channel(
            DISCORD_CHANNEL_ID
        )

        if channel is None:
            print("Discord channel not found.")
            return

        while not self.is_closed():

            try:
                messages = get_new_messages(
                    self.gmail
                )

                for item in messages:

                    message_id = item["id"]

                    if message_id in self.seen:
                        continue

                    self.seen.add(message_id)

                    message = get_message(
                        self.gmail,
                        message_id
                    )

                    payload = message.get(
                        "payload",
                        {}
                    )

                    text = extract_text(
                        payload
                    )

                    code = extract_code(text)

                    if code:
                        await channel.send(
                            f"VALORANT login code: `{code}`"
                        )

                        save_processed_message(message_id)
                        self.seen.add(message_id)

            except Exception as e:
                print("Error:", e)

            await asyncio.sleep(10)


intents = discord.Intents.default()

client = CodeBot(
    intents=intents
)

client.run(DISCORD_TOKEN)