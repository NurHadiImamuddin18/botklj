import time
import requests
import schedule
import os
import logging
from datetime import datetime, timezone, timedelta
from playwright.sync_api import sync_playwright
import threading
import json
import subprocess
import requests
import logging

TELEGRAM_BOT_TOKEN = "8438813402:AAHx98XuJj7zBWO-AP1B_xzp19a8oCpUKs8"
TELEGRAM_CHAT_IDS = ["-1002755104290","-1001714188559","-1002033158680"]

# === Mapping caption -> target chat_id ===
GROUP_TARGETS = {
    # WO DAN QC2 KLJ + MAGANG KLJ
    "DASHBOARD PROVISIONING TSEL @rolimartin @JackSpaarroww @firdausmulia @YantiMohadi @b1yant @Yna_as @chukong": ["-1002755104290", "-1001714188559"],
    "Produktifitas Teknisi PSB Klojen": ["-1002755104290", "-1001714188559"],

    # LAPHAR KLOJEN + MAGANG KLJ
    "unspec B2C Klojen @rolimartin @JackSpaarroww @firdausmulia @YantiMohadi @b1yant @Yna_as @chukong": ["-1002033158680", "-1001714188559"],
    "KLOJEN - UNSPEC (KLIRING)": ["-1002033158680", "-1001714188559"],

    # Hanya ke MAGANG KLJ
    "Unspec B2B Klojen": ["-1001714188559"],
    "Detail Order PSB Klojen": ["-1001714188559"],
}

# === Fungsi kirim screenshot ke grup sesuai caption ===
def send_screenshot_to_telegram(file_path, caption):
    # Ambil target group sesuai caption
    target_groups = GROUP_TARGETS.get(caption, [])
    if not target_groups:
        logging.warning(f"⚠️ Caption {caption} tidak ada di GROUP_TARGETS, tidak ada grup tujuan.")
        return

    for chat_id in target_groups:
        try:
            with open(file_path, "rb") as f:
                url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
                requests.post(
                    url,
                    data={"chat_id": chat_id, "caption": caption},
                    files={"photo": f}
                )
                logging.info(f"✅ Screenshot {file_path} terkirim ke {chat_id} ({caption})")
        except Exception as e:
            logging.error(f"❌ Gagal kirim {file_path} ke {chat_id}: {e}")


API_URL = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

# --- Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

is_running = False

schedules_data = {
    "02:59": {"active": True, "id": "schedule_1"},
    "05:59": {"active": True, "id": "schedule_2"},
    "09:59": {"active": True, "id": "schedule_3"},
    "11:59": {"active": True, "id": "schedule_4"},
    "14:59": {"active": True, "id": "schedule_5"}
}

user_states = {}


# --- Fungsi helper untuk konversi waktu ---
def wib_to_utc(wib_time_str):
    """
    Mengkonversi waktu WIB (HH:MM) ke UTC (HH:MM)
    """
    try:
        wib_time = datetime.strptime(wib_time_str, "%H:%M")
        # Set sebagai WIB (UTC+7)
        wib_time = wib_time.replace(tzinfo=timezone(timedelta(hours=7)))
        # Konversi ke UTC
        utc_time = wib_time.astimezone(timezone.utc)
        return utc_time.strftime("%H:%M")
    except Exception:
        return wib_time_str


def utc_to_wib(utc_time_str):
    """
    Mengkonversi waktu UTC (HH:MM) ke WIB (HH:MM)
    """
    try:
        utc_time = datetime.strptime(utc_time_str, "%H:%M")
        # Set sebagai UTC
        utc_time = utc_time.replace(tzinfo=timezone.utc)
        # Konversi ke WIB (UTC+7)
        wib_time = utc_time.astimezone(timezone(timedelta(hours=7)))
        return wib_time.strftime("%H:%M")
    except Exception:
        return utc_time_str


