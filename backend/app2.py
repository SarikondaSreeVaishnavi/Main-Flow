import base64, hashlib, os, smtplib, uuid
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from urllib.parse import urlparse
from apscheduler.schedulers.background import BackgroundScheduler
from cryptography.fernet import Fernet, InvalidToken
from flask import Flask, jsonify, redirect, request, send_from_directory, url_for
from flask_login import LoginManager, UserMixin, current_user, login_required, login_user, logout_user
from flask_sqlalchemy import SQLAlchemy
import pymysql
from werkzeug.security import check_password_hash, generate_password_hash
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BASE_DIR)
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
def can_write_directory(path):
    probe = Path(path) / ".rtf_write_probe.tmp"
    try:
        probe.write_text("ok", encoding="ascii")
        probe.unlink(missing_ok=True)
        return True
    except Exception:
        return False
def resolve_sqlite_path():
    env_path = (os.environ.get("SQLITE_DB_PATH") or "").strip()
    if env_path:
        db_path = Path(env_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        return str(db_path)
    project_db_path = Path(PROJECT_ROOT) / "rtf_demo.db"
    if can_write_directory(PROJECT_ROOT):
        return str(project_db_path)
    local_app_data = os.environ.get("LOCALAPPDATA")
    fallback_root = Path(local_app_data) if local_app_data else (Path.home() / "AppData" / "Local")
    db_dir = fallback_root / "rtf-project"
    db_dir.mkdir(parents=True, exist_ok=True)
    return str(db_dir / "rtf_demo.db")
def normalize_database_uri(database_uri):
    if not database_uri:
        return None
    if database_uri.startswith("mysql://"):
        return database_uri.replace("mysql://", "mysql+pymysql://", 1)
    return database_uri
def build_database_uri():
    database_url = normalize_database_uri((os.environ.get("DATABASE_URL") or os.environ.get("MYSQL_URL") or "").strip())
    if database_url:
        return database_url
    mysql_host = os.environ.get("MYSQL_HOST", "localhost")
    mysql_port = os.environ.get("MYSQL_PORT", "3306")
    mysql_user = os.environ.get("MYSQL_USER", "root")
    mysql_password = os.environ.get("MYSQL_PASSWORD", "root")
    mysql_database = os.environ.get("MYSQL_DATABASE", "rtf_project")
    if mysql_host and mysql_user and mysql_password and mysql_database:
        return (
            f"mysql+pymysql://{mysql_user}:{mysql_password}"
            f"@{mysql_host}:{mysql_port}/{mysql_database}"
        )
    return f"sqlite:///{resolve_sqlite_path()}"
app = Flask(__name__, static_folder=None)
app.config.update(SECRET_KEY=os.environ.get("SECRET_KEY", "dev-secret-key"), SQLALCHEMY_DATABASE_URI=build_database_uri(), SQLALCHEMY_TRACK_MODIFICATIONS=False)
def derive_fernet_key(secret):
    return base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
def get_credential_cipher():
    key_source = os.environ.get("SMTP_CREDENTIALS_KEY") or app.config["SECRET_KEY"]
    return Fernet(derive_fernet_key(key_source))
def encrypt_secret(raw_value):
    return get_credential_cipher().encrypt(raw_value.encode("utf-8")).decode("ascii")
def decrypt_secret(encrypted_value):
    return get_credential_cipher().decrypt(encrypted_value.encode("ascii")).decode("utf-8")
def ensure_mysql_database_exists():
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if not uri.startswith("mysql+pymysql://"):
        return
    parsed_uri = urlparse(uri)
    mysql_host = os.environ.get("MYSQL_HOST") or parsed_uri.hostname or "localhost"
    mysql_port = int(os.environ.get("MYSQL_PORT") or parsed_uri.port or 3306)
    mysql_user = os.environ.get("MYSQL_USER") or parsed_uri.username or "root"
    mysql_password = os.environ.get("MYSQL_PASSWORD") or parsed_uri.password or "root"
    mysql_database = os.environ.get("MYSQL_DATABASE") or parsed_uri.path.lstrip("/") or "rtf_project"
    try:
        conn = pymysql.connect(
            host=mysql_host,
            port=mysql_port,
            user=mysql_user,
            password=mysql_password,
            charset="utf8mb4",
            autocommit=True,
        )
        with conn.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{mysql_database}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.close()
    except Exception as exc:
        print(f"⚠  Could not ensure MySQL database exists: {exc}")
# Optional fallback for local development when MySQL is not configured.
app.config["DATABASE_BACKEND"] = "mysql" if app.config["SQLALCHEMY_DATABASE_URI"].startswith("mysql") else "sqlite"
db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login_page"
scheduler = BackgroundScheduler(daemon=True)
scheduler.start()
def get_smtp_credentials():
    smtp_user = (os.environ.get("GMAIL_USER") or "").strip()
    smtp_pass = (os.environ.get("GMAIL_PASS") or "").strip()
    if smtp_user and smtp_pass:
        return smtp_user, smtp_pass
    # On Windows, terminals opened before `setx` may miss updated env values.
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as env_key:
                if not smtp_user:
                    smtp_user = (winreg.QueryValueEx(env_key, "GMAIL_USER")[0] or "").strip()
                if not smtp_pass:
                    smtp_pass = (winreg.QueryValueEx(env_key, "GMAIL_PASS")[0] or "").strip()
        except Exception:
            pass
    return smtp_user, smtp_pass
class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    sent_messages = db.relationship("ScheduledEmail", foreign_keys="ScheduledEmail.sender_user_id", back_populates="sender_user", lazy="dynamic")
    smtp_credential = db.relationship("UserSmtpCredential", back_populates="user", uselist=False, cascade="all, delete-orphan")
class UserSmtpCredential(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False, unique=True)
    smtp_host = db.Column(db.String(255), nullable=False, default="smtp.gmail.com")
    smtp_port = db.Column(db.Integer, nullable=False, default=465)
    smtp_username = db.Column(db.String(255), nullable=False)
    smtp_password_encrypted = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    user = db.relationship("User", back_populates="smtp_credential")
class ScheduledEmail(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    job_id = db.Column(db.String(64), unique=True, nullable=False, index=True)
    owner_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False)
    subject = db.Column(db.String(255), nullable=False)
    body = db.Column(db.Text, nullable=False)
    send_at = db.Column(db.DateTime, nullable=False)
    recurrence_type = db.Column(db.String(32), nullable=False, default="once")
    recurrence_interval_days = db.Column(db.Integer, nullable=True)
    next_run_at = db.Column(db.DateTime, nullable=True)
    last_sent_at = db.Column(db.DateTime, nullable=True)
    last_error = db.Column(db.Text, nullable=True)
    status = db.Column(db.String(32), nullable=False, default="scheduled")
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
    owner_user = db.relationship("User", foreign_keys=[owner_user_id])
    sender_user = db.relationship("User", foreign_keys=[sender_user_id])
    recipient_user = db.relationship("User", foreign_keys=[recipient_user_id])
    send_logs = db.relationship("EmailSendLog", back_populates="message", cascade="all, delete-orphan", lazy="dynamic")
class EmailSendLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    message_id = db.Column(db.Integer, db.ForeignKey("scheduled_email.id"), nullable=False)
    sender_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    recipient_user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    recipient_email = db.Column(db.String(255), nullable=False)
    smtp_sender = db.Column(db.String(255), nullable=False)
    status = db.Column(db.String(32), nullable=False)
    error_message = db.Column(db.Text, nullable=True)
    sent_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    message = db.relationship("ScheduledEmail", back_populates="send_logs")
with app.app_context():
    ensure_mysql_database_exists()
    db.create_all()
def json_error(message, code=400): return jsonify({"error": message}), code
def user_payload(user): return {"id": user.id, "name": user.name, "email": user.email}
def owned_message_or_404(message_id):
    message = db.session.get(ScheduledEmail, message_id); return message if message and message.owner_user_id == current_user.id else None
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))
def resolve_sender_smtp_credentials(user_id):
    saved = UserSmtpCredential.query.filter_by(user_id=user_id).first()
    if saved:
        try:
            return (
                saved.smtp_username,
                decrypt_secret(saved.smtp_password_encrypted),
                saved.smtp_host,
                int(saved.smtp_port),
            )
        except (InvalidToken, ValueError):
            return "", "", "", 0
    env_user, env_pass = get_smtp_credentials()
    return env_user, env_pass, "smtp.gmail.com", 465
