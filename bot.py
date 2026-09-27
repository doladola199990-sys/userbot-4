import asyncio
import json
import os
import random
import gc
import re
from datetime import datetime
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.errors import FloodWait, SlowmodeWait, UserAlreadyParticipant
from pyrogram.types import Message


# ════════════════════════════════════════════════════════════════
# ANTI-CRASH PATCH: Pyrogram Peer ID Invalid + Handle Updates
# Mencegah bot freeze/mati saat menerima update dari channel/grup
# yang belum ter-cache di session SQLite lokal
# ════════════════════════════════════════════════════════════════
import pyrogram.methods.advanced.resolve_peer as _rp_mod
_orig_resolve = _rp_mod.ResolvePeer.resolve_peer

async def _safe_resolve_peer(self, peer_id):
    try:
        return await _orig_resolve(self, peer_id)
    except (ValueError, KeyError):
        return None
    except Exception:
        return None

_rp_mod.ResolvePeer.resolve_peer = _safe_resolve_peer

from pyrogram import Client as _PyroCli
_orig_handle = _PyroCli.handle_updates

async def _safe_handle_updates(self, updates):
    try:
        await _orig_handle(self, updates)
    except (ValueError, KeyError) as _e:
        if "Peer id invalid" in str(_e) or "ID not found" in str(_e):
            pass  # abaikan peer tak dikenal
        else:
            print(f"[handle_updates] {type(_e).__name__}: {_e}", flush=True)
    except Exception as _e:
        print(f"[handle_updates] {type(_e).__name__}: {_e}", flush=True)

_PyroCli.handle_updates = _safe_handle_updates
# ════════════════════════════════════════════════════════════════
WORKDIR = Path(__file__).resolve().parent
GROUPS_FILE = WORKDIR / "groups.json"
TEMPLATES_FILE = WORKDIR / "templates.json"
AUTOROTATE_FILE = WORKDIR / "autorotate.json"
SESSION_FILE = WORKDIR / "session_string.txt"

API_ID = int(os.environ.get("TG_API_ID", "0"))
API_HASH = os.environ.get("TG_API_HASH", "")
SESSION_STRING = os.environ.get("SESSION_STRING", "") or (SESSION_FILE.read_text().strip() if SESSION_FILE.exists() else "")
BOT_LABEL = os.environ.get("BOT_LABEL", "USERBOT PROMO")

if not API_ID or not API_HASH or not SESSION_STRING:
    raise RuntimeError("Set TG_API_ID/TG_API_HASH and create session_string.txt for the separate Telegram account")

app = Client("userbot_4", api_id=API_ID, api_hash=API_HASH, session_string=SESSION_STRING)
ADMIN_ID = None
URL_RE = re.compile(r"https?://t\.me/(?:joinchat/|\+)?[A-Za-z0-9_+\-/]+")


def read_json(path, fallback):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def write_json(path, data):
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def groups():
    return read_json(GROUPS_FILE, [])


def templates():
    return read_json(TEMPLATES_FILE, {})


def autorotate_config():
    base = {"enabled": False, "interval": 3600, "delay_seconds": 5, "target": "all", "report": True, "template_index": 0, "batch_index": 0}
    base.update(read_json(AUTOROTATE_FILE, {}))
    return base


def save_autorotate(data):
    write_json(AUTOROTATE_FILE, data)


def parse_interval(value):
    value = value.strip().lower()
    m = re.fullmatch(r"(\d+)([smhd]?)", value)
    if not m:
        return None
    n, unit = int(m.group(1)), m.group(2) or "s"
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def fmt(seconds):
    seconds = int(seconds)
    if seconds % 86400 == 0: return f"{seconds // 86400}h"
    if seconds % 3600 == 0: return f"{seconds // 3600}j"
    if seconds % 60 == 0: return f"{seconds // 60}m"
    return f"{seconds}dtk"