# --- NEW: convert stored UTC time string to server-local time string ---
def utc_to_server_local_str(utc_time_str):
    """
    Mengkonversi waktu yang disimpan sebagai UTC (HH:MM) menjadi waktu server lokal (HH:MM).
    Digunakan agar schedule.every().day.at() dipanggil dengan waktu lokal yang benar.
    """
    try:
        # Parse hh:mm as UTC time on an arbitrary date
        utc_dt = datetime.strptime(utc_time_str, "%H:%M").replace(tzinfo=timezone.utc)
        # Convert to server local timezone
        local_dt = utc_dt.astimezone()  # None => system local timezone
        return local_dt.strftime("%H:%M")
    except Exception as e:
        logging.warning(f"⚠️ Gagal konversi UTC->local untuk '{utc_time_str}': {e}")
        return utc_time_str


# --- Fungsi helper untuk format waktu dengan WIB ---
def format_time_with_wib(utc_time_str):
    """
    Menampilkan waktu UTC dengan konversi WIB
    Format: UTC_TIME (WIB_TIME WIB)
    """
    try:
        wib_str = utc_to_wib(utc_time_str)
        return f"`{utc_time_str}` UTC (`{wib_str}` WIB)"
    except Exception:
        return f"`{utc_time_str}` UTC (WIB)"


def format_datetime_with_wib(dt):
    """
    Format datetime object dengan zona waktu WIB.
    Perbaikan: jika `dt` tidak memiliki tzinfo, anggap sebagai waktu lokal server (bukan UTC).
    """
    # Konversi ke WIB (UTC+7)
    wib_tz = timezone(timedelta(hours=7))
    try:
        if dt is None:
            return 'Tidak ada'

        # Jika dt adalah string, coba parsing beberapa format umum
        if isinstance(dt, str):
            try:
                dt = datetime.fromisoformat(dt)
            except Exception:
                try:
                    dt = datetime.strptime(dt, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    # fallback: return raw string
                    return dt

        # Jika dt tidak memiliki tzinfo, anggap sebagai waktu lokal server
        if dt.tzinfo is None:
            local_tz = datetime.now().astimezone().tzinfo
            dt = dt.replace(tzinfo=local_tz)

        wib_time = dt.astimezone(wib_tz)
        return wib_time.strftime('%H:%M pada %d/%m/%Y (WIB)')
    except Exception as e:
        logging.warning(f"⚠️ format_datetime_with_wib gagal untuk {dt}: {e}")
        return str(dt)


# --- Kirim foto + caption sesuai GROUP_TARGETS ---
def send_screenshot_to_telegram(image_path, caption, target_chat_ids=None):
    """
    Mengirim screenshot ke Telegram.

    - Jika target_chat_ids diberikan, akan dikirim ke chat tersebut.
    - Jika tidak, akan mencari caption di GROUP_TARGETS (exact match).
    - File akan dihapus hanya sekali setelah semua pengiriman selesai.
    """

    if not os.path.exists(image_path):
        logging.error(f"❌ File tidak ditemukan: {image_path}")
        return

    # Tentukan daftar tujuan
    if target_chat_ids:
        chat_ids = target_chat_ids
    else:
        chat_ids = GROUP_TARGETS.get(caption, [])

    if not chat_ids:
        logging.warning(f"⚠️ Tidak ada grup tujuan untuk caption: {caption}")
        return

    success = False
    for chat_id in chat_ids:
        try:
            with open(image_path, "rb") as photo:
                resp = requests.post(
                    f"{API_URL}/sendPhoto",
                    data={"chat_id": chat_id, "caption": caption, "parse_mode": "HTML"},
                    files={"photo": photo}
                )
                resp.raise_for_status()
            logging.info(f"✅ {image_path} terkirim ke {chat_id} ({caption})")
            success = True
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Gagal kirim {image_path} ke {chat_id}: {e}")
        except Exception as e:
            logging.error(f"❌ Error tak terduga saat kirim {image_path} ke {chat_id}: {e}")

    # Hapus file sekali setelah semua chat selesai
    if success:
        try:
            os.remove(image_path)
            logging.info(f"🗑️ File '{image_path}' dihapus setelah pengiriman.")
        except Exception as e:
            logging.warning(f"⚠️ Gagal menghapus file {image_path}: {e}")


# --- Kirim pesan teks ---
def send_message(chat_id, text, reply_markup=None):
    try:
        data = {"chat_id": chat_id, "text": text, "parse_mode": "Markdown"}
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)

        resp = requests.post(f"{API_URL}/sendMessage", data=data)
        resp.raise_for_status()
        logging.info(f"✅ Pesan terkirim ke {chat_id}: '{text[:50]}...'")
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Gagal kirim pesan ke {chat_id}: {e}")
    except Exception as e:
        logging.error(f"❌ Error tak terduga saat kirim pesan ke {chat_id}: {e}")