def recurrence_to_interval_days(recurrence_type, recurrence_interval_days):
    if recurrence_type in {"daily", "weekly"}:
        return 1 if recurrence_type == "daily" else 7
    if recurrence_type == "every_n_days":
        return max(1, int(recurrence_interval_days or 1))
    return None
def compute_next_run(message):
    interval_days = recurrence_to_interval_days(message.recurrence_type, message.recurrence_interval_days)
    if interval_days is None:
        return None
    base_time = message.next_run_at or message.send_at
    return base_time + timedelta(days=interval_days)
def serialize_message(message):
    return {
        "id": message.id,
        "job_id": message.job_id,
        "owner_user_id": message.owner_user_id,
        "sender_user_id": message.sender_user_id,
        "sender_email": message.sender_user.email if message.sender_user else "",
        "recipient_user_id": message.recipient_user_id,
        "recipient_email": message.recipient_email,
        "subject": message.subject,
        "body": message.body,
        "send_at": message.send_at.isoformat(),
        "recurrence_type": message.recurrence_type,
        "recurrence_interval_days": message.recurrence_interval_days,
        "next_run_at": message.next_run_at.isoformat() if message.next_run_at else None,
        "last_sent_at": message.last_sent_at.isoformat() if message.last_sent_at else None,
        "last_error": message.last_error,
        "status": message.status,
        "created_at": message.created_at.isoformat(),
        "updated_at": message.updated_at.isoformat(),
    }