@app.on_message(filters.private & filters.command("start"))
async def start_cmd(_, m: Message):
    global ADMIN_ID
    ADMIN_ID = m.from_user.id
    await m.reply(f"**{BOT_LABEL}**\n\nKirim link grup `t.me` ke chat ini untuk auto-join.\n\n**Template**\n`/template tambah nama isi pesan`\n`/template daftar`\n`/template hapus nama`\n\n**Autorotate**\n`/autorotate on|off|status`\n`/autorotate delay <detik>`\n`/autorotate interval <5m|1h|angka detik>`\n`/autorotate target all|batch`\n`/autorotate report on|off`\n\n`/groups`\n`/remove nomor` → hapus target dari daftar\n`/stats`")


@app.on_message(filters.private & filters.command("template"))
async def template_cmd(_, m: Message):
    parts = (m.text or "").split(maxsplit=3)
    data = templates()
    if len(parts) == 1 or (len(parts) > 1 and parts[1] == "daftar"):
        if not data:
            return await m.reply("📭 Belum ada template.")
        return await m.reply("**📝 Template**\n" + "\n".join(f"• `{name}`" for name in data))
    action = parts[1].lower()
    if action == "tambah":
        if len(parts) < 4 or not parts[2].strip() or not parts[3].strip():
            return await m.reply("Cara: `/template tambah nama isi pesan`")
        data[parts[2].strip()] = parts[3].strip()
        write_json(TEMPLATES_FILE, data)
        return await m.reply(f"✅ Template `{parts[2].strip()}` disimpan.")
    if action == "hapus":
        if len(parts) < 3 or not parts[2].strip():
            return await m.reply("Cara: `/template hapus nama_template`")
        name = parts[2].strip()
        if name not in data:
            return await m.reply(f"❌ Template `{name}` tidak ditemukan.")
        del data[name]
        write_json(TEMPLATES_FILE, data)
        return await m.reply(f"🗑 Template `{name}` dihapus.")
    await m.reply("Cara: `/template tambah nama isi pesan`, `/template daftar`, atau `/template hapus nama`")


@app.on_message(filters.private & filters.command("autorotate"))
async def autorotate_cmd(_, m: Message):
    global ADMIN_ID
    ADMIN_ID = m.from_user.id
    args = (m.text or "").split()
    data = autorotate_config()
    if len(args) < 2 or args[1].lower() in ("status", "help", "bantuan"):
        return await m.reply(
            f"**🔄 AUTOROTATE**\n\n"
            f"Status: **{'ON' if data['enabled'] else 'OFF'}**\n"
            f"Interval putaran: **{fmt(data['interval'])}**\n"
            f"Jeda antar grup: **{data['delay_seconds']} detik**\n"
            f"Target: **{data['target']}**\n"
            f"Laporan: **{'ON' if data['report'] else 'OFF'}**\n\n"
            "**CARA PAKAI**\n"
            "• Aktifkan: `/autorotate on`\n"
            "• Matikan: `/autorotate off`\n"
            "• Lihat status: `/autorotate status`\n"
            "• Ubah jeda antar grup: `/autorotate delay 5`\n"
            "• Ubah interval putaran: `/autorotate interval 5m`\n"
            "• Target semua grup: `/autorotate target all`\n"
            "• Target bergantian batch: `/autorotate target batch`\n"
            "• Laporan on/off: `/autorotate report on`\n\n"
            "**CONTOH**\n"
            "`/autorotate delay 5` = kirim ke grup berikutnya setelah 5 detik\n"
            "`/autorotate interval 10m` = putaran berikutnya mulai 10 menit lagi"
        )
    cmd = args[1].lower()
    if cmd in ("on", "off"):
        data["enabled"] = cmd == "on"; save_autorotate(data)
        return await m.reply(f"✅ Autorotate **{'aktif' if data['enabled'] else 'nonaktif'}**.")
    if cmd == "delay" and len(args) == 3 and args[2].isdigit():
        data["delay_seconds"] = int(args[2]); save_autorotate(data)
        return await m.reply(f"✅ Jeda: **{data['delay_seconds']} detik**.")
    if cmd == "interval" and len(args) == 3:
        val = parse_interval(args[2])
        if val is None: return await m.reply("❌ Interval tidak valid. Contoh: `/autorotate interval 5m`, `/autorotate interval 1h`, atau `/autorotate interval 30`")
        data["interval"] = val; save_autorotate(data)
        return await m.reply(f"✅ Interval: **{fmt(val)}**.")
    if cmd == "target" and len(args) == 3 and args[2].lower() in ("all", "batch"):
        data["target"] = args[2].lower(); save_autorotate(data)
        return await m.reply(f"✅ Target: **{data['target']}**.")
    if cmd == "report" and len(args) == 3 and args[2].lower() in ("on", "off"):
        data["report"] = args[2].lower() == "on"; save_autorotate(data)
        return await m.reply(f"✅ Report: **{'ON' if data['report'] else 'OFF'}**.")
    await m.reply(
        "❌ Perintah autorotate tidak dikenali.\n\n"
        "Untuk ubah jeda gunakan: `/autorotate delay 5`\n"
        "Untuk ubah interval gunakan: `/autorotate interval 5m`\n"
        "Ketik `/autorotate status` untuk bantuan lengkap."
    )