# --- Fungsi untuk membuat inline keyboard ---
def create_inline_keyboard(buttons):
    return {
        "inline_keyboard": buttons
    }


# --- Setup ulang jadwal ---
def setup_schedule():
    """
    Membersihkan dan mengatur ulang schedule berdasarkan data yang tersimpan (diasumsikan disimpan dalam UTC).
    Perubahan penting: saat menjadwalkan, kita mengonversi waktu yang disimpan (UTC) ke waktu lokal server
    sehingga schedule.every().day.at() dipanggil dengan waktu lokal yang benar.
    """
    schedule.clear()
    active_count = 0
    for time_str, data in schedules_data.items():
        if data["active"]:
            try:
                # validasi format yang disimpan
                datetime.strptime(time_str, "%H:%M")

                # Convert stored UTC -> server local time string (HH:MM)
                schedule_time_local = utc_to_server_local_str(time_str)

                # validasi lagi hasil konversi
                datetime.strptime(schedule_time_local, "%H:%M")

                # Jadwalkan pada waktu lokal server — schedule library menginterpretasikan waktu sebagai waktu lokal
                schedule.every().day.at(schedule_time_local).do(run_full_task).tag(data["id"])
                active_count += 1

                logging.info(
                    f"🗓️ Terjadwal: id={data['id']} | stored_utc={time_str} | local_time={schedule_time_local}")
            except ValueError:
                logging.warning(f"⚠️ Jadwal '{time_str}' tidak valid, dilewati.")
    logging.info(f"📅 Jadwal diperbarui: {active_count} jadwal aktif")


# --- Tampilkan jadwal berikutnya ---
def show_next_schedule():
    next_run = schedule.next_run()
    if next_run:
        formatted_time = format_datetime_with_wib(next_run)
        logging.info(f"⏭️ Jadwal berikutnya: {formatted_time}")
    else:
        logging.info("⏭️ Tidak ada jadwal berikutnya yang aktif.")


# --- Command: /showtime ---
def handle_showtime(chat_id):
    active_schedules = [(time_str, data) for time_str, data in schedules_data.items() if data["active"]]
    inactive_schedules = [(time_str, data) for time_str, data in schedules_data.items() if not data["active"]]

    message = "📋 **STATUS JADWAL**\n\n"

    if active_schedules:
        message += "✅ **Jadwal Aktif:**\n"
        for time_str, _ in sorted(active_schedules):
            message += f"⏰ {format_time_with_wib(time_str)}\n"
        message += f"\n📊 Total aktif: {len(active_schedules)}\n"

    if inactive_schedules:
        message += "\n❌ **Jadwal Nonaktif:**\n"
        for time_str, _ in sorted(inactive_schedules):
            message += f"⏰ {format_time_with_wib(time_str)}\n"
        message += f"\n📊 Total nonaktif: {len(inactive_schedules)}\n"

    if not active_schedules and not inactive_schedules:
        message = "❌ Tidak ada jadwal yang terkonfigurasi."
    else:
        next_run = schedule.next_run()
        if next_run:
            message += f"\n⏭️ Jadwal berikutnya: `{format_datetime_with_wib(next_run)}`"

    send_message(chat_id, message)


