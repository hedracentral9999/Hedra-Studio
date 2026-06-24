#!/usr/bin/env python3
"""TTS Bot — input → Viral → 11labs → render ElevenLabs → trả audio"""
import logging, os, requests, tempfile
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, MessageHandler, CommandHandler, CallbackQueryHandler, filters, ContextTypes, Defaults

load_dotenv()
TOKEN = os.getenv("TELEGRAM_TOKEN")
DS_KEY = os.getenv("DEEPSEEK_API_KEY")
EL_KEY = os.getenv("ELEVENLABS_API_KEY")
VOICE_ID = os.getenv("VOICE_ID", "pNInz6obpgDQGcFmaJgB")  # Adam
EL_MODEL = os.getenv("ELEVENLABS_MODEL", "eleven_v3")

logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

BASE = os.path.dirname(__file__)
V = open(os.path.join(BASE, "docs", "tts", "viral.md"), "r", encoding="utf-8").read()
L = open(os.path.join(BASE, "docs", "tts", "11labs.md"), "r", encoding="utf-8").read()

# ── Cache giữa 2 step ──────────────────────────────────────
cache: dict[int, str] = {}  # chat_id → enhanced_text


def call_deepseek(text: str, prompt: str, temp: float = 0.4) -> str:
    r = requests.post("https://api.deepseek.com/chat/completions",
        headers={"Authorization": f"Bearer {DS_KEY}", "Content-Type": "application/json"},
        json={"model": "deepseek-v4-flash", "temperature": temp,
              "messages": [{"role": "system", "content": prompt}, {"role": "user", "content": text}]},
        timeout=90)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def call_elevenlabs(text: str) -> bytes:
    r = requests.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE_ID}",
        headers={"xi-api-key": EL_KEY, "Content-Type": "application/json"},
        json={"text": text, "model_id": EL_MODEL,
              "voice_settings": {"stability": 0.5, "similarity_boost": 0.75, "speed": 1.0}},
        timeout=120)
    r.raise_for_status()
    return r.content


# ── Handlers ────────────────────────────────────────────────

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 TTS Bot sẵn sàng!\n"
        "Gửi kịch bản → enhance → render audio.\n"
        "/help để xem hướng dẫn."
    )


async def on_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    cid = update.message.chat_id

    if not text or len(text) < 10:
        await update.message.reply_text("⚠️ Gửi kịch bản dài hơn nhé.")
        return

    if text.lower() in ("ok", "oke", "oki", "okay", "ok anh", "ok bạn", "render", "duyệt", "done"):
        # ── Render audio ──
        enhanced = cache.get(cid)
        if not enhanced:
            await update.message.reply_text("⚠️ Chưa có kịch bản đã enhance. Gửi kịch bản gốc trước.")
            return
        msg = await update.message.reply_text("🎙️ Đang render audio ElevenLabs...")
        try:
            audio = call_elevenlabs(enhanced)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio)
                fpath = f.name
            await msg.delete()
            await update.message.reply_voice(voice=open(fpath, "rb"))
            os.unlink(fpath)
        except Exception as e:
            await msg.edit_text(f"❌ Render lỗi: {e}")
        return

    # ── Enhance 2 bước ──
    msg = await update.message.reply_text("⏳ Step 1/2: Viral...")
    try:
        step1 = call_deepseek(text, V)
        await msg.edit_text("⏳ Step 2/2: 11labs...")
        step2 = call_deepseek(step1, L)
        cache[cid] = step2

        preview = step2
        if len(preview) > 3500:
            preview = preview[:3500] + "\n\n... (xem đủ trong file)"

        kb = InlineKeyboardMarkup([[
            InlineKeyboardButton("✅ Render audio", callback_data="render"),
            InlineKeyboardButton("❌ Hủy", callback_data="cancel"),
        ]])
        await msg.edit_text(f"📝 Kịch bản đã enhance:\n\n{preview}", reply_markup=kb)
    except Exception as e:
        await msg.edit_text(f"❌ Enhance lỗi: {e}")


async def on_button(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cid = query.message.chat_id
    await query.answer()

    if query.data == "cancel":
        cache.pop(cid, None)
        await query.edit_message_text("❌ Đã hủy.")
        return

    if query.data == "render":
        enhanced = cache.pop(cid, None)
        if not enhanced:
            await query.edit_message_text("⚠️ Hết hạn. Gửi lại kịch bản nhé.")
            return
        await query.edit_message_text("🎙️ Đang render audio ElevenLabs...")
        try:
            audio = call_elevenlabs(enhanced)
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                f.write(audio)
                fpath = f.name
            await query.message.reply_voice(voice=open(fpath, "rb"),
                caption="✅ Done! → /start để làm kịch bản mới")
            os.unlink(fpath)
            await query.message.delete()
        except Exception as e:
            await query.edit_message_text(f"❌ Render lỗi: {e}")


# ── Main ───────────────────────────────────────────────────
def main():
    app = Application.builder().token(TOKEN).defaults(Defaults(block=False)).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_handler(CallbackQueryHandler(on_button))
    logging.info("🤖 TTS Bot running — gửi kịch bản để bắt đầu")
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