@app.on_message(filters.private & filters.command("groups"))
async def groups_cmd(_, m: Message):
    data = groups()
    if not data:
        await m.reply("📭 Belum ada grup tersimpan.")
        return
    lines = [f"**📋 Daftar Grup ({len(data)})**"]
    for i, group in enumerate(data, 1):
        title = group.get("title") or "Tanpa nama"
        chat_id = group.get("id", "-")
        link = group.get("link", "-")
        lines.append(f"{i}. **{title}**\n   ID: `{chat_id}`\n   Link: {link}")
    text = "\n".join(lines)
    # Telegram message limit safety: split long group lists.
    for offset in range(0, len(text), 3500):
        await m.reply(text[offset:offset + 3500])


@app.on_message(filters.private & filters.command("remove"))
async def remove_group_cmd(_, m: Message):
    parts = (m.text or "").split(maxsplit=1)
    if len(parts) != 2 or not parts[1].strip().isdigit():
        return await m.reply("Cara: `/remove nomor`\n\nLihat nomor grup dengan `/groups`.")

    index = int(parts[1].strip()) - 1
    current = groups()
    if index < 0 or index >= len(current):
        return await m.reply(f"❌ Nomor grup tidak ditemukan. Total grup saat ini: {len(current)}.")

    removed = current.pop(index)
    write_json(GROUPS_FILE, current)
    await m.reply(
        f"🗑 Grup dihapus dari daftar target:\n"
        f"**{removed.get('title') or 'Tanpa nama'}**\n\n"
        f"📁 Sisa grup: {len(current)}\n"
        f"_Akun tetap menjadi anggota grup Telegram; yang dihapus hanya target autorotate._"
    )


@app.on_message(filters.private & filters.command("stats"))
async def stats_cmd(_, m: Message):
    await m.reply(f"**📊 {BOT_LABEL} Stats**\nGrup: **{len(groups())}**\nTemplate: **{len(templates())}**\nAutorotate: **{'ON' if autorotate_config()['enabled'] else 'OFF'}**")


@app.on_message(filters.private & filters.text & ~filters.command(["start", "template", "autorotate", "stats"]))
async def auto_join(_, m: Message):
    links = URL_RE.findall(m.text or "")
    if not links: return
    current = groups()
    replies = []
    for link in links:
        try:
            target = link if ("/joinchat/" in link or "/+" in link) else link.rstrip("/").split("/")[-1]
            chat = await app.join_chat(target)
            if not any(g["id"] == chat.id for g in current):
                current.append({"id": chat.id, "title": chat.title or str(chat.id), "link": link, "added_at": datetime.now().isoformat()})
                write_json(GROUPS_FILE, current)
            replies.append(f"✅ {chat.title}")
        except UserAlreadyParticipant:
            try:
                target = link if ("/joinchat/" in link or "/+" in link) else link.rstrip("/").split("/")[-1]
                chat = await app.get_chat(target)
                if not any(g.get("id") == chat.id for g in current):
                    current.append({"id": chat.id, "title": chat.title or str(chat.id), "link": link, "added_at": datetime.now().isoformat()})
                    write_json(GROUPS_FILE, current)
                    replies.append(f"✅ Sudah join, disimpan: {chat.title or str(chat.id)}")
                else:
                    replies.append(f"✅ Sudah join: {chat.title or str(chat.id)}")
            except Exception as e:
                replies.append(f"❌ Gagal menyimpan {link}: {type(e).__name__}")
        except FloodWait as e:
            replies.append(f"⏳ FloodWait {e.value} detik: {link}")
        except Exception as e:
            replies.append(f"❌ Gagal {link}: {type(e).__name__}")
    await m.reply("\n".join(replies))


