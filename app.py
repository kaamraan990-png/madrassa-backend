import json
import secrets
import sqlite3
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs


BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "madrassa.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "madrassa@admin2025"
ADMIN_SESSION_TTL = 8 * 60 * 60
ADMIN_SESSIONS = {}


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS admissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            parent_name TEXT NOT NULL,
            phone TEXT NOT NULL,
            course TEXT NOT NULL,
            date_of_birth TEXT,
            address TEXT,
            previous_education TEXT,
            captcha TEXT,
            status TEXT DEFAULT 'Pending',
            roll_no TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    for col, col_def in [
        ("date_of_birth", "TEXT"),
        ("address", "TEXT"),
        ("previous_education", "TEXT"),
        ("status", "TEXT DEFAULT 'Pending'"),
        ("roll_no", "TEXT"),
    ]:
        try:
            cur.execute(f"ALTER TABLE admissions ADD COLUMN {col} {col_def}")
        except Exception:
            pass

    cur.execute("""
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id TEXT NOT NULL UNIQUE,
            student_name TEXT NOT NULL,
            password TEXT NOT NULL,
            progress INTEGER NOT NULL,
            attendance INTEGER NOT NULL,
            lesson TEXT NOT NULL,
            revision TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS syllabus (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS library_books (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            category TEXT NOT NULL,
            availability TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            roll_no TEXT NOT NULL UNIQUE,
            student_name TEXT NOT NULL,
            exam_name TEXT NOT NULL,
            course TEXT NOT NULL,
            total_marks INTEGER NOT NULL,
            obtained_marks INTEGER NOT NULL,
            grade TEXT NOT NULL,
            status TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            message TEXT NOT NULL,
            pdf_url TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("SELECT COUNT(*) FROM students")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO students (student_id, student_name, password, progress, attendance, lesson, revision)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, [
            ("DUA101", "Abdullah", "madrassa123", 78, 96, "Surah Al-Baqarah – New Sabaq", "2 Paras Complete"),
            ("DUA102", "Ayaan", "student456", 55, 89, "Surah Al-Imran – New Sabaq", "1 Para Complete"),
            ("DUA103", "Ibrahim", "pass789", 92, 100, "Surah An-Nisa – New Sabaq", "3 Paras Complete"),
        ])

    cur.execute("SELECT COUNT(*) FROM syllabus")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO syllabus (title, description) VALUES (?, ?)", [
            ("Hifz-ul-Quran", "Daily sabaq (new lesson), sabqi (yesterday's lesson), manzil (older revision), tajweed correction, and personalised memorisation planning under an experienced Hafiz."),
            ("Islamic Studies", "Structured lessons in duas, adab (Islamic manners), basic fiqh (jurisprudence), aqeedah (belief) foundations, seerah (Prophet's biography), and essential knowledge for daily life."),
            ("Tajweed & Qirat", "Focused articulation of Quranic letters, rules of madd, waqf, and proper recitation manners — taught alongside Hifz for complete Quranic mastery."),
            ("Weekly Revision Plan", "Structured Sunday–Thursday timetable with daily sabqi and manzil targets to ensure consistent retention and measurable student progress."),
        ])

    cur.execute("SELECT COUNT(*) FROM library_books")
    if cur.fetchone()[0] == 0:
        cur.executemany("INSERT INTO library_books (title, category, availability) VALUES (?, ?, ?)", [
            ("Tajweed Made Easy", "Quran & Tajweed", "Available"),
            ("Forty Rabbana Duas", "Dua & Dhikr", "Available"),
            ("Basic Fiqh for Students", "Islamic Studies", "Issued"),
            ("Stories of the Prophets – Ibn Kathir", "Seerah & History", "Available"),
            ("Riyad us Saliheen (Abridged)", "Hadith", "Available"),
            ("Aqeedah Tahawiyyah (Simplified)", "Aqeedah", "Issued"),
            ("Masnoon Duas Booklet", "Dua & Dhikr", "Available"),
            ("Learning Arabic Script", "Arabic Language", "Available"),
        ])

    cur.execute("SELECT COUNT(*) FROM results")
    if cur.fetchone()[0] == 0:
        cur.executemany("""
            INSERT INTO results (roll_no, student_name, exam_name, course, total_marks, obtained_marks, grade, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("DUA101", "Abdullah", "Mid-Term Examination 2025", "Hifz-ul-Quran", 100, 88, "A", "Pass"),
            ("DUA102", "Ayaan", "Mid-Term Examination 2025", "Islamic Studies", 100, 81, "A-", "Pass"),
            ("DUA103", "Ibrahim", "Mid-Term Examination 2025", "Hifz-ul-Quran", 100, 95, "A+", "Pass"),
        ])

    conn.commit()
    conn.close()


