"""
UDI LINGO — African language learning Telegram bot.

Required environment variables:
  BOT_TOKEN
  OPENAI_KEY

Optional Supabase integration:
  SUPABASE_URL
  SUPABASE_KEY

Install:
  pip install "python-telegram-bot>=20,<23" "openai>=1" supabase
"""

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from flask import Flask
import threading

flask_app = Flask(__name__)
@flask_app.route('/')
def home():
    return "UDI LINGO Bot is Live!"

def run_flask():
    flask_app.run(host='0.0.0.0',port=10000)
from openai import OpenAI
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.constants import ParseMode
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

# ---------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger("udi_lingo")

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing. Add it to your environment.")
if not OPENAI_KEY:
    raise RuntimeError("OPENAI_KEY is missing. Add it to your environment.")

client = OpenAI(api_key=OPENAI_KEY)

supabase = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        from supabase import create_client

        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        logger.info("Supabase integration enabled.")
    except Exception:
        logger.exception("Supabase initialization failed; continuing without it.")

DATA_FILE = Path("udi_bot_data.json")
TRAINING_FILE = Path("training_data.jsonl")

# ---------------------------------------------------------------------
# Language prompts — 14 Nigerian + 7 other African languages
# ---------------------------------------------------------------------

LANG_PROMPTS = {
    # Nigerian languages
    "yoruba": (
        "You are a Yoruba tutor from Lagos, Nigeria. Teach Yoruba simply, "
        "include pronunciation in square brackets, and always give an English "
        "translation. Keep lessons short and friendly."
    ),
    "igbo": (
        "You are an Igbo tutor from Enugu, Nigeria. Teach Igbo simply, include "
        "pronunciation, and always explain in English."
    ),
    "hausa": (
        "You are a Hausa tutor from Kano, Nigeria. Teach Hausa simply and "
        "always explain in English."
    ),
    "pidgin": (
        "You are a Nigerian Pidgin tutor from Lagos. Teach natural Nigerian "
        "Pidgin, explain usage, and give a standard English translation."
    ),
    "edo": (
        "You are an Edo (Bini) tutor from Benin City, Edo State, Nigeria. "
        "Teach Edo simply, include pronunciation, and explain in English."
    ),
    "ijaw": (
        "You are an Ijaw (Izon) tutor from the Niger Delta, Nigeria. Teach "
        "carefully, include pronunciation, and explain in English. Mention "
        "dialect variation when relevant."
    ),
    "efik": (
        "You are an Efik tutor from Calabar, Cross River State, Nigeria. "
        "Teach simply, include pronunciation, and explain in English."
    ),
    "etsakowest": (
        "You are an Etsakowest (Afenmai) tutor from Edo North, Nigeria. Teach "
        "simply, include pronunciation, and explain in English."
    ),
    "tiv": (
        "You are a Tiv tutor from Benue State, Nigeria. Teach simply, include "
        "pronunciation, and explain in English."
    ),
    "idoma": (
        "You are an Idoma tutor from Benue State, Nigeria. Teach simply, "
        "include pronunciation, and explain in English."
    ),
    "fulani": (
        "You are a Fulani/Fulfulde tutor. Teach clearly, include pronunciation, "
        "and explain in English. Mention regional variation when relevant."
    ),
    "urhobo": (
        "You are an Urhobo tutor from Delta State, Nigeria. Teach simply, "
        "include pronunciation, and explain in English."
    ),
    "ibibio": (
        "You are an Ibibio tutor from Akwa Ibom State, Nigeria. Teach simply, "
        "include pronunciation, and explain in English."
    ),
    "kanuri": (
        "You are a Kanuri tutor from Borno State, Nigeria. Teach simply, "
        "include pronunciation, and explain in English."
    ),

    # Other African languages
    "swahili": (
        "You are a Swahili tutor. Teach simply, include useful examples, "
        "and always explain in English."
    ),
    "twi": (
        "You are a Twi tutor from Ghana. Teach simply and always explain in English."
    ),
    "zulu": (
        "You are a Zulu tutor from South Africa. Teach simply, include "
        "pronunciation, and explain in English."
    ),
    "amharic": (
        "You are an Amharic tutor. Show the Amharic script, transliteration, "
        "pronunciation, and English meaning."
    ),
    "kinyarwanda": (
        "You are a Kinyarwanda tutor. Teach simply and always explain in English."
    ),
    "lingala": (
        "You are a Lingala tutor from the Congo region. Teach simply and "
        "always explain in English."
    ),
    "wolof": (
        "You are a Wolof tutor from Senegal. Teach simply and always explain in English."
    ),
}

