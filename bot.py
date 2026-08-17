import os
import asyncio
import random
import string
import html
import requests

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
BASE_URL = "https://api.mail.tm"


def generate_password():
    return "".join(
        random.choices(
            string.ascii_letters + string.digits,
            k=16
        )
    )


def create_temp_account():
    # Available Mail.tm domain
    response = requests.get(
        f"{BASE_URL}/domains",
        timeout=15
    )
    response.raise_for_status()

    domains = response.json().get(
        "hydra:member",
        []
    )

    if not domains:
        raise Exception(
            "Mail.tm par koi domain available nahi hai."
        )

    # Active domain choose karo
    active_domains = [
        item["domain"]
        for item in domains
        if item.get("isActive", True)
    ]

    if not active_domains:
        active_domains = [
            item["domain"]
            for item in domains
        ]

    domain = random.choice(active_domains)

    username = "".join(
        random.choices(
            string.ascii_lowercase + string.digits,
            k=12
        )
    )

    email = f"{username}@{domain}"
    password = generate_password()

    response = requests.post(
        f"{BASE_URL}/accounts",
        json={
            "address": email,
            "password": password
        },
        timeout=15
    )

    if response.status_code not in (200, 201):
        raise Exception(
            f"Account creation failed: "
            f"{response.status_code}\n"
            f"{response.text}"
        )

    return email, password


def get_token(email, password):
    response = requests.post(
        f"{BASE_URL}/token",
        json={
            "address": email,
            "password": password
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json()["token"]


def get_messages(token):
    response = requests.get(
        f"{BASE_URL}/messages",
        headers={
            "Authorization": f"Bearer {token}"
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json().get(
        "hydra:member",
        []
    )


def get_full_message(token, message_id):
    response = requests.get(
        f"{BASE_URL}/messages/{message_id}",
        headers={
            "Authorization": f"Bearer {token}"
        },
        timeout=15
    )

    response.raise_for_status()

    return response.json()


async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    await update.message.reply_text(
        "🤖 <b>Temp Mail Bot</b>\n\n"
        "/get — New temporary email\n"
        "/stop — Stop inbox monitoring",
        parse_mode="HTML"
    )


async def get_mail(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):
    chat_id = update.effective_chat.id

    # Agar purani monitoring chal rahi hai
    old_job = context.user_data.get(
        "monitor_job"
    )

    if old_job:
        old_job.schedule_removal()

    await update.message.reply_text(
        "⏳ Temporary email create kar raha hoon..."
    )

    try:
        # Account create
        email, password = await asyncio.to_thread(
            create_temp_account
        )

        # Login token
        token = await asyncio.to_thread(
            get_token,
            email,
            password
        )

        # User data save
        context.user_data["email"] = email
        context.user_data["password"] = password
        context.user_data["token"] = token

        # Background inbox monitor
        job = context.job_queue.run_repeating(
            monitor_inbox,
            interval=5,
            first=5,
            data={
                "chat_id": chat_id,
                "token": token,
                "seen_messages": set()
            }
        )

        context.user_data["monitor_job"] = job

        await update.message.reply_text(
            "✅ <b>Temporary Email Ready</b>\n\n"
            f"📬 Email:\n"
            f"<code>{html.escape(email)}</code>\n\n"
            f"🔑 Password:\n"
            f"<code>{html.escape(password)}</code>\n\n"
            "📡 Inbox monitoring: <b>ON</b>\n"
            "⏱️ Checking every 5 seconds\n\n"
            "📩 Inbox me koi bhi naya email aayega "
            "to automatically isi Telegram chat me bhej dunga.\n\n"