def serialize_log(log):
    return {
        "id": log.id,
        "message_id": log.message_id,
        "sender_user_id": log.sender_user_id,
        "recipient_user_id": log.recipient_user_id,
        "recipient_email": log.recipient_email,
        "smtp_sender": log.smtp_sender,
        "status": log.status,
        "error_message": log.error_message,
        "sent_at": log.sent_at.isoformat(),
    }
def schedule_job(message):
    existing_job = scheduler.get_job(message.job_id)
    if existing_job:
        scheduler.remove_job(message.job_id)
    if message.status == "cancelled":
        return
    if message.recurrence_type == "once":
        scheduler.add_job(send_message, trigger="date", run_date=message.send_at, args=[message.id], id=message.job_id, replace_existing=True)
        return
    interval_days = recurrence_to_interval_days(message.recurrence_type, message.recurrence_interval_days)
    if interval_days is None:
        return
    scheduler.add_job(send_message, trigger="interval", days=interval_days, next_run_time=message.next_run_at or message.send_at, args=[message.id], id=message.job_id, replace_existing=True)
def restore_jobs():
    with app.app_context():
        messages = ScheduledEmail.query.filter(ScheduledEmail.status == "scheduled").all()
        for message in messages:
            if message.next_run_at and message.next_run_at < datetime.utcnow() and message.recurrence_type == "once":
                continue
            if message.send_at >= datetime.utcnow() or message.recurrence_type != "once":
                schedule_job(message)
def send_message(message_id):
    with app.app_context():
        message = db.session.get(ScheduledEmail, message_id)
        if not message or message.status == "cancelled":
            return
        smtp_sender, smtp_password, smtp_host, smtp_port = resolve_sender_smtp_credentials(message.sender_user_id)
        timestamp = datetime.utcnow()
        try:
            if not smtp_sender or not smtp_password:
                raise RuntimeError("SMTP sender credentials are not configured")
            outbound = MIMEMultipart("alternative")
            outbound["From"] = smtp_sender
            outbound["To"] = message.recipient_email
            outbound["Subject"] = message.subject
            outbound.attach(MIMEText(message.body, "plain"))
            with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
                server.login(smtp_sender, smtp_password)
                server.sendmail(smtp_sender, [message.recipient_email], outbound.as_string())
            message.last_sent_at = timestamp
            message.last_error = None
            if message.recurrence_type == "once":
                message.status = "sent"
                message.next_run_at = None
            else:
                message.status = "scheduled"
                message.next_run_at = compute_next_run(message)
            db.session.add(
                EmailSendLog(
                    message_id=message.id,
                    sender_user_id=message.sender_user_id,
                    recipient_user_id=message.recipient_user_id,
                    recipient_email=message.recipient_email,
                    smtp_sender=smtp_sender,
                    status="sent",
                    sent_at=timestamp,
                )
            )
            db.session.commit()
            print(f"[✓] Email sent to {message.recipient_email} — {message.subject}")
        except Exception as exc:
            message.last_error = str(exc)
            if message.recurrence_type == "once":
                message.status = "failed"
            db.session.add(
                EmailSendLog(
                    message_id=message.id,
                    sender_user_id=message.sender_user_id,
                    recipient_user_id=message.recipient_user_id,
                    recipient_email=message.recipient_email,
                    smtp_sender=smtp_sender or "",
                    status="failed",
                    error_message=str(exc),
                    sent_at=timestamp,
                )
            )
            db.session.commit()
            print(f"[✗] Failed to send email {message.id}: {exc}")
@app.route("/")
def index():
    return redirect(url_for("dashboard_page" if current_user.is_authenticated else "login_page"))
