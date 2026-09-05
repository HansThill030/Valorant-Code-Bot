import os
import re
import base64
import asyncio

import discord
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_CHANNEL_ID = int(os.getenv("DISCORD_CHANNEL_ID"))

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly"
]


def gmail_service():
    creds = None

    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file(
            "token.json",
            SCOPES
        )

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                "credentials.json",
                SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open("token.json", "w") as f:
            f.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


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
        q='from:(riotgames.com) newer_than:1d',
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
        self.seen = set()

        asyncio.create_task(self.check_gmail())

    async def check_gmail(self):

        await self.wait_until_ready()

        channel = self.get_channel(DISCORD_CHANNEL_ID)

        if channel is None:
            print("Discord channel not found.")
            return

        while not self.is_closed():

            try:
                messages = get_new_messages(self.gmail)

                for item in messages:

                    message_id = item["id"]

                    if message_id in self.seen:
                        continue

                    self.seen.add(message_id)

                    message = get_message(
                        self.gmail,
                        message_id
                    )

                    payload = message.get("payload", {})

                    text = extract_text(payload)

                    code = extract_code(text)

                    if code:
                        await channel.send(
                            f"VALORANT login code: `{code}`"
                        )

            except Exception as e:
                print("Error:", e)

            await asyncio.sleep(10)


intents = discord.Intents.default()

client = CodeBot(intents=intents)

client.run(DISCORD_TOKEN)