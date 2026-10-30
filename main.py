import os
import json
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from openai import OpenAI

BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_KEY = os.getenv("OPENAI_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

client = OpenAI(api_key=OPENAI_KEY)

try:
from supabase import create_client
supabase = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL else None
except:
supabase = None

# --- 21 LANGUAGES ---
LANG_PROMPTS = {
# MAJOR NIGERIAN
"yoruba": "You are a Yoruba tutor from Lagos, Nigeria. Teach Yoruba simply with pronunciation [in brackets]. Always give English translation. Short, friendly.",
"igbo": "You are an Igbo tutor from Enugu, Nigeria. Teach Igbo simply with pronunciation. Always English.",
"hausa": "You are a Hausa tutor from Kano, Nigeria. Teach Hausa simply. Always English.",
"pidgin": "You are a Nigerian Pidgin tutor from Lagos. Teach Pidgin with correct street usage. Fun, give standard English translation.",
"edo": "You are an Edo (Bini) tutor from Benin City, Edo State. Language of Benin Kingdom. Teach Edo simply with pronunciation. Always English.",
"ijaw": "You are an Ijaw (Izon) tutor from Bayelsa, Niger Delta. Teach Ijaw from Bayelsa/Delta/Rivers with pronunciation. Always English.",
"efik": "You are an Efik tutor from Calabar, Cross River. Teach Efik simply with pronunciation. Always English.",
"etsakowest": "You are an Etsako (Afenmai) tutor from Auchi, Etsako West, Edo North. Teach Etsako West simply with pronunciation. Always English.",
"tiv": "You are a Tiv tutor from Makurdi, Benue State, Middle Belt. Teach Tiv simply with pronunciation. Always English.",
"idoma": "You are an Idoma tutor from Otukpa, Benue State. Teach Idoma simply with pronunciation. Always English.",
"fulani": "You are a Fulani/Fulfulde tutor, spoken across Northern Nigeria. Also called Fula/Pulaar. Teach Fulani simply with pronunciation. Always English.",
"urhobo": "You are an Urhobo tutor from Warri, Delta State. Teach Urhobo simply with pronunciation. Always English.",
"ibibio": "You are an Ibibio tutor from Uyo, Akwa Ibom. Teach Ibibio simply with pronunciation. Always English.",
"kanuri": "You are a Kanuri tutor from Maiduguri, Borno State. Teach Kanuri simply with pronunciation. Always English.",
# PAN-AFRICAN
"swahili": "You are a Swahili tutor from Nairobi, Kenya. Teach Swahili simply. Always English.",
"twi": "You are a Twi tutor from Kumasi, Ghana, Ashanti. Teach Twi simply. Always English.",
"zulu": "You are a Zulu tutor from Durban, South Africa. Teach Zulu with pronunciation. Always English.",
"amharic": "You are an Amharic tutor from Addis Ababa, Ethiopia. Show Amharic script + transliteration + pronunciation. Always English.",
"kinyarwanda": "You are a Kinyarwanda tutor from Kigali, Rwanda. Teach Kinyarwanda simply. Always English.",
"lingala": "You are a Lingala tutor from Kinshasa, Congo. Teach Lingala simply. Always English.",
"wolof": "You are a Wolof tutor from Dakar, Senegal. Teach Wolof simply. Always English."
}

user_lang = {}
user_points = {}

def save_training_data(prompt, completion, lang, user_id, type, contributor=""):
data = {
"timestamp": datetime.now().isoformat(),
"prompt": prompt,
"completion": completion,
"lang": lang,
"user_id": user_id,
"type": type,
"contributor": contributor
}
try:
with open("training_data.jsonl", "a", encoding="utf-8") as f:
f.write(json.dumps(data, ensure_ascii=False) + "\n")
except: pass
if supabase:
try:
supabase.table("udi_training_data").insert(data).execute()
except: pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
await update.message.reply_text(
"🌍 *UDI LINGO - African Languages | Community Trained* 🌍\n\n"
"Learn African Languages + Help Train AI!\n\n"
"*NIGERIA (14):*\n"
"/yoruba /igbo /hausa /pidgin\n"
"/edo /ijaw /efik /etsakowest\n"
"/tiv /idoma /fulani\n"
"/urhobo /ibibio /kanuri\n\n"
"*AFRICA (7):*\n"
"/swahili 🇰🇪 /twi 🇬🇭 /zulu 🇿🇦\n"
"/amharic 🇪🇹 /kinyarwanda 🇷🇼\n"
"/lingala 🇨🇩 /wolof 🇸🇳\n\n"
"How to use:\n"
"1. Pick language e.g /edo\n"
"2. Ask: 'How do you say Good Morning?'\n\n"
"🏆 *Fluent?* If bot is wrong, click ❌ and correct it. Earn points!\n"
"/leaderboard - Top contributors\n"
"/mystats - Your points",
parse_mode="Markdown"
)

async def set_lang(update: Update, context: ContextTypes.DEFAULT_TYPE):
lang = update.message.text.replace("/", "").split()[0].lower().split("@")[0]
if lang not in LANG_PROMPTS:
return
user_lang[update.effective_user.id] = lang
await update.message.reply_text(f"✅ Set to *{lang.upper()}*! Now ask me anything.\nTry: 'Teach me numbers 1-10' or 'How to greet an elder?'", parse_mode="Markdown")

async def chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
uid = update.effective_user.id
lang = user_lang.get(uid, "yoruba")
user_text = update.message.text

if context.user_data.get("awaiting_correction"):
# This message is actually a correction, not a new question
correction = user_text
original_q = context.user_data.get("last_question", "")
save_training_data(original_q, correction, lang, uid, "gold_correction", contributor=str(update.effective_user.username))
user_points[uid] = user_points.get(uid, 0) + 10
await update.message.reply_text(
f"🌟 *GOLD Correction Saved!* +10 points\n"
f"Total: {user_points[uid]} pts\n\n"
f"Your correction will train our own Udi Lingo Model! Thank you elder 🙏",
parse_mode="Markdown"
)
context.user_data["awaiting_correction"] = False
return

save_training_data(user_text, None, lang, uid, "raw")
prompt = LANG_PROMPTS.get(lang, LANG_PROMPTS["yoruba"])

try:
response = client.chat.completions.create(
model="gpt-4o-mini",
messages=[
{"role": "system", "content": prompt},
{"role": "user", "content": user_text}
]
)
reply = response.choices[0].message.content
context.user_data["last_reply"] = reply
context.user_data["last_question"] = user_text

keyboard = [
[InlineKeyboardButton("✅ Correct", callback_data="ok"),
InlineKeyboardButton("❌ Wrong, I will correct", callback_data="fix")]
]
markup = InlineKeyboardMarkup(keyboard)
await update.message.reply_text(reply, reply_markup=markup, parse_mode="Markdown")
except Exception as e:
await update.message.reply_text(f"Small error, try again: {e}")

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
query = update.callback_query
await query.answer()
action = query.data
uid = query.from_user.id

if action == "ok":
await query.edit_message_reply_markup(reply_markup=None)
user_points[uid] = user_points.get(uid, 0) + 1
await query.message.reply_text(f"Thanks! 🙏 +1 point. Total: {user_points[uid]}")
save_training_data(context.user_data.get("last_question",""), context.user_data.get("last_reply",""), user_lang.get(uid,"yoruba"), uid, "verified_good")

if action == "fix":
context.user_data["awaiting_correction"] = True
await query.message.reply_text(
"🙏 *Elder, correct us!* Send in this format:\n\n"
"Correct: ...\n"
"Pronunciation: ...\n"
"Note: ...\n\n"
"Example:\nCorrect: E kaaro o\nPronunciation: eh-kah-roh oh\nNote: For elders in morning",
parse_mode="Markdown"
)

async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
if not user_points:
await update.message.reply_text("No contributors yet. Be the first to correct! 🏆")
return
sorted_users = sorted(user_points.items(), key=lambda x: x[1], reverse=True)[:10]
text = "🏆 *Top Contributors - Future Model Trainers*\n\n"
for i, (uid, pts) in enumerate(sorted_users, 1):
text += f"{i}. User {uid} - {pts} pts\n"
text += "\nGold corrections = 10pts, Verified = 1pt"
await update.message.reply_text(text, parse_mode="Markdown")

async def mystats(update: Update, context: ContextTypes.DEFAULT_TYPE):
uid = update.effective_user.id
pts = user_points.get(uid, 0)
lang = user_lang.get(uid, "Not set")
await update.message.reply_text(f"📊 *Your Stats*\n\nLanguage: {lang}\nPoints: {pts}\n\nKeep correcting to earn more!", parse_mode="Markdown")

def main():
app = Application.builder().token(BOT_TOKEN).build()
for lang in LANG_PROMPTS.keys():
app.add_handler(CommandHandler(lang, set_lang))
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("leaderboard", leaderboard))
app.add_handler(CommandHandler("mystats", mystats))
app.add_handler(CallbackQueryHandler(button_handler))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, chat))
print(f"UDI LINGO {len(LANG_PROMPTS)} Languages LIVE - Community Training ON")
app.run_polling()

if __name__ == "__main__":
main()
