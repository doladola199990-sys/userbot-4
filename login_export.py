import asyncio, os
from pyrogram import Client

PHONE = os.environ["PROMO_PHONE"]
API_ID = int(os.environ["TG_API_ID"])
API_HASH = os.environ["TG_API_HASH"]

async def main():
    app = Client("userbot_promo1_login", api_id=API_ID, api_hash=API_HASH, in_memory=True)
    await app.connect()
    sent = await app.send_code(PHONE)
    print("OTP_SENT", flush=True)
    otp = input("OTP: ").strip()
    try:
        await app.sign_in(PHONE, sent.phone_code_hash, otp)
    except Exception as e:
        from pyrogram.errors import SessionPasswordNeeded
        if isinstance(e, SessionPasswordNeeded):
            password = input("2FA_PASSWORD: ").strip()
            await app.check_password(password)
        else:
            raise
    session = await app.export_session_string()
    open(os.path.expanduser("~/userbot-promo1/session_string.txt"), "w").write(session + "\n")
    os.chmod(os.path.expanduser("~/userbot-promo1/session_string.txt"), 0o600)
    print("SESSION_SAVED", flush=True)
    await app.disconnect()

asyncio.run(main())
