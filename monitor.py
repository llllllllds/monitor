import asyncio
import re
import requests
from telethon import TelegramClient

# === Настройки ===
API_ID = 21610900
API_HASH = "ad608e8630bdba3a4e4b5ff3d929c476"
BOT_TOKEN = "7539175415:AAECIfHrar6SEygyx9hBhQd087kNgTm1TeA"
TARGET_CHAT_ID = -1002383425682

CHANNELS = {
    "plasma": "https://t.me/PLASMA_ALERTS",
    "solana": "https://t.me/PumpFunNewPools",
    "trx": "https://t.me/SunPumpNewDeploys",
    "bsc": "https://t.me/FourMemeNewTokens"
}

client = TelegramClient("userbot_session", API_ID, API_HASH)
sent_messages = {}  # key = "<tag>:<ticker>" -> {"message_id":..., "count":...}

def send_or_update_message(tag: str, display_name: str, count: int, twitter_url=None, telegram_url=None):
    """Отправка нового сообщения или обновление существующего"""
    key = f"{tag}:{display_name.lower()}"
    text = f"⚡ [{tag.upper()}] Найден повтор!\n🪙 {display_name} — встречается {count} раза(ов)\n"

    if tag != "plasma":
        text += f"🐦 Twitter: {twitter_url or 'Not available'}\n📱 Telegram: {telegram_url or 'Not available'}"
    else:
        text += f"🐦 Twitter: {twitter_url or 'Not available'}"

    if key in sent_messages:
        # Обновляем существующее сообщение
        old = sent_messages[key]
        if count != old["count"]:
            resp = requests.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/editMessageText",
                json={"chat_id": TARGET_CHAT_ID, "message_id": old["message_id"], "text": text}
            )
            if resp.status_code == 200:
                sent_messages[key]["count"] = count
                print(f"✏️ Обновлено: {display_name} ({tag}) | Количество: {count}" + (f" | Twitter: {twitter_url}" if tag == "plasma" and twitter_url else ""))
    else:
        # Отправляем новое сообщение
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
            json={"chat_id": TARGET_CHAT_ID, "text": text}
        )
        if resp.status_code == 200:
            data = resp.json()
            sent_messages[key] = {"message_id": data["result"]["message_id"], "count": count}
            print(f"📤 Отправлено: {display_name} ({tag}) | Количество: {count}" + (f" | Twitter: {twitter_url}" if tag == "plasma" and twitter_url else ""))

def parse_plasma_message(msg):
    """
    Парсинг сообщений из канала Plasma.
    Возвращает: (symbol, twitter_url, telegram_url)
    """
    text = (getattr(msg, "message", None) or getattr(msg, "raw_text", None) or "")
    
    # Ищем Symbol
    sym_m = re.search(r"Symbol\s*:\s*(\S+)", text, re.IGNORECASE)
    symbol = sym_m.group(1).strip() if sym_m else None

    twitter_url = None

    # Проверяем кнопки (msg.buttons)
    if hasattr(msg, "buttons") and msg.buttons:
        try:
            for row in msg.buttons:
                for button in row:
                    btn_url = getattr(button, "url", None)
                    if btn_url and ("x.com" in btn_url or "twitter.com" in btn_url):
                        twitter_url = btn_url
                        break
                if twitter_url:
                    break
        except:
            pass

    # Fallback: проверяем reply_markup
    if not twitter_url and hasattr(msg, "reply_markup") and getattr(msg.reply_markup, "rows", None):
        try:
            for row in msg.reply_markup.rows:
                for b in getattr(row, "buttons", []):
                    btn_url = getattr(b, "url", None)
                    if btn_url and ("x.com" in btn_url or "twitter.com" in btn_url):
                        twitter_url = btn_url
                        break
                if twitter_url:
                    break
        except:
            pass

    # Последний fallback: ищем ссылку в тексте
    if not twitter_url:
        m = re.search(r"https?://(?:x\.com|twitter\.com)/[^\s)]+", text, re.IGNORECASE)
        if m:
            twitter_url = m.group(0)

    return symbol, twitter_url, None

def parse_solana_message(msg):
    """Парсинг сообщений из канала Solana"""
    try:
        txt = (getattr(msg, "message", None) or getattr(msg, "raw_text", None) or "")
        lines = txt.splitlines()
        if len(lines) >= 10:
            line = lines[9]
            token = line.split("|")[0].strip() if "|" in line else None
            if token:
                twitter = next((l.split(":",1)[1].strip() for l in lines if "Twitter" in l), None)
                telegram = next((l.split(":",1)[1].strip() for l in lines if "Telegram" in l), None)
                return token, twitter, telegram
    except Exception:
        pass
    return None, None, None

def parse_trx_message(msg):
    """Парсинг сообщений из канала TRX"""
    try:
        txt = (getattr(msg, "message", None) or getattr(msg, "raw_text", None) or "")
        lines = txt.splitlines()
        if lines:
            parts = lines[0].split()
            token = parts[1] if len(parts) > 1 else None
            if token:
                twitter = next((l.split(":",1)[1].strip() for l in lines if "Twitter" in l), None)
                telegram = next((l.split(":",1)[1].strip() for l in lines if "Telegram" in l), None)
                return token, twitter, telegram
    except Exception:
        pass
    return None, None, None

def parse_bsc_message(msg):
    """Парсинг сообщений из канала BSC"""
    return parse_trx_message(msg)

# Словарь парсеров для каждого типа канала
PARSERS = {
    "plasma": parse_plasma_message,
    "solana": parse_solana_message,
    "trx": parse_trx_message,
    "bsc": parse_bsc_message
}

async def monitor_channel(tag, url):
    """Мониторинг одного канала и поиск повторяющихся токенов"""
    try:
        channel = await client.get_entity(url)
    except Exception as e:
        print(f"[!] Не удалось получить канал {url}: {e}")
        return

    # Получаем последние 40 сообщений
    messages = await client.get_messages(channel, limit=40)
    counts = {}
    details = {}

    # Парсим каждое сообщение
    for msg in messages:
        token, twitter, telegram = PARSERS[tag](msg)
        if token:
            token_norm = token.lower().strip()
            counts[token_norm] = counts.get(token_norm, 0) + 1
            # Сохраняем данные первого найденного токена
            if token_norm not in details:
                details[token_norm] = (token, twitter, telegram)

    # Отправляем уведомления о токенах, которые встречаются >= 2 раз
    for token_norm, count in counts.items():
        if count >= 2:
            token, twitter, telegram = details[token_norm]
            send_or_update_message(tag, token, count, twitter, telegram)

async def main():
    """Главная функция - запуск бота и постоянный мониторинг"""
    await client.start()
    print("✅ Userbot авторизован. Проверка каналов каждые 10 секунд...")
    
    while True:
        for tag, url in CHANNELS.items():
            try:
                await monitor_channel(tag, url)
            except Exception as e:
                print(f"[❌] Ошибка при проверке {tag}: {e}")
        await asyncio.sleep(10)

if __name__ == "__main__":
    asyncio.run(main())