# --- Command: /settime ---
def handle_settime(chat_id):
    if not schedules_data:
        user_states[chat_id] = {"action": "settime_input", "old_time": None}
        send_message(chat_id,
                     "➕ **TAMBAH JADWAL BARU**\n\nAnda belum memiliki jadwal. Masukkan waktu untuk jadwal baru:\nFormat: `HH:MM` (contoh: `16:30`)\n\n*Catatan: Masukkan waktu dalam **WIB** - bot akan otomatis mengkonversi ke UTC*")
        return

    # Buat keyboard dengan jadwal yang ada
    buttons = []
    sorted_schedules = sorted(schedules_data.items(), key=lambda item: item[0])
    for time_str, data in sorted_schedules:
        status = "✅" if data["active"] else "❌"
        # Konversi UTC ke WIB untuk tampilan tombol
        try:
            wib_str = utc_to_wib(time_str)
            buttons.append([{
                "text": f"{status} {wib_str} WIB ({time_str} UTC)",
                "callback_data": f"edit_{time_str}"
            }])
        except Exception:
            buttons.append([{
                "text": f"{status} {time_str} UTC",
                "callback_data": f"edit_{time_str}"
            }])

    buttons.append([{"text": "➕ Tambah Jadwal Baru", "callback_data": "add_new"}])
    buttons.append([{"text": "❌ Batal", "callback_data": "cancel"}])

    reply_markup = create_inline_keyboard(buttons)
    send_message(chat_id,
                 "⚙️ **PENGATURAN JADWAL**\n\nPilih jadwal yang ingin diubah/aktifkan/nonaktifkan atau tambah jadwal baru:\n\n*Catatan: Input waktu dalam **WIB** - ditampilkan WIB (UTC)*",
                 reply_markup)

    user_states[chat_id] = {"action": "settime_select"}


# --- Command: /deltime ---
def handle_deltime(chat_id):
    active_schedules = {time_str: data for time_str, data in schedules_data.items() if data["active"]}

    if not active_schedules:
        send_message(chat_id, "❌ Tidak ada jadwal aktif untuk dihapus.")
        return

    # Buat keyboard dengan jadwal aktif
    buttons = []
    for time_str in sorted(active_schedules.keys()):
        # Konversi UTC ke WIB untuk tampilan tombol
        try:
            wib_str = utc_to_wib(time_str)
            buttons.append([{
                "text": f"🗑️ {wib_str} WIB ({time_str} UTC)",
                "callback_data": f"delete_{time_str}"
            }])
        except Exception:
            buttons.append([{
                "text": f"🗑️ {time_str} UTC",
                "callback_data": f"delete_{time_str}"
            }])

    buttons.append([{"text": "❌ Batal", "callback_data": "cancel"}])

    reply_markup = create_inline_keyboard(buttons)
    send_message(chat_id, "🗑️ **HAPUS JADWAL**\n\nPilih jadwal yang ingin dihapus:\n\n*Catatan: Ditampilkan WIB (UTC)*",
                 reply_markup)

    user_states[chat_id] = {"action": "deltime_select"}