async def autorotate_worker():
    await asyncio.sleep(15)
    while True:
        try:
            cfg, gs, ts = autorotate_config(), groups(), templates()
            if not cfg["enabled"] or not gs or not ts:
                await asyncio.sleep(10); continue
            values = list(ts.items())
            name, text = values[int(cfg["template_index"]) % len(values)]
            batches = [gs] if cfg["target"] == "all" else [gs[:max(1, len(gs)//2)], gs[max(1, len(gs)//2):]]
            batch = batches[int(cfg["batch_index"]) % len(batches)]
            sent, failed = 0, 0
            details = []
            for group in list(batch):
                try:
                    target = group["id"]
                    try:
                        await app.send_message(target, text)
                    except (ValueError, KeyError):
                        # Peer ID invalid — fallback ke username dari link
                        link = group.get("link", "")
                        uname = link.rstrip("/").split("/")[-1] if link else None
                        if uname and not uname.startswith("+"):
                            await app.send_message(uname, text)
                        else:
                            raise
                    sent += 1
                    details.append(f"✅ {group.get('title', group.get('id'))}")
                    print(f"[autorotate] BERHASIL kirim ke: {group.get('title', group.get('id'))}", flush=True)
                    await asyncio.sleep(max(0, float(cfg["delay_seconds"])) + random.uniform(0, 1))
                except (FloodWait, SlowmodeWait) as e:
                    if e.value > 30:
                        # Slowmode/FloodWait terlalu lama — skip grup ini, lanjut ke berikutnya
                        failed += 1
                        details.append(f"⏭️ {group.get('title', group.get('id'))}: SKIP (wait {e.value}s terlalu lama)")
                        print(f"[autorotate] {group.get('id')}: SKIP FloodWait {e.value}s", flush=True)
                    else:
                        # Wait pendek (<=30s) — tunggu sebentar lalu lanjut
                        await asyncio.sleep(e.value)
                        try:
                            target = group["id"]
                            await app.send_message(target, text)
                            sent += 1
                            details.append(f"✅ {group.get('title', group.get('id'))} (after wait {e.value}s)")
                        except Exception:
                            failed += 1
                            details.append(f"⏳ {group.get('title', group.get('id'))}: FloodWait {e.value}s retry gagal")
                except Exception as e:
                    failed += 1
                    reason = f"{type(e).__name__}: {str(e).replace(chr(10), ' ')[:100]}"
                    details.append(f"❌ {group.get('title', group.get('id'))}: {reason}")
                    print(f"[autorotate] {group.get('id')}: {reason}", flush=True)
            cfg["template_index"] = (int(cfg["template_index"]) + 1) % len(values)
            cfg["batch_index"] = (int(cfg["batch_index"]) + 1) % len(batches)
            save_autorotate(cfg)
            if cfg["report"] and ADMIN_ID:
                report = f"🔄 Autorotate selesai\nTemplate: `{name}`\n✅ {sent} | ❌ {failed}\nPutaran berikutnya: {fmt(cfg['interval'])}\n\n" + "\n".join(details)
                for offset in range(0, len(report), 3500):
                    await app.send_message(ADMIN_ID, report[offset:offset + 3500])
            # Memory cleanup: release broadcast data
            del details
            gc.collect()
            await asyncio.sleep(max(0, float(cfg["interval"])))
        except Exception as e:
            print(f"[autorotate] {type(e).__name__}: {e}", flush=True)
            await asyncio.sleep(15)


loop = asyncio.get_event_loop()

# Anti-crash: tangani uncaught asyncio exception (Peer id invalid, dsb)
def _handle_loop_exception(loop, context):
    msg = str(context.get("exception", context.get("message", "")))
    if "Peer id invalid" in msg or "ID not found" in msg:
        return
    print(f"[Unhandled AsyncIO] {msg}", flush=True)

loop.set_exception_handler(_handle_loop_exception)
loop.create_task(autorotate_worker())
app.run()