# ---------------------------------------------------------------------
# Lightweight persistent bot state
# ---------------------------------------------------------------------

def load_data() -> dict:
    if not DATA_FILE.exists():
        return {"users": {}}
    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict):
            return {"users": {}}
        data.setdefault("users", {})
        return data
    except (OSError, json.JSONDecodeError):
        logger.exception("Could not read %s; starting with empty state.", DATA_FILE)
        return {"users": {}}


bot_data = load_data()


def save_data() -> None:
    temporary_file = DATA_FILE.with_suffix(".tmp")
    with temporary_file.open("w", encoding="utf-8") as file:
        json.dump(bot_data, file, ensure_ascii=False, indent=2)
    temporary_file.replace(DATA_FILE)


def get_user_record(user_id: int) -> dict:
    users = bot_data.setdefault("users", {})
    record = users.setdefault(
        str(user_id),
        {"language": "yoruba", "points": 0, "username": ""},
    )
    return record


# ---------------------------------------------------------------------
# Training data
# ---------------------------------------------------------------------

def save_training_data(
    prompt: str,
    completion: Optional[str],
    lang: str,
    user_id: int,
    record_type: str,
    contributor: str = "",
) -> None:
    data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "prompt": prompt,
        "completion": completion,
        "lang": lang,
        "user_id": user_id,
        "type": record_type,
        "contributor": contributor,
    }

    try:
        with TRAINING_FILE.open("a", encoding="utf-8") as file:
            file.write(json.dumps(data, ensure_ascii=False) + "\n")
    except OSError:
        logger.exception("Could not write local training data.")

    if supabase is not None:
        try:
            supabase.table("udi_training_data").insert(data).execute()
        except Exception:
            # Local JSONL logging still works if Supabase is unavailable.
            logger.exception("Could not save training data to Supabase.")


# ---------------------------------------------------------------------
# Telegram handlers
# ---------------------------------------------------------------------

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None:
        return

    language_lines = []
    names = list(LANG_PROMPTS)
    for index in range(0, len(names), 4):
        language_lines.append("  ".join(f"/{name}" for name in names[index:index + 4]))

    text = (
        "🌍 *UDI LINGO — African Languages* 🌍\n\n"
        "Learn African languages and help improve community language resources!\n\n"
        "*NIGERIAN LANGUAGES (14)*\n"
        "/yoruba /igbo /hausa /pidgin\n"
        "/edo /ijaw /efik /etsakowest\n"
        "/tiv /idoma /fulani\n"
        "/urhobo /ibibio /kanuri\n\n"
        "*OTHER AFRICAN LANGUAGES (7)*\n"
        "/swahili /twi /zulu /amharic\n"
        "/kinyarwanda /lingala /wolof\n\n"
        "*How to use*\n"
        "1. Choose a language command, for example /yoruba.\n"
        "2. Ask a question, for example: “How do you say good morning?”\n"
        "3. Use the buttons to confirm an answer or submit a correction.\n\n"
        "🏆 /leaderboard — Top contributors\n"
        "📊 /mystats — Your points and selected language"
    )
    await message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