# --- Handle callback dari inline keyboard ---
def handle_callback_query(callback_query):
    chat_id = callback_query["message"]["chat"]["id"]
    data = callback_query["data"]
    callback_query_id = callback_query["id"]

    # Answer callback query untuk menghilangkan loading status di tombol
    try:
        requests.post(f"{API_URL}/answerCallbackQuery", data={"callback_query_id": callback_query_id})
    except requests.exceptions.RequestException as e:
        logging.warning(f"Gagal menjawab callback query {callback_query_id}: {e}")

    if data == "cancel":
        user_states.pop(chat_id, None)
        send_message(chat_id, "❌ Operasi dibatalkan.")
        return

    # Handle settime
    if data.startswith("edit_"):
        time_str = data.replace("edit_", "")
        if time_str in schedules_data:
            user_states[chat_id] = {"action": "settime_input", "old_time": time_str}
            current_status = "aktif" if schedules_data[time_str]["active"] else "nonaktif"
            current_wib = utc_to_wib(time_str)
            send_message(chat_id,
                         f"⏰ **UBAH JADWAL**\n\nJadwal saat ini: `{current_wib}` WIB ({current_status})\n\nSilakan masukkan waktu baru dalam **WIB** (atau waktu yang sama untuk mengubah status aktif/nonaktifnya).\nFormat: `HH:MM` (contoh: `16:30`)\n\n*Catatan: Input waktu dalam **WIB** - bot akan otomatis mengkonversi ke UTC*")
        else:
            send_message(chat_id, "❌ Jadwal tidak ditemukan.")
            user_states.pop(chat_id, None)
        return

    if data == "add_new":
        user_states[chat_id] = {"action": "settime_input", "old_time": None}
        send_message(chat_id,
                     "➕ **TAMBAH JADWAL BARU**\n\nMasukkan waktu untuk jadwal baru:\nFormat: `HH:MM` (contoh: `16:30`)\n\n*Catatan: Masukkan waktu dalam **WIB** - bot akan otomatis mengkonversi ke UTC*")
        return

    # Handle deltime
    if data.startswith("delete_"):
        time_str = data.replace("delete_", "")
        if time_str in schedules_data:
            schedules_data[time_str]["active"] = False
            setup_schedule()
            send_message(chat_id, f"✅ Jadwal {format_time_with_wib(time_str)} berhasil dinonaktifkan.")
        else:
            send_message(chat_id, f"❌ Jadwal `{time_str}` tidak ditemukan.")
        user_states.pop(chat_id, None)
        return


# --- Validasi format waktu ---
def validate_time_format(time_str):
    try:
        datetime.strptime(time_str, "%H:%M")
        return True
    except ValueError:
        return False


# --- Handle input waktu dari user ---
def handle_time_input(chat_id, time_input):
    if not validate_time_format(time_input):
        send_message(chat_id,
                     "❌ Format waktu tidak valid! Gunakan format `HH:MM` (contoh: `16:30`)\n\n*Catatan: Masukkan waktu dalam **WIB** - bot akan otomatis mengkonversi ke UTC*")
        return

    user_state = user_states.get(chat_id, {})
    old_time_utc = user_state.get("old_time")  # Ini dalam UTC

    # Konversi input WIB ke UTC untuk penyimpanan
    new_time_utc = wib_to_utc(time_input)

    if old_time_utc:
        if old_time_utc in schedules_data:
            # Jika user input waktu WIB yang sama dengan yang sudah ada
            old_time_wib = utc_to_wib(old_time_utc)
            if time_input == old_time_wib:
                # Toggle status aktif/nonaktif
                schedules_data[old_time_utc]["active"] = not schedules_data[old_time_utc]["active"]
                status_text = "diaktifkan" if schedules_data[old_time_utc]["active"] else "dinonaktifkan"
                send_message(chat_id, f"✅ Jadwal `{time_input}` WIB berhasil {status_text}.")
            else:
                # Ubah waktu jadwal
                del schedules_data[old_time_utc]
                new_schedule_id = f"schedule_{int(time.time())}"
                schedules_data[new_time_utc] = {"active": True, "id": new_schedule_id}
                send_message(chat_id, f"✅ Jadwal berhasil diubah dari `{old_time_wib}` WIB ke `{time_input}` WIB.")
            setup_schedule()
        else:
            send_message(chat_id, f"❌ Jadwal tidak ditemukan.")
    else:
        # Tambah jadwal baru
        if new_time_utc in schedules_data and schedules_data[new_time_utc]["active"]:
            send_message(chat_id, f"❌ Jadwal `{time_input}` WIB sudah ada dan aktif.")
        else:
            new_schedule_id = f"schedule_{int(time.time())}"
            schedules_data[new_time_utc] = {"active": True, "id": new_schedule_id}
            setup_schedule()
            send_message(chat_id, f"✅ Jadwal baru `{time_input}` WIB berhasil ditambahkan.")

    user_states.pop(chat_id, None)