@app.route("/login")
def login_page():
    return send_from_directory(FRONTEND_DIR, "login.html")
@app.route("/dashboard")
@login_required
def dashboard_page():
    return send_from_directory(FRONTEND_DIR, "dashboard.html")
@app.route("/messages")
@login_required
def messages_page():
    return send_from_directory(FRONTEND_DIR, "messages.html")
@app.route("/frontend/<path:filename>")
def frontend_assets(filename):
    return send_from_directory(FRONTEND_DIR, filename)
@app.route("/api/me")
@login_required
def api_me():
    smtp_user, smtp_pass, smtp_host, smtp_port = resolve_sender_smtp_credentials(current_user.id)
    return jsonify(
        {
            "id": current_user.id,
            "name": current_user.name,
            "email": current_user.email,
            "smtp_sender": smtp_user,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "smtp_ready": bool(smtp_user and smtp_pass),
        }
    )
@app.route("/api/smtp-credentials", methods=["GET"])
@login_required
def get_smtp_credential():
    credential = UserSmtpCredential.query.filter_by(user_id=current_user.id).first()
    if not credential:
        return jsonify(
            {
                "configured": False,
                "smtp_host": "smtp.gmail.com",
                "smtp_port": 465,
                "smtp_username": "",
            }
        )
    return jsonify(
        {
            "configured": True,
            "smtp_host": credential.smtp_host,
            "smtp_port": credential.smtp_port,
            "smtp_username": credential.smtp_username,
            "updated_at": credential.updated_at.isoformat(),
        }
    )
@app.route("/api/smtp-credentials", methods=["POST"])
@login_required
def upsert_smtp_credential():
    data = request.get_json(silent=True) or {}
    smtp_host = (data.get("smtp_host") or "smtp.gmail.com").strip()
    smtp_username = (data.get("smtp_username") or "").strip()
    smtp_password = data.get("smtp_password") or ""
    smtp_port_raw = data.get("smtp_port", 465)
    if not smtp_host or not smtp_username or not smtp_password:
        return json_error("smtp_host, smtp_port, smtp_username, and smtp_password are required.")
    try:
        smtp_port = int(smtp_port_raw)
    except (TypeError, ValueError):
        return json_error("smtp_port must be a number.")
    if smtp_port <= 0:
        return json_error("smtp_port must be a positive number.")
    credential = UserSmtpCredential.query.filter_by(user_id=current_user.id).first()
    if not credential:
        credential = UserSmtpCredential(user_id=current_user.id)
        db.session.add(credential)
    credential.smtp_host = smtp_host
    credential.smtp_port = smtp_port
    credential.smtp_username = smtp_username
    credential.smtp_password_encrypted = encrypt_secret(smtp_password)
    db.session.commit()
    return jsonify({"message": "SMTP credentials saved.", "configured": True})
@app.route("/api/auth/register", methods=["POST"])
def register():
    data = request.get_json(silent=True) or {}
    name = (data.get("name") or "").strip()
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    if not name or not email or not password:
        return json_error("Name, email, and password are required.")
    if User.query.filter_by(email=email).first():
        return json_error("An account with that email already exists.")
    user = User(
        name=name,
        email=email,
        password_hash=generate_password_hash(password),
    )
    db.session.add(user)
    db.session.commit()
    login_user(user)
    return jsonify({"message": "Account created.", "user": user_payload(user)}), 201
