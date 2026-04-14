import os

from backend.app import app, get_smtp_credentials


if __name__ == "__main__":
    smtp_user, smtp_pass = get_smtp_credentials()
    if not smtp_user or not smtp_pass:
        print("⚠  Warning: GMAIL_USER / GMAIL_PASS not set. Emails will fail to send.")
    app.run(host="0.0.0.0", debug=False, port=int(os.environ.get("PORT", "5000")), use_reloader=False)