# --- Fungsi utama pengambilan screenshot ---
def run_full_task(target_chat_ids=None):
    global is_running
    if is_running:
        logging.warning("⚠️ Task sedang berjalan, permintaan diabaikan.")
        if target_chat_ids:
            send_message(target_chat_ids[0],
                         "⚠️ Maaf, task pengambilan screenshot sedang berjalan. Silakan coba lagi nanti.")
        return

    is_running = True

    is_manual_trigger = False
    if not target_chat_ids:
        target_chat_ids = GROUP_TARGETS
    else:
        is_manual_trigger = True

    logging.info(f"\n--- Mulai task screenshot untuk {target_chat_ids} ---")

    if is_manual_trigger:
        send_message(target_chat_ids[0], "⏳ Memulai proses pengambilan screenshot. Mohon tunggu...")

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)

            # === Screenshot Looker Studio ===
            logging.info("➡️ Mengambil screenshot Looker Studio...")
            context_looker = browser.new_context(
                viewport={"width": 525, "height": 635},
                device_scale_factor=2.6,
                is_mobile=True,
                user_agent="Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15A372 Safari/604.1"
            )
            page_looker = context_looker.new_page()

            try:
                page_looker.goto(
                    "https://lookerstudio.google.com/reporting/ef7aa823-d379-4eca-8c7c-f0ff47a9924b/page/p_rgveqlnbkd",
                    timeout=60000)
                time.sleep(60)

                print("▶️ Klik tombol menu presentasi…")
                page_looker.wait_for_selector("button#more-options-header-menu-button", timeout=10000)
                page_looker.locator("button#more-options-header-menu-button").click()
                time.sleep(10)
                page_looker.wait_for_selector("button#header-present-button", timeout=10000)
                page_looker.locator("button#header-present-button").click()
                time.sleep(10)

                full_screenshot_looker = "screenshot_full_page_looker.png"
                page_looker.mouse.click(10, 10)
                time.sleep(2)
                page_looker.screenshot(path=full_screenshot_looker, full_page=True)
                send_screenshot_to_telegram(full_screenshot_looker, "DASHBOARD PROVISIONING TSEL @rolimartin @JackSpaarroww @firdausmulia @YantiMohadi @b1yant @Yna_as @chukong")

                actions_looker = [
                    (page_looker.locator(".lego-component.simple-table > .front > .component").first,
                     "Produktifitas Teknisi PSB Klojen"),
                    (page_looker.locator(".lego-component.simple-table.cd-mq84137tsd > .front > .component"),
                     "Detail Order PSB Klojen"),
                ]
                for idx, (locator, caption) in enumerate(actions_looker, start=1):
                    filename = f"click_looker_{idx}.png"
                    try:
                        locator.screenshot(path=filename)
                        locator.click()
                        send_screenshot_to_telegram(filename, caption)
                    except Exception as e_inner:
                        logging.error(f"❌ Gagal screenshot elemen Looker {idx}: {e_inner}")

            except Exception as e_looker:
                logging.error(f"❌ Gagal saat memproses Looker Studio: {e_looker}")
                if target_chat_ids:
                    send_message(target_chat_ids[0], f"⚠️ Gagal mengambil screenshot Looker Studio: {e_looker}")
            finally:
                if context_looker:
                    context_looker.close()

                    # === Screenshot Google Sheets ===
            logging.info("➡️ Mengambil screenshot Google Sheets...")
            context_sheet = None
            page_sheet = None
            try:
                context_sheet = browser.new_context()
                page_sheet = context_sheet.new_page()

                sheet_steps = [
                    ("D9:J23", "sheet_click_1.png", "unspec B2C Klojen @rolimartin @JackSpaarroww @firdausmulia @YantiMohadi @b1yant @Yna_as @chukong"),
                    ("D30:I44", "sheet_click_2.png", "KLOJEN - UNSPEC (KLIRING)"),
                    ("M9:T24", "sheet_click_3.png", "Unspec B2B Klojen"),
                ]
                for range_value, filename, caption in sheet_steps:
                    try:
                        page_sheet.goto(
                            f"https://docs.google.com/spreadsheets/d/1gcprpyHpjuG8QzklpfgWk8hrV5dlAX3aKf-ZQmOM_IU/edit?gid=1872895195&range={range_value}",
                            timeout=75000,
                            wait_until="domcontentloaded"
                        )
                        time.sleep(15)
                        element = page_sheet.locator("#scrollable_right_0 > div:nth-child(2) > div").first
                        element.wait_for(state="visible", timeout=15000)
                        element.screenshot(path=filename)
                        send_screenshot_to_telegram(filename, caption)
                    except Exception as e_sheet_inner:
                        logging.error(f"❌ Gagal saat memproses Google Sheet range {range_value}: {e_sheet_inner}")
                        if target_chat_ids:
                            send_message(target_chat_ids[0],
                                         f"⚠️ Gagal mengambil screenshot Google Sheet (Range {range_value}): {e_sheet_inner}")
            finally:
                if context_sheet:
                    context_sheet.close()

            browser.close()

            if is_manual_trigger:
                send_message(target_chat_ids[0], "✅ Pengambilan screenshot selesai dan telah dikirim.")

    except Exception as e:
        logging.error(f"❌ Error fatal saat menjalankan task screenshot: {e}")
        if target_chat_ids:
            send_message(target_chat_ids[0], f"❌ Terjadi kesalahan fatal saat menjalankan task: {e}")
    finally:
        is_running = False
        logging.info(f"--- Task screenshot selesai ---")
        show_next_schedule()