@app.route("/api/auth/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip().lower()
    password = data.get("password") or ""
    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return json_error("Invalid email or password.", 401)
    login_user(user)
    return jsonify({"message": "Logged in.", "user": user_payload(user)})
@app.route("/api/auth/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    return jsonify({"message": "Logged out."})
@app.route("/api/messages", methods=["GET"])
@login_required
def list_messages():
    messages = (
        ScheduledEmail.query.filter_by(owner_user_id=current_user.id)
        .order_by(ScheduledEmail.created_at.desc())
        .all()
    )
    return jsonify([serialize_message(message) for message in messages])
@app.route("/api/messages", methods=["POST"])
@login_required
def create_message():
    data = request.get_json(silent=True) or {}
    required = ["recipient_email", "subject", "body", "send_at", "recurrence_type"]
    if not all(field in data for field in required):
        return json_error("Missing fields.")
    recipient_email = (data.get("recipient_email") or "").strip().lower()
    subject = (data.get("subject") or "").strip()
    body = data.get("body") or ""
    recurrence_type = (data.get("recurrence_type") or "once").strip()
    recurrence_interval_days = data.get("recurrence_interval_days")
    specific_send_times = data.get("specific_send_times") or []
    if not recipient_email or not subject or not body:
        return json_error("Recipient, subject, and body are required.")
    try:
        send_at = datetime.fromisoformat(data["send_at"])
    except ValueError:
        return json_error("Invalid send_at format.")
    if send_at <= datetime.utcnow():
        return json_error("Scheduled time must be in the future.")
    if recurrence_type not in {"once", "daily", "weekly", "every_n_days", "specific_dates"}:
        return json_error("Invalid recurrence type.")
    if recurrence_type == "specific_dates":
        if not isinstance(specific_send_times, list) or not specific_send_times:
            return json_error("specific_send_times must include one or more dates.")
        parsed_times = []
        for raw_time in specific_send_times:
            try:
                parsed = datetime.fromisoformat(str(raw_time))
            except ValueError:
                return json_error("Invalid date in specific_send_times.")
            if parsed <= datetime.utcnow():
                return json_error("All specific dates must be in the future.")
            parsed_times.append(parsed)
        recipient_user = User.query.filter_by(email=recipient_email).first()
        created_messages = []
        for parsed_time in sorted(set(parsed_times)):
            job_id = f"msg-{uuid.uuid4().hex[:12]}"
            message = ScheduledEmail(
                job_id=job_id,
                owner_user_id=current_user.id,
                sender_user_id=current_user.id,
                recipient_user_id=recipient_user.id if recipient_user else None,
                recipient_email=recipient_email,
                subject=subject,
                body=body,
                send_at=parsed_time,
                recurrence_type="once",
                recurrence_interval_days=None,
                next_run_at=parsed_time,
                status="scheduled",
            )
            db.session.add(message)
            created_messages.append(message)
        db.session.commit()
        for message in created_messages:
            schedule_job(message)
        return jsonify({"created": [serialize_message(message) for message in created_messages]}), 201
    if recurrence_type == "every_n_days":
        try:
            recurrence_interval_days = max(1, int(recurrence_interval_days or 0))
        except (TypeError, ValueError):
            return json_error("Interval days must be a positive number.")
    elif recurrence_type == "daily":
        recurrence_interval_days = 1
    elif recurrence_type == "weekly":
        recurrence_interval_days = 7
    else:
        recurrence_interval_days = None
    recipient_user = User.query.filter_by(email=recipient_email).first()
    job_id = f"msg-{uuid.uuid4().hex[:12]}"
    message = ScheduledEmail(
        job_id=job_id,
        owner_user_id=current_user.id,
        sender_user_id=current_user.id,
        recipient_user_id=recipient_user.id if recipient_user else None,
        recipient_email=recipient_email,
        subject=subject,
        body=body,
        send_at=send_at,
        recurrence_type=recurrence_type,
        recurrence_interval_days=recurrence_interval_days,
        next_run_at=send_at,
        status="scheduled",
    )
    db.session.add(message)
    db.session.commit()
    schedule_job(message)
    return jsonify(serialize_message(message)), 201
@app.route("/api/messages/<int:message_id>", methods=["DELETE"])
@login_required
def cancel_message(message_id):
    message = owned_message_or_404(message_id)
    if not message:
        return json_error("Not found.", 404)
    try:
        scheduler.remove_job(message.job_id)
    except Exception:
        pass
    message.status = "cancelled"
    db.session.commit()
    return jsonify({"message": "Cancelled."})
@app.route("/api/messages/<int:message_id>/logs", methods=["GET"])
@login_required
def message_logs(message_id):
    message = owned_message_or_404(message_id)
    if not message:
        return json_error("Not found.", 404)
    logs = message.send_logs.order_by(EmailSendLog.sent_at.desc()).all()
    return jsonify([serialize_log(log) for log in logs])
restore_jobs()
if __name__ == "__main__":
    smtp_user, smtp_pass = get_smtp_credentials()
    if not smtp_user or not smtp_pass:
        print("⚠  Warning: GMAIL_USER / GMAIL_PASS not set. Emails will fail to send.")
    if app.config["DATABASE_BACKEND"] == "sqlite":
        print("⚠  Using SQLite fallback because no MySQL DATABASE_URL or MYSQL_* variables were provided.")
        print(f"ℹ  SQLite path: {app.config['SQLALCHEMY_DATABASE_URI'].replace('sqlite:///', '')}")
    app.run(host="0.0.0.0", debug=os.environ.get("FLASK_DEBUG") == "1", port=int(os.environ.get("PORT", "5000")), use_reloader=False)