async def set_lang(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not message.text:
        return

    command = message.text.split()[0].split("@")[0].lstrip("/").lower()
    if command not in LANG_PROMPTS:
        await message.reply_text("That language is not supported.")
        return

    record = get_user_record(user.id)
    record["language"] = command
    record["username"] = user.username or ""
    save_data()

    await message.reply_text(
        f"✅ Language set to {command.upper()}!\n"
        "Now ask me anything in English, or ask for a lesson."
    )


async def chat(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None or not message.text:
        return

    uid = user.id
    record = get_user_record(uid)
    lang = record.get("language", "yoruba")
    user_text = message.text.strip()

    # A correction is the next text message after the user presses "Wrong".
    if context.user_data.get("awaiting_correction"):
        correction = user_text
        original_question = context.user_data.get("last_question", "")
        original_answer = context.user_data.get("last_reply", "")

        save_training_data(
            prompt=original_question,
            completion=correction,
            lang=lang,
            user_id=uid,
            record_type="gold_correction",
            contributor=user.username or "",
        )

        record["points"] = int(record.get("points", 0)) + 10
        save_data()
        context.user_data["awaiting_correction"] = False

        await message.reply_text(
            "🌟 *Correction saved!* You earned 10 points.\n"
            f"Your total: {record['points']} points.\n\n"
            "Thank you for helping improve UDI LINGO! 🙏",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    save_training_data(
        prompt=user_text,
        completion=None,
        lang=lang,
        user_id=uid,
        record_type="raw",
        contributor=user.username or "",
    )

    system_prompt = LANG_PROMPTS.get(lang, LANG_PROMPTS["yoruba"])

    try:
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
        )
        reply = response.choices[0].message.content
        if not reply:
            reply = "I couldn't generate an answer. Please try again."

        context.user_data["last_reply"] = reply
        context.user_data["last_question"] = user_text

        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("✅ Correct", callback_data="ok"),
                InlineKeyboardButton("❌ Wrong — correct it", callback_data="fix"),
            ]]
        )

        # Plain text avoids Telegram Markdown parse errors from model output.
        await message.reply_text(reply, reply_markup=keyboard)

    except Exception:
        logger.exception("OpenAI request failed for user %s.", uid)
        await message.reply_text(
            "Sorry, I couldn't answer just now. Please try again in a moment."
        )


async def button_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    await query.answer()
    uid = query.from_user.id
    record = get_user_record(uid)

    if query.data == "ok":
        await query.edit_message_reply_markup(reply_markup=None)

        record["points"] = int(record.get("points", 0)) + 1
        save_data()

        save_training_data(
            prompt=context.user_data.get("last_question", ""),
            completion=context.user_data.get("last_reply", ""),
            lang=record.get("language", "yoruba"),
            user_id=uid,
            record_type="verified_good",
            contributor=query.from_user.username or "",
        )

        await query.message.reply_text(
            f"Thanks for confirming! 🙏 +1 point. Total: {record['points']}."
        )

    elif query.data == "fix":
        context.user_data["awaiting_correction"] = True
        await query.message.reply_text(
            "🙏 Please send your correction in this format:\n\n"
            "Correct: ...\n"
            "Pronunciation: ...\n"
            "Note: ...\n\n"
            "Example:\n"
            "Correct: Ẹ káàárọ̀\n"
            "Pronunciation: eh-kah-ah-roh\n"
            "Note: A morning greeting in Yoruba"
        )


async def leaderboard(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    if message is None:
        return

    users = bot_data.get("users", {})
    ranked = sorted(
        users.items(),
        key=lambda item: int(item[1].get("points", 0)),
        reverse=True,
    )[:10]

    if not ranked or all(int(data.get("points", 0)) == 0 for _, data in ranked):
        await message.reply_text(
            "🏆 No contributors yet. Be the first to earn points!"
        )
        return

    lines = ["🏆 *Top Contributors*\n"]
    for position, (user_id, data) in enumerate(ranked, start=1):
        username = data.get("username")
        display_name = f"@{username}" if username else f"User {user_id}"
        points = int(data.get("points", 0))
        lines.append(f"{position}. {display_name} — {points} pts")

    lines.append("\nCorrections: 10 points | Confirmed answers: 1 point")
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


async def mystats(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    message = update.effective_message
    user = update.effective_user
    if message is None or user is None:
        return

    record = get_user_record(user.id)
    language = record.get("language", "Not set")
    points = int(record.get("points", 0))

    await message.reply_text(
        "📊 *Your UDI LINGO Stats*\n\n"
        f"Language: {language.upper()}\n"
        f"Points: {points}\n\n"
        "Keep learning and contributing!",
        parse_mode=ParseMode.MARKDOWN,
    )


async def error_handler(
    update: object,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    logger.error(
        "Unhandled Telegram update error",
        exc_info=context.error,
    )


# ---------------------------------------------------------------------
# Startup
# ---------------------------------------------------------------------

def main() -> None:
    application = Application.builder().token(BOT_TOKEN).connect_timeout(30).read_timeout(30).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("leaderboard", leaderboard))
    application.add_handler(CommandHandler("mystats", mystats))

    for language in LANG_PROMPTS:
        application.add_handler(CommandHandler(language, set_lang))

    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, chat)
    )
    application.add_error_handler(error_handler)

    logger.info(
        "UDI LINGO started with %d languages. Supabase enabled: %s",
        len(LANG_PROMPTS),
        supabase is not None,
    )
  threading.Thread(target=run_flask, daemon=True).start()
  application.run_polling(drop_pending_updates=True,allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