# --- Command help ---
def handle_help(chat_id):
    help_text = """🤖 **PANDUAN BOT SCHEDULER**

📋 **Perintah yang tersedia:**
• `/start` - Jalankan task screenshot sekarang
• `/showtime` - Tampilkan semua jadwal
• `/settime` - Ubah atau tambah jadwal
• `/deltime` - Hapus jadwal
• `/help` - Tampilkan panduan ini

⏰ **Informasi Jadwal:**
Bot akan otomatis mengambil screenshot dari dashboard dan mengirimkannya sesuai jadwal yang telah diatur.

📝 **Format Waktu:**
Gunakan format `HH:MM` (24 jam)
Contoh: `08:30`, `14:45`, `23:00`

🌏 **Zona Waktu:**
Input waktu dalam **WIB (Waktu Indonesia Barat)**
Bot otomatis mengkonversi dan menyimpan dalam UTC
Jadwal akan berjalan sesuai waktu WIB yang Anda masukkan"""

    send_message(chat_id, help_text)


# --- Listener utama ---
def listen_for_commands():
    offset = None
    while True:
        try:
            resp = requests.get(f"{API_URL}/getUpdates", params={"offset": offset, "timeout": 60})
            resp.raise_for_status()
            data = resp.json()

            if "result" in data:
                for update in data["result"]:
                    offset = update["update_id"] + 1

                    # Handle callback query (dari inline keyboard)
                    if "callback_query" in update:
                        threading.Thread(target=handle_callback_query, args=(update["callback_query"],)).start()
                        continue

                    # Handle message biasa
                    message = update.get("message", {})
                    text = message.get("text", "")

                    chat_info = message.get("chat", {})
                    chat_id = chat_info.get("id", "")
                    chat_type = chat_info.get("type", "unknown")
                    chat_title = chat_info.get("title", "")
                    from_user = message.get("from", {}).get("username", "unknown_user")

                    logging.info(
                        f"📩 Pesan dari @{from_user} | chat_id={chat_id} | type={chat_type} | title='{chat_title}' | text='{text}'")

                    # Handle commands
                    if text.lower() == "/start":
                        logging.info(f"▶ Menerima command /start dari chat_id={chat_id}")
                        # Memicu run_full_task di thread terpisah
                        threading.Thread(target=run_full_task, args=([str(chat_id)],)).start()

                    elif text.lower() == "/showtime":
                        logging.info(f"▶ Menerima command /showtime dari chat_id={chat_id}")
                        threading.Thread(target=handle_showtime, args=(chat_id,)).start()

                    elif text.lower() == "/settime":
                        logging.info(f"▶ Menerima command /settime dari chat_id={chat_id}")
                        threading.Thread(target=handle_settime, args=(chat_id,)).start()

                    elif text.lower() == "/deltime":
                        logging.info(f"▶ Menerima command /deltime dari chat_id={chat_id}")
                        threading.Thread(target=handle_deltime, args=(chat_id,)).start()

                    elif text.lower() == "/help":
                        logging.info(f"▶ Menerima command /help dari chat_id={chat_id}")
                        threading.Thread(target=handle_help, args=(chat_id,)).start()

                    # Handle input waktu dari user yang sedang dalam proses settime
                    elif chat_id in user_states and user_states[chat_id].get("action") == "settime_input":
                        logging.info(f"▶ Menerima input waktu dari chat_id={chat_id}: '{text}'")
                        threading.Thread(target=handle_time_input, args=(chat_id, text.strip(),)).start()

        except requests.exceptions.Timeout:
            pass
        except requests.exceptions.RequestException as e:
            logging.error(f"❌ Error koneksi API Telegram di listener: {e}")
        except Exception as e:
            logging.error(f"❌ Error tak terduga di listener: {e}")

        time.sleep(0.5)


# --- Main scheduler loop ---
def run_scheduler():
    logging.info("⏳ Memulai scheduler otomatis...")
    last_next_run_str = ""
    while True:
        schedule.run_pending()
        next_run = schedule.next_run()
        current_next_run_str = format_datetime_with_wib(next_run) if next_run else 'Tidak ada'

        if current_next_run_str != last_next_run_str:
            logging.info(f"⏭️ Jadwal berikutnya: {current_next_run_str}")
            last_next_run_str = current_next_run_str

        time.sleep(5)


# --- Main ---
if __name__ == "__main__":
    logging.info("🚀 Bot memulai...")

    try:
        logging.info("⚙️ Memastikan Playwright Chromium terinstal...")
        result = subprocess.run(["playwright", "install", "chromium"], capture_output=True, text=True, check=True)
        logging.info(result.stdout)
        logging.info("✅ Playwright Chromium siap.")
    except FileNotFoundError:
        logging.error("❌ Perintah 'playwright' tidak ditemukan. Pastikan Playwright terinstal dan berada di PATH.")
        logging.error(
            "Coba jalankan 'pip install playwright' lalu 'playwright install chromium' secara manual di terminal.")
        exit(1)
    except subprocess.CalledProcessError as e:
        logging.error(f"❌ Gagal menginstal Playwright Chromium: {e.stderr}")
        logging.error("Pastikan Node.js dan npm terinstal, atau instal Playwright secara manual.")
        exit(1)

    setup_schedule()

    listener_thread = threading.Thread(target=listen_for_commands, daemon=True)
    listener_thread.setName("TelegramListener")
    listener_thread.start()
    logging.info("✅ Thread Telegram Listener dimulai.")

    # Start scheduler thread (untuk menjalankan tugas terjadwal)
    scheduler_thread = threading.Thread(target=run_scheduler, daemon=True)
    scheduler_thread.setName("SchedulerLoop")
    scheduler_thread.start()
    logging.info("✅ Thread Scheduler dimulai.")

    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        logging.info("👋 Bot dihentikan secara manual (Ctrl+C).")
    finally:
        logging.info("Program berakhir.")