def read_json(handler):
    length = int(handler.headers.get("Content-Length", "0"))
    data = handler.rfile.read(length).decode("utf-8") if length else "{}"
    return json.loads(data)


def parse_cookies(cookie_header):
    cookies = {}
    if not cookie_header:
        return cookies
    for part in cookie_header.split(";"):
        if "=" not in part:
            continue
        key, value = part.strip().split("=", 1)
        cookies[key] = value
    return cookies


def generate_roll_no(conn):
    row = conn.execute("SELECT COUNT(*) as cnt FROM admissions WHERE roll_no IS NOT NULL").fetchone()
    count = (row["cnt"] or 0) + 1
    return f"DUA{str(count + 200).zfill(3)}"


class MadrassaHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _send_json(self, payload, status=200, extra_headers=None):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        origin = self.headers.get("Origin", "")
        if origin.startswith("https://madrassa-backend-1-5bqd.onrender.com:") or origin.startswith("https://madrassa-backend-1-5bqd.onrender.com:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        if extra_headers:
            for key, value in extra_headers.items():
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(body)

    def _admin_token(self):
        cookies = parse_cookies(self.headers.get("Cookie", ""))
        return cookies.get("admin_session")

    def _is_admin_authenticated(self):
        token = self._admin_token()
        if not token:
            return False
        expires_at = ADMIN_SESSIONS.get(token)
        if not expires_at or expires_at < time.time():
            ADMIN_SESSIONS.pop(token, None)
            return False
        ADMIN_SESSIONS[token] = time.time() + ADMIN_SESSION_TTL
        return True

    def _require_admin(self):
        if self._is_admin_authenticated():
            return True
        self._send_json({"ok": False, "message": "Admin login required."}, 401)
        return False

    def _send_file(self, path: Path, content_type: str):
        if not path.exists():
            self.send_error(404, "Not Found")
            return
        body = path.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        origin = self.headers.get("Origin", "")
        if origin.startswith("https://madrassa-backend-1-5bqd.onrender.com") or origin.startswith("https://madrassa-backend-1-5bqd.onrender.com:"):
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Credentials", "true")
        else:
            self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PATCH, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        static_map = {
            "/": ("index.html", "text/html; charset=utf-8"),
            "/index.html": ("index.html", "text/html; charset=utf-8"),
            "/index.css": ("index.css", "text/css; charset=utf-8"),
            "/admission": ("admission.html", "text/html; charset=utf-8"),
            "/admission.html": ("admission.html", "text/html; charset=utf-8"),
            "/login": ("login.html", "text/html; charset=utf-8"),
            "/login.html": ("login.html", "text/html; charset=utf-8"),
            "/syllabus": ("syllabus.html", "text/html; charset=utf-8"),
            "/syllabus.html": ("syllabus.html", "text/html; charset=utf-8"),
            "/library": ("library.html", "text/html; charset=utf-8"),
            "/library.html": ("library.html", "text/html; charset=utf-8"),
            "/admin": ("admin_admissions.html", "text/html; charset=utf-8"),
            "/admin/admissions": ("admin_admissions.html", "text/html; charset=utf-8"),
            "/admin_admissions.html": ("admin_admissions.html", "text/html; charset=utf-8"),
            "/result": ("result.html", "text/html; charset=utf-8"),
            "/result.html": ("result.html", "text/html; charset=utf-8"),
            "/admit-card": ("admit_card.html", "text/html; charset=utf-8"),
            "/admit_card.html": ("admit_card.html", "text/html; charset=utf-8"),
        }

        if path in static_map:
            filename, ct = static_map[path]
            self._send_file(BASE_DIR / filename, ct)
            return

        if path == "/api/admissions":
            if not self._require_admin():
                return
            qs = parse_qs(parsed.query)
            status_filter = qs.get("status", [None])[0]
            search = qs.get("search", [None])[0]
            query = "SELECT * FROM admissions"
            conditions, params = [], []
            if status_filter and status_filter != "All":
                conditions.append("status = ?")
                params.append(status_filter)
            if search:
                conditions.append("(student_name LIKE ? OR parent_name LIKE ? OR phone LIKE ? OR roll_no LIKE ?)")
                s = f"%{search}%"
                params.extend([s, s, s, s])
            if conditions:
                query += " WHERE " + " AND ".join(conditions)
            query += " ORDER BY created_at DESC, id DESC"
            conn = get_connection()
            rows = conn.execute(query, params).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM admissions").fetchone()[0]
            pending = conn.execute("SELECT COUNT(*) FROM admissions WHERE status='Pending'").fetchone()[0]
            approved = conn.execute("SELECT COUNT(*) FROM admissions WHERE status='Approved'").fetchone()[0]
            rejected = conn.execute("SELECT COUNT(*) FROM admissions WHERE status='Rejected'").fetchone()[0]
            conn.close()
            self._send_json({"items": [dict(r) for r in rows], "stats": {"total": total, "pending": pending, "approved": approved, "rejected": rejected}})
            return

        if path == "/api/syllabus":
            conn = get_connection()
            rows = conn.execute("SELECT title, description FROM syllabus ORDER BY id").fetchall()
            conn.close()
            self._send_json({"items": [dict(r) for r in rows]})
            return

        if path == "/api/library":
            conn = get_connection()
            rows = conn.execute("SELECT title, category, availability FROM library_books ORDER BY id").fetchall()
            conn.close()
            self._send_json({"items": [dict(r) for r in rows]})
            return

        if path == "/api/admit-card":
            qs = parse_qs(parsed.query)
            roll = qs.get("roll_no", [None])[0]
            if not roll:
                self._send_json({"ok": False, "message": "Roll number required."}, 400)
                return
            conn = get_connection()
            row = conn.execute("SELECT * FROM admissions WHERE roll_no = ? AND status = 'Approved'", (roll.strip(),)).fetchone()
            conn.close()
            if not row:
                self._send_json({"ok": False, "message": "No approved admission found for this roll number. Please contact the madrassa office."}, 404)
                return
            self._send_json({"ok": True, "admission": dict(row)})
            return

        if path == "/api/students":
            if not self._require_admin():
                return
            conn = get_connection()
            students = conn.execute("SELECT student_id, student_name, progress, attendance, lesson, revision FROM students ORDER BY student_id").fetchall()
            conn.close()
            self._send_json({"ok": True, "students": [dict(s) for s in students]})
            return

        if path == "/api/results":
            if not self._require_admin():
                return
            conn = get_connection()
            results = conn.execute("SELECT * FROM results ORDER BY id DESC").fetchall()
            conn.close()
            self._send_json({"ok": True, "results": [dict(r) for r in results]})
            return

        if path == "/api/notifications":
            conn = get_connection()
            rows = conn.execute("SELECT id, title, message, pdf_url, created_at FROM notifications ORDER BY created_at DESC").fetchall()
            conn.close()
            self._send_json({"ok": True, "notifications": [dict(r) for r in rows]})
            return

        self.send_error(404, "Not Found")

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/admissions":
            payload = read_json(self)
            required = ["student_name", "parent_name", "phone", "course"]
            missing = [f for f in required if not payload.get(f, "").strip()]
            if missing:
                self._send_json({"ok": False, "message": "Please fill all required admission fields."}, 400)
                return
            conn = get_connection()
            conn.execute("""
                INSERT INTO admissions
                  (student_name, parent_name, phone, course, date_of_birth, address, previous_education, captcha, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
            """, (
                payload["student_name"].strip(), payload["parent_name"].strip(),
                payload["phone"].strip(), payload["course"].strip(),
                payload.get("date_of_birth", "").strip(), payload.get("address", "").strip(),
                payload.get("previous_education", "").strip(), payload.get("captcha", "").strip(),
            ))
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "message": "Admission form submitted successfully. You will be contacted soon. Jazakallahu Khayran."})
            return

        if path == "/api/admin/login":
            payload = read_json(self)
            if payload.get("username", "").strip() == ADMIN_USERNAME and payload.get("password", "").strip() == ADMIN_PASSWORD:
                token = secrets.token_urlsafe(32)
                ADMIN_SESSIONS[token] = time.time() + ADMIN_SESSION_TTL
                self._send_json(
                    {"ok": True, "message": "Admin login successful."},
                    extra_headers={"Set-Cookie": f"admin_session={token}; Max-Age={ADMIN_SESSION_TTL}; Path=/; HttpOnly; SameSite=Lax"}
                )
            else:
                self._send_json({"ok": False, "message": "Invalid admin credentials. Please try again."}, 401)
            return

        if path == "/api/admin/logout":
            token = self._admin_token()
            if token:
                ADMIN_SESSIONS.pop(token, None)
            self._send_json(
                {"ok": True, "message": "Admin logged out."},
                extra_headers={"Set-Cookie": "admin_session=; Max-Age=0; Path=/; HttpOnly; SameSite=Lax"}
            )
            return

        if path == "/api/students":
            if not self._require_admin():
                return
            payload = read_json(self)
            student_id = payload.get("student_id", "").strip()
            student_name = payload.get("student_name", "").strip()
            progress = int(payload.get("progress", 0) or 0)
            attendance = int(payload.get("attendance", 0) or 0)
            lesson = payload.get("lesson", "").strip()
            revision = payload.get("revision", "").strip() or "0 Paras"
            if not student_id or not student_name:
                self._send_json({"ok": False, "message": "Roll number and student name are required."}, 400)
                return
            conn = get_connection()
            try:
                conn.execute(
                    "INSERT INTO students (student_id, student_name, password, progress, attendance, lesson, revision) VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (student_id, student_name, "", progress, attendance, lesson, revision)
                )
                conn.commit()
            except Exception as exc:
                conn.close()
                self._send_json({"ok": False, "message": f"Unable to add student: {exc}"}, 400)
                return
            conn.close()
            self._send_json({"ok": True, "message": "Student added successfully."})
            return

        if path.startswith("/api/students/") and len(path.split("/")) == 4:
            if not self._require_admin():
                return
            student_id = path.split("/")[-1]
            if self.command == "PATCH":
                payload = read_json(self)
                student_name = payload.get("student_name", "").strip()
                progress = int(payload.get("progress", 0) or 0)
                attendance = int(payload.get("attendance", 0) or 0)
                lesson = payload.get("lesson", "").strip()
                revision = payload.get("revision", "").strip() or "0 Paras"
                if not student_name:
                    self._send_json({"ok": False, "message": "Student name is required."}, 400)
                    return
                conn = get_connection()
                try:
                    conn.execute(
                        "UPDATE students SET student_name = ?, progress = ?, attendance = ?, lesson = ?, revision = ? WHERE student_id = ?",
                        (student_name, progress, attendance, lesson, revision, student_id)
                    )
                    conn.commit()
                    if conn.total_changes == 0:
                        conn.close()
                        self._send_json({"ok": False, "message": "Student not found."}, 404)
                        return
                except Exception as exc:
                    conn.close()
                    self._send_json({"ok": False, "message": f"Unable to update student: {exc}"}, 400)
                    return
                conn.close()
                self._send_json({"ok": True, "message": "Student updated successfully."})
                return

        if path == "/api/login":
            payload = read_json(self)
            roll_no = payload.get("roll_no", "").strip() or payload.get("login", "").strip()
            if not roll_no:
                self._send_json({"ok": False, "message": "Please enter your roll number."}, 400)
                return
            conn = get_connection()
            student = conn.execute("""
                SELECT student_id, student_name, progress, attendance, lesson, revision
                FROM students WHERE student_id = ?
            """, (roll_no,)).fetchone()
            conn.close()
            if not student:
                self._send_json({"ok": False, "message": "Invalid roll number."}, 401)
                return
            student = dict(student)
            performance = "Outstanding" if student["progress"] >= 85 and student["attendance"] >= 95 else "Strong" if student["progress"] >= 65 else "Improving"
            student["monthly_performance"] = performance
            self._send_json({"ok": True, "student": student})
            return

        if path == "/api/result":
            payload = read_json(self)
            roll_no = payload.get("roll_no", "").strip()
            captcha = payload.get("captcha", "").strip()
            expected = payload.get("expected_captcha", "").strip()
            if not roll_no or not captcha:
                self._send_json({"ok": False, "message": "Please enter roll number and captcha."}, 400)
                return
            if expected and captcha != expected:
                self._send_json({"ok": False, "message": "Captcha does not match. Please refresh and try again."}, 400)
                return
            conn = get_connection()
            result = conn.execute("SELECT * FROM results WHERE roll_no = ? ORDER BY id DESC LIMIT 1", (roll_no,)).fetchone()
            conn.close()
            if not result:
                self._send_json({"ok": False, "message": "No result found for this roll number."}, 404)
                return
            self._send_json({"ok": True, "result": dict(result)})
            return

        if path == "/api/results":
            if not self._require_admin():
                return
            payload = read_json(self)
            roll_no = payload.get("roll_no", "").strip()
            student_name = payload.get("student_name", "").strip()
            exam_name = payload.get("exam_name", "").strip()
            course = payload.get("course", "").strip()
            total_marks = payload.get("total_marks", "").strip()
            obtained_marks = payload.get("obtained_marks", "").strip()
            grade = payload.get("grade", "").strip()
            status = payload.get("status", "Published").strip()
            if not all([roll_no, student_name, exam_name, course, total_marks, obtained_marks, grade]):
                self._send_json({"ok": False, "message": "All fields are required."}, 400)
                return
            try:
                total_marks = int(total_marks)
                obtained_marks = int(obtained_marks)
            except ValueError:
                self._send_json({"ok": False, "message": "Marks must be numbers."}, 400)
                return
            if obtained_marks > total_marks:
                self._send_json({"ok": False, "message": "Obtained marks cannot exceed total marks."}, 400)
                return
            conn = get_connection()
            try:
                conn.execute("""
                    INSERT INTO results (roll_no, student_name, exam_name, course, total_marks, obtained_marks, grade, status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (roll_no, student_name, exam_name, course, total_marks, obtained_marks, grade, status))
                conn.commit()
            except Exception as exc:
                conn.close()
                self._send_json({"ok": False, "message": f"Unable to add result: {exc}"}, 400)
                return
            conn.close()
            self._send_json({"ok": True, "message": "Result added successfully."})
            return

        if path == "/api/notifications":
            if not self._require_admin():
                return
            payload = read_json(self)
            title = payload.get("title", "").strip()
            message = payload.get("message", "").strip()
            pdf_url = payload.get("pdf_url", "").strip()
            if not title or not message:
                self._send_json({"ok": False, "message": "Please provide both title and message."}, 400)
                return
            conn = get_connection()
            conn.execute(
                "INSERT INTO notifications (title, message, pdf_url) VALUES (?, ?, ?)",
                (title, message, pdf_url)
            )
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "message": "Notification saved successfully."})
            return

        self.send_error(404, "Not Found")

    def do_PATCH(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/admissions/"):
            if not self._require_admin():
                return
            admission_id = path.split("/")[-1]
            if not admission_id.isdigit():
                self._send_json({"ok": False, "message": "Invalid admission ID."}, 400)
                return
            payload = read_json(self)
            new_status = payload.get("status", "").strip()
            if new_status not in ("Pending", "Approved", "Rejected"):
                self._send_json({"ok": False, "message": "Invalid status."}, 400)
                return
            conn = get_connection()
            row = conn.execute("SELECT * FROM admissions WHERE id = ?", (admission_id,)).fetchone()
            if not row:
                conn.close()
                self._send_json({"ok": False, "message": "Admission not found."}, 404)
                return
            roll_no = row["roll_no"]
            if new_status == "Approved" and not roll_no:
                roll_no = generate_roll_no(conn)
                conn.execute("UPDATE admissions SET status=?, roll_no=? WHERE id=?", (new_status, roll_no, admission_id))
            else:
                conn.execute("UPDATE admissions SET status=? WHERE id=?", (new_status, admission_id))
            conn.commit()
            updated = dict(conn.execute("SELECT * FROM admissions WHERE id=?", (admission_id,)).fetchone())
            conn.close()
            self._send_json({"ok": True, "message": f"Status updated to {new_status}.", "admission": updated})
            return
        self.send_error(404, "Not Found")

    def do_DELETE(self):
        parsed = urlparse(self.path)
        path = parsed.path
        if path.startswith("/api/admissions/"):
            if not self._require_admin():
                return
            admission_id = path.split("/")[-1]
            if not admission_id.isdigit():
                self._send_json({"ok": False, "message": "Invalid ID."}, 400)
                return
            conn = get_connection()
            conn.execute("DELETE FROM admissions WHERE id=?", (admission_id,))
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "message": "Record deleted."})
            return
        
        if path.startswith("/api/students/"):
            if not self._require_admin():
                return
            student_id = path.split("/")[-1]
            conn = get_connection()
            try:
                conn.execute("DELETE FROM students WHERE student_id = ?", (student_id,))
                conn.commit()
                if conn.total_changes == 0:
                    conn.close()
                    self._send_json({"ok": False, "message": "Student not found."}, 404)
                    return
            except Exception as exc:
                conn.close()
                self._send_json({"ok": False, "message": f"Unable to delete student: {exc}"}, 400)
                return
            conn.close()
            self._send_json({"ok": True, "message": "Student deleted successfully."})
            return
        
        if path.startswith("/api/results/"):
            if not self._require_admin():
                return
            result_id = path.split("/")[-1]
            if not result_id.isdigit():
                self._send_json({"ok": False, "message": "Invalid ID."}, 400)
                return
            conn = get_connection()
            conn.execute("DELETE FROM results WHERE id=?", (result_id,))
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "message": "Result deleted."})
            return

        if path.startswith("/api/notifications/"):
            if not self._require_admin():
                return
            notification_id = path.split("/")[-1]
            if not notification_id.isdigit():
                self._send_json({"ok": False, "message": "Invalid notification ID."}, 400)
                return
            conn = get_connection()
            conn.execute("DELETE FROM notifications WHERE id = ?", (notification_id,))
            conn.commit()
            conn.close()
            self._send_json({"ok": True, "message": "Notification deleted."})
            return
        
        self.send_error(404, "Not Found")


import os

if __name__ == "__main__":
    init_db()

    PORT = int(os.environ.get("PORT", 10000))

    server = ThreadingHTTPServer(("0.0.0.0", PORT), MadrassaHandler)
    print(f"Server running on port {PORT}")
    server.serve_forever()