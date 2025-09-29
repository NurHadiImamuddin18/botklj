from flask import Flask, request
import os
import requests

app = Flask(__name__)

TOKEN = os.environ.get("BOT_TOKEN")  # Simpan token di environment variable

@app.route("/", methods=["GET"])
def index():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(force=True)
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # Balas pesan
        requests.post(
            f"https://api.telegram.org/bot{TOKEN}/sendMessage",
            json={"chat_id": chat_id, "text": f"Kamu bilang: {text}"}
        )
    return "ok", 200
