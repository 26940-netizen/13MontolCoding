"""
ระบบติดตามงานและคะแนน (Student Assignment Tracking & Grading System)
Flask + SQLite — ไฟล์เดียว

วิธีรัน:
    pip install flask
    python app.py

จากนั้นเปิด:
    http://127.0.0.1:5000
"""

import os
import sqlite3
import hashlib
from datetime import date, datetime, timedelta
from functools import wraps
from jinja2 import DictLoader

from flask import (
    Flask, render_template_string, request, redirect,
    url_for, session, flash, g
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "school.db")

app = Flask(__name__)
app.secret_key = "student-tracking-demo-secret"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  email TEXT UNIQUE NOT NULL,
  password TEXT NOT NULL,
  role TEXT NOT NULL CHECK (role IN ('TEACHER','STUDENT')),
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS classes (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  description TEXT,
  teacher_id INTEGER NOT NULL,
  join_code TEXT UNIQUE,
  homeroom_teacher_name TEXT,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS subjects (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,
  class_id INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS enrollments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  class_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  created_at TEXT DEFAULT (datetime('now')),
  UNIQUE(class_id, student_id)
);
CREATE TABLE IF NOT EXISTS assignments (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  subject_id INTEGER NOT NULL,
  created_by_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  description TEXT,
  due_date TEXT NOT NULL,
  full_score REAL NOT NULL DEFAULT 100,
  attachment_url TEXT,
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS submissions (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  assignment_id INTEGER NOT NULL,
  student_id INTEGER NOT NULL,
  content TEXT,
  file_url TEXT,
  status TEXT NOT NULL DEFAULT 'SUBMITTED',
  submitted_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now')),
  UNIQUE(assignment_id, student_id)
);
CREATE TABLE IF NOT EXISTS grades (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  submission_id INTEGER NOT NULL UNIQUE,
  score REAL NOT NULL,
  feedback TEXT,
  graded_by_id INTEGER NOT NULL,
  graded_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_id INTEGER NOT NULL,
  title TEXT NOT NULL,
  message TEXT,
  type TEXT NOT NULL,
  is_read INTEGER NOT NULL DEFAULT 0,
  related_assignment_id INTEGER,
  created_at TEXT DEFAULT (datetime('now'))
);
"""

def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db

@app.teardown_appcontext
def close_db(exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def hashpw(pw):
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()

def init_db():
    db = get_db()
    db.executescript(SCHEMA)
    seed(db)
    ensure_demo_submissions_and_notifications(db)
    cleanup_and_expand_demo_data(db)
    db.commit()

def seed(db):
    """Create demo data on first run, and also update the demo roster on later runs."""
    cur = db.cursor()

    # If the database already exists, migrate the demo roster instead of
    # returning early. This is important because school.db may already have
    # been created by an older version of the app.
    existing = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if existing > 0:
        migrate_demo_roster(db)
        return

    teacher_id = cur.execute(
        "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
        ("ครูสุเทพ ชื่นบาน", "suthep@school.ac.th", hashpw("1234"), "TEACHER")
    ).lastrowid
    bio_teacher_id = cur.execute(
        "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
        ("นางสาวอุมาพร จงนอก", "umaphorn@school.ac.th", hashpw("1234"), "TEACHER")
    ).lastrowid

    student_names = [
        ("นายปิยวัฒน์ คำหอม", "piyawat@school.ac.th"),
        ("นายกิตติกร ปะวะบุตร", "kittikorn@school.ac.th"),
        ("นายจิรวัฒน์ เครือวรรณ", "jirawat@school.ac.th"),
        ("นายมณฑล ทองประดับ", "montol@school.ac.th"),
        ("นายพีรพันธุ์ ช้างเชียว", "phiraphan@school.ac.th"),
    ]

    student_ids = []
    for name, email in student_names:
        sid = cur.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
            (name, email, hashpw("1234"), "STUDENT")
        ).lastrowid
        student_ids.append(sid)

    classes = [
        ("ม.4/4", "ห้องเรียนระดับชั้นมัธยมศึกษาปีที่ 4 ห้อง 4", "M44", "ครูสุเทพ ชื่นบาน"),
        ("ม.5/4", "ห้องเรียนระดับชั้นมัธยมศึกษาปีที่ 5 ห้อง 4", "M54", "ครูปาลีภัสร์ ธัญเมธจารุโรจน์"),
        ("ม.6/4", "ห้องเรียนระดับชั้นมัธยมศึกษาปีที่ 6 ห้อง 4", "M64", "ครูนฤมล สุนทอง"),
    ]
    subject_names = ["คณิตศาสตร์", "ฟิสิกส์", "เคมี", "ชีววิทยา", "ภาษาอังกฤษ", "ภาษาไทย"]

    primary_class_id = None
    class_ids = {}
    for i, (cname, cdesc, code, homeroom) in enumerate(classes):
        cid = cur.execute(
            "INSERT INTO classes (name,description,teacher_id,join_code,homeroom_teacher_name) VALUES (?,?,?,?,?)",
            (cname, cdesc, teacher_id, code, homeroom)
        ).lastrowid
        class_ids[cname] = cid
        if i == 0:
            primary_class_id = cid
        for subj in subject_names:
            cur.execute("INSERT INTO subjects (name,class_id) VALUES (?,?)", (subj, cid))

    for sid in student_ids:
        cur.execute("INSERT INTO enrollments (class_id,student_id) VALUES (?,?)", (primary_class_id, sid))

    # The requested M.5/4 student.
    kanokporn_id = cur.execute(
        "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
        ("นางสาวกนกพร ลพานุสรณ์", "kanokporn@school.ac.th", hashpw("1234"), "STUDENT")
    ).lastrowid
    cur.execute("INSERT INTO enrollments (class_id,student_id) VALUES (?,?)", (class_ids["ม.5/4"], kanokporn_id))

    # M.5/4 gets its own M.5-level work across every subject.
    m5_defs = {
        "คณิตศาสตร์": [
            ("ลำดับและอนุกรม", "แบบฝึกหัดเรื่องลำดับเลขคณิตและเรขาคณิต ระดับ ม.5", 5, 20),
            ("ตรีโกณมิติ", "แบบฝึกหัดการประยุกต์ใช้ฟังก์ชันตรีโกณมิติ ระดับ ม.5", 10, 30),
            ("โครงงานคณิตศาสตร์", "โจทย์ประยุกต์และการนำเสนอวิธีคิด ระดับ ม.5", 20, 50),
        ],
        "ฟิสิกส์": [
            ("การเคลื่อนที่แบบโพรเจกไทล์", "แบบฝึกหัดการเคลื่อนที่แบบโพรเจกไทล์ ระดับ ม.5", 5, 20),
            ("งานและพลังงาน", "แบบฝึกหัดเรื่องงาน กำลัง และพลังงาน ระดับ ม.5", 10, 30),
            ("โครงงานฟิสิกส์", "รายงานการทดลองและวิเคราะห์ผล ระดับ ม.5", 20, 50),
        ],
        "เคมี": [
            ("อัตราการเกิดปฏิกิริยา", "แบบฝึกหัดเรื่องอัตราการเกิดปฏิกิริยาเคมี ระดับ ม.5", 5, 20),
            ("สมดุลเคมี", "แบบฝึกหัดเรื่องสมดุลเคมี ระดับ ม.5", 10, 30),
            ("โครงงานเคมี", "รายงานการทดลองเคมี ระดับ ม.5", 20, 50),
        ],
        "ชีววิทยา": [
            ("โครงสร้างและหน้าที่ของเซลล์", "แบบฝึกหัดชีววิทยาเรื่องโครงสร้างและหน้าที่ของเซลล์ ระดับ ม.5", 5, 20),
            ("ระบบย่อยอาหาร", "แบบฝึกหัดเรื่องการย่อยและการดูดซึมสารอาหาร ระดับ ม.5", 10, 30),
            ("โครงงานชีววิทยา", "รายงานการสังเกตหรือการทดลองทางชีววิทยา ระดับ ม.5", 20, 50),
        ],
        "ภาษาอังกฤษ": [
            ("Reading Comprehension", "แบบฝึกอ่านจับใจความภาษาอังกฤษ ระดับ ม.5", 5, 20),
            ("Grammar in Context", "แบบฝึกไวยากรณ์และการใช้ภาษาในบริบท ระดับ ม.5", 10, 30),
            ("English Project", "โครงงานนำเสนอภาษาอังกฤษ ระดับ ม.5", 20, 50),
        ],
        "ภาษาไทย": [
            ("วิเคราะห์วรรณคดี", "แบบฝึกวิเคราะห์วรรณคดีและวรรณกรรม ระดับ ม.5", 5, 20),
            ("การเขียนเชิงวิชาการ", "แบบฝึกการเขียนและเรียบเรียงข้อมูล ระดับ ม.5", 10, 30),
            ("โครงงานภาษาไทย", "รายงานวิเคราะห์ภาษาและวรรณกรรม ระดับ ม.5", 20, 50),
        ],
    }
    for subject_name, defs in m5_defs.items():
        subject_row = cur.execute(
            "SELECT id FROM subjects WHERE class_id=? AND name=?",
            (class_ids["ม.5/4"], subject_name)
        ).fetchone()
        if subject_row:
            for title, desc, days, score in defs:
                due = (date.today() + timedelta(days=days)).isoformat()
                cur.execute(
                    "INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score) VALUES (?,?,?,?,?,?)",
                    (subject_row[0], teacher_id, title, desc, due, score)
                )

    # The biology teacher owns only biology assignments.
    for class_name in ("ม.4/4", "ม.5/4"):
        class_row = cur.execute("SELECT id FROM classes WHERE name=?", (class_name,)).fetchone()
        if class_row:
            subject_row = cur.execute(
                "SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา'",
                (class_row[0],)
            ).fetchone()
            if subject_row:
                bio_defs = [
                    ("ใบงานชีววิทยา: เซลล์", f"ใบงานชีววิทยาเรื่องโครงสร้างและหน้าที่ของเซลล์ ({class_name})", 5, 20),
                    ("แบบทดสอบชีววิทยา", f"แบบทดสอบเก็บคะแนนชีววิทยา ({class_name})", 10, 30),
                    ("โครงงานชีววิทยา", f"โครงงานชีววิทยาประจำภาคเรียน ({class_name})", 20, 50),
                ]
                for title, desc, days, score in bio_defs:
                    due = (date.today() + timedelta(days=days)).isoformat()
                    cur.execute(
                        "INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score) VALUES (?,?,?,?,?,?)",
                        (subject_row[0], bio_teacher_id, title, desc, due, score)
                    )

    assignment_defs = [
        ("แบบฝึกหัดครั้งที่ 1", "แบบฝึกหัดเก็บคะแนนชุดแรกของภาคเรียน", 5, 20),
        ("สอบย่อยกลางภาค", "สอบย่อยเพื่อวัดความเข้าใจเนื้อหาครึ่งภาคเรียน", 10, 30),
        ("รายงาน / โครงงาน", "งานชิ้นใหญ่ประจำวิชา ส่งท้ายภาค", 20, 50),
    ]
    assignment_ids = {}
    subjects = cur.execute("SELECT id,name FROM subjects WHERE class_id=?", (primary_class_id,)).fetchall()
    for sub in subjects:
        for title, desc, days, score in assignment_defs:
            due = (date.today() + timedelta(days=days)).isoformat()
            aid = cur.execute(
                "INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score) VALUES (?,?,?,?,?,?)",
                (sub["id"], teacher_id, title, desc, due, score)
            ).lastrowid
            assignment_ids[(sub["name"], title)] = aid

    # Demo grades belong to the user named Montol.
    montol = student_ids[3]
    graded = [
        ("คณิตศาสตร์", "แบบฝึกหัดครั้งที่ 1", "ส่งแบบฝึกหัดคณิตศาสตร์ครบทุกข้อแล้วครับ", 18, "ทำได้ดีมาก แสดงวิธีทำครบถ้วน"),
        ("คณิตศาสตร์", "สอบย่อยกลางภาค", "ทำข้อสอบย่อยเสร็จแล้ว ข้อท้ายๆ ค่อนข้างยาก", 26, "เก่งมาก ระวังโจทย์ตรรกะข้อสุดท้าย"),
        ("ฟิสิกส์", "แบบฝึกหัดครั้งที่ 1", "ส่งแบบฝึกหัดฟิสิกส์แล้วครับ", 15, "ภาพรวมดี มีจุดที่คำนวณคลาดเคลื่อน 2 ข้อ"),
        ("ภาษาอังกฤษ", "แบบฝึกหัดครั้งที่ 1", "ส่งแบบฝึกหัดภาษาอังกฤษแล้วครับ", 17, "ไวยากรณ์ดี ระวังเรื่อง tense นิดหน่อย"),
    ]
    waiting = [
        ("ชีววิทยา", "แบบฝึกหัดครั้งที่ 1", "ส่งงานชีววิทยาแล้วครับ"),
        ("ภาษาไทย", "แบบฝึกหัดครั้งที่ 1", "ส่งงานภาษาไทยแล้วครับ"),
    ]
    for subj, title, content, score, feedback in graded:
        aid = assignment_ids[(subj, title)]
        sub_id = cur.execute(
            "INSERT INTO submissions (assignment_id,student_id,content,status) VALUES (?,?,?,?)",
            (aid, montol, content, "GRADED")
        ).lastrowid
        cur.execute(
            "INSERT INTO grades (submission_id,score,feedback,graded_by_id) VALUES (?,?,?,?)",
            (sub_id, score, feedback, teacher_id)
        )
    for subj, title, content in waiting:
        aid = assignment_ids[(subj, title)]
        cur.execute(
            "INSERT INTO submissions (assignment_id,student_id,content,status) VALUES (?,?,?,?)",
            (aid, montol, content, "SUBMITTED")
        )


def migrate_demo_roster(db):
    """Update an existing school.db to the requested demo roster."""
    cur = db.cursor()
    teacher = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("suthep@school.ac.th",)).fetchone()
    if not teacher:
        teacher = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("supaporn@school.ac.th",)).fetchone()
    if not teacher:
        teacher_id = cur.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,'TEACHER')",
            ("ครูสุเทพ ชื่นบาน", "suthep@school.ac.th", hashpw("1234"))
        ).lastrowid
    else:
        teacher_id = teacher[0]
        cur.execute(
            "UPDATE users SET name=?, email=?, password=?, role='TEACHER' WHERE id=?",
            ("ครูสุเทพ ชื่นบาน", "suthep@school.ac.th", hashpw("1234"), teacher_id)
        )

    bio_teacher = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("umaphorn@school.ac.th",)).fetchone()
    if not bio_teacher:
        bio_teacher_id = cur.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,'TEACHER')",
            ("นางสาวอุมาพร จงนอก", "umaphorn@school.ac.th", hashpw("1234"))
        ).lastrowid
    else:
        bio_teacher_id = bio_teacher[0]
        cur.execute(
            "UPDATE users SET name=?, password=?, role='TEACHER' WHERE id=?",
            ("นางสาวอุมาพร จงนอก", hashpw("1234"), bio_teacher_id)
        )

    desired_m44 = [
        ("นายมณฑล ทองประดับ", "montol@school.ac.th", "monton@school.ac.th"),
        ("นายปิยวัฒน์ คำหอม", "piyawat@school.ac.th", "napas@school.ac.th"),
        ("นายกิตติกร ปะวะบุตร", "kittikorn@school.ac.th", "tanakorn@school.ac.th"),
        ("นายจิรวัฒน์ เครือวรรณ", "jirawat@school.ac.th", "natcha@school.ac.th"),
        ("นายพีรพันธุ์ ช้างเชียว", "phiraphan@school.ac.th", "orawan@school.ac.th"),
    ]

    # Reuse the old demo student rows so existing grades/submissions do not break.
    used_ids = set()
    for name, new_email, old_email in desired_m44:
        row = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (new_email,)).fetchone()
        if not row:
            row = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (old_email,)).fetchone()
        if row and row[0] not in used_ids:
            sid = row[0]
            used_ids.add(sid)
            cur.execute("UPDATE users SET name=?, email=?, password=?, role='STUDENT' WHERE id=?",
                        (name, new_email, hashpw("1234"), sid))
        else:
            cur.execute("INSERT OR IGNORE INTO users (name,email,password,role) VALUES (?,?,?,'STUDENT')",
                        (name, new_email, hashpw("1234")))

    # Ensure M.5/4 exists.
    m54 = cur.execute("SELECT id FROM classes WHERE name='ม.5/4' AND teacher_id=?", (teacher_id,)).fetchone()
    if not m54:
        m54_id = cur.execute(
            "INSERT INTO classes (name,description,teacher_id,join_code,homeroom_teacher_name) VALUES (?,?,?,?,?)",
            ("ม.5/4", "ห้องเรียนระดับชั้นมัธยมศึกษาปีที่ 5 ห้อง 4", "M54", "ครูปาลีภัสร์ ธัญเมธจารุโรจน์")
        ).lastrowid
        for subj in ["คณิตศาสตร์", "ฟิสิกส์", "เคมี", "ชีววิทยา", "ภาษาอังกฤษ", "ภาษาไทย"]:
            cur.execute("INSERT INTO subjects (name,class_id) VALUES (?,?)", (subj, m54_id))
    else:
        m54_id = m54[0]

    # Ensure the requested M.5/4 student exists.
    kanok = cur.execute("SELECT id FROM users WHERE lower(email)=?", ("kanokporn@school.ac.th",)).fetchone()
    if not kanok:
        kanok_id = cur.execute(
            "INSERT INTO users (name,email,password,role) VALUES (?,?,?,'STUDENT')",
            ("นางสาวกนกพร ลพานุสรณ์", "kanokporn@school.ac.th", hashpw("1234"))
        ).lastrowid
    else:
        kanok_id = kanok[0]
        cur.execute("UPDATE users SET name=?, password=?, role='STUDENT' WHERE id=?",
                    ("นางสาวกนกพร ลพานุสรณ์", hashpw("1234"), kanok_id))
    cur.execute("INSERT OR IGNORE INTO enrollments (class_id,student_id) VALUES (?,?)", (m54_id, kanok_id))

    # Make ครูสุเทพ the advisor/owner of M.4/4.
    cur.execute(
        "UPDATE classes SET teacher_id=?, homeroom_teacher_name=? WHERE name='ม.4/4'",
        (teacher_id, "ครูสุเทพ ชื่นบาน")
    )
    # M.5/4 remains under its existing homeroom teacher name.

    # Biology work in M.4/4 and M.5/4 belongs to the biology teacher so the
    # same submission/grade is visible to that teacher and the advisor.
    for class_name in ("ม.4/4", "ม.5/4"):
        cur.execute("""
            UPDATE assignments
            SET created_by_id=?
            WHERE subject_id IN (
                SELECT s.id FROM subjects s
                JOIN classes c ON c.id=s.class_id
                WHERE c.name=? AND s.name='ชีววิทยา'
            )
        """, (bio_teacher_id, class_name))

    # Rebuild M.4/4 enrollment so it contains exactly the five requested students.
    m44 = cur.execute("SELECT id FROM classes WHERE name='ม.4/4' AND teacher_id=?", (teacher_id,)).fetchone()
    if m44:
        m44_id = m44[0]
        cur.execute("DELETE FROM enrollments WHERE class_id=?", (m44_id,))
        for name, email, old_email in desired_m44:
            row = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", (email,)).fetchone()
            if row:
                cur.execute("INSERT OR IGNORE INTO enrollments (class_id,student_id) VALUES (?,?)", (m44_id, row[0]))

    # Ensure M.5/4 has M.5-level assignments for Kanokporn.
    m54_id = cur.execute("SELECT id FROM classes WHERE name='ม.5/4' AND teacher_id=?", (teacher_id,)).fetchone()[0]
    m5_defs = {
        "คณิตศาสตร์": [
            ("ลำดับและอนุกรม", "แบบฝึกหัดเรื่องลำดับเลขคณิตและเรขาคณิต ระดับ ม.5", 5, 20),
            ("ตรีโกณมิติ", "แบบฝึกหัดการประยุกต์ใช้ฟังก์ชันตรีโกณมิติ ระดับ ม.5", 10, 30),
            ("โครงงานคณิตศาสตร์", "โจทย์ประยุกต์และการนำเสนอวิธีคิด ระดับ ม.5", 20, 50),
        ],
        "ฟิสิกส์": [
            ("การเคลื่อนที่แบบโพรเจกไทล์", "แบบฝึกหัดการเคลื่อนที่แบบโพรเจกไทล์ ระดับ ม.5", 5, 20),
            ("งานและพลังงาน", "แบบฝึกหัดเรื่องงาน กำลัง และพลังงาน ระดับ ม.5", 10, 30),
            ("โครงงานฟิสิกส์", "รายงานการทดลองและวิเคราะห์ผล ระดับ ม.5", 20, 50),
        ],
        "เคมี": [
            ("อัตราการเกิดปฏิกิริยา", "แบบฝึกหัดเรื่องอัตราการเกิดปฏิกิริยาเคมี ระดับ ม.5", 5, 20),
            ("สมดุลเคมี", "แบบฝึกหัดเรื่องสมดุลเคมี ระดับ ม.5", 10, 30),
            ("โครงงานเคมี", "รายงานการทดลองเคมี ระดับ ม.5", 20, 50),
        ],
        "ชีววิทยา": [
            ("โครงสร้างและหน้าที่ของเซลล์", "แบบฝึกหัดชีววิทยาเรื่องโครงสร้างและหน้าที่ของเซลล์ ระดับ ม.5", 5, 20),
            ("ระบบย่อยอาหาร", "แบบฝึกหัดเรื่องการย่อยและการดูดซึมสารอาหาร ระดับ ม.5", 10, 30),
            ("โครงงานชีววิทยา", "รายงานการสังเกตหรือการทดลองทางชีววิทยา ระดับ ม.5", 20, 50),
        ],
        "ภาษาอังกฤษ": [
            ("Reading Comprehension", "แบบฝึกอ่านจับใจความภาษาอังกฤษ ระดับ ม.5", 5, 20),
            ("Grammar in Context", "แบบฝึกไวยากรณ์และการใช้ภาษาในบริบท ระดับ ม.5", 10, 30),
            ("English Project", "โครงงานนำเสนอภาษาอังกฤษ ระดับ ม.5", 20, 50),
        ],
        "ภาษาไทย": [
            ("วิเคราะห์วรรณคดี", "แบบฝึกวิเคราะห์วรรณคดีและวรรณกรรม ระดับ ม.5", 5, 20),
            ("การเขียนเชิงวิชาการ", "แบบฝึกการเขียนและเรียบเรียงข้อมูล ระดับ ม.5", 10, 30),
            ("โครงงานภาษาไทย", "รายงานวิเคราะห์ภาษาและวรรณกรรม ระดับ ม.5", 20, 50),
        ],
    }
    for subject_name, defs in m5_defs.items():
        sr = cur.execute("SELECT id FROM subjects WHERE class_id=? AND name=?", (m54_id, subject_name)).fetchone()
        if sr:
            for title, desc, days, score in defs:
                exists = cur.execute(
                    "SELECT id FROM assignments WHERE subject_id=? AND title=? AND created_by_id=?",
                    (sr[0], title, teacher_id)
                ).fetchone()
                if not exists:
                    cur.execute(
                        "INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score) VALUES (?,?,?,?,?,?)",
                        (sr[0], teacher_id, title, desc, (date.today() + timedelta(days=days)).isoformat(), score)
                    )

    # Ensure the biology teacher has biology-only assignments in M.4/4 and M.5/4.
    for class_name in ("ม.4/4", "ม.5/4"):
        cr = cur.execute("SELECT id FROM classes WHERE name=?", (class_name,)).fetchone()
        if cr:
            sr = cur.execute("SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา'", (cr[0],)).fetchone()
            if sr:
                bio_defs = [
                    ("ใบงานชีววิทยา: เซลล์", f"ใบงานชีววิทยาเรื่องโครงสร้างและหน้าที่ของเซลล์ ({class_name})", 5, 20),
                    ("แบบทดสอบชีววิทยา", f"แบบทดสอบเก็บคะแนนชีววิทยา ({class_name})", 10, 30),
                    ("โครงงานชีววิทยา", f"โครงงานชีววิทยาประจำภาคเรียน ({class_name})", 20, 50),
                ]
                for title, desc, days, score in bio_defs:
                    exists = cur.execute(
                        "SELECT id FROM assignments WHERE subject_id=? AND title=? AND created_by_id=?",
                        (sr[0], title, bio_teacher_id)
                    ).fetchone()
                    if not exists:
                        cur.execute(
                            "INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score) VALUES (?,?,?,?,?,?)",
                            (sr[0], bio_teacher_id, title, desc, (date.today() + timedelta(days=days)).isoformat(), score)
                        )

    db.commit()

def ensure_demo_submissions_and_notifications(db):
    """Keep the demo data rich and synchronized on every startup."""
    cur = db.cursor()

    suthep = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("suthep@school.ac.th",)).fetchone()
    bio = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("umaphorn@school.ac.th",)).fetchone()
    montol = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("montol@school.ac.th",)).fetchone()
    kanok = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("kanokporn@school.ac.th",)).fetchone()
    m44 = cur.execute("SELECT id FROM classes WHERE name='ม.4/4' LIMIT 1").fetchone()
    m54 = cur.execute("SELECT id FROM classes WHERE name='ม.5/4' LIMIT 1").fetchone()
    if not all((suthep, bio, montol, kanok, m44, m54)):
        return
    suthep_id, bio_id = suthep[0], bio[0]
    montol_id, kanok_id = montol[0], kanok[0]
    m44_id, m54_id = m44[0], m54[0]

    # Advisor sees the entire M.4/4 roster, while the biology teacher owns
    # biology assignments. Existing M.4 biology submissions remain attached.
    cur.execute("UPDATE classes SET teacher_id=?, homeroom_teacher_name=? WHERE id=?",
                (suthep_id, "ครูสุเทพ ชื่นบาน", m44_id))
    cur.execute("""
        UPDATE assignments SET created_by_id=?
        WHERE subject_id IN (SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา')
    """, (bio_id, m44_id))
    cur.execute("""
        UPDATE assignments SET created_by_id=?
        WHERE subject_id IN (SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา')
    """, (bio_id, m54_id))

    # Give Kanokporn a realistic mix of submitted/graded work.
    preferred = [
        (m54_id, "คณิตศาสตร์", "ลำดับและอนุกรม", 18, "ทำได้ดีมาก แสดงวิธีทำครบถ้วน"),
        (m54_id, "ฟิสิกส์", "การเคลื่อนที่แบบโพรเจกไทล์", 17, "เข้าใจหลักการดี มีจุดเล็กน้อยเรื่องหน่วย"),
        (m54_id, "เคมี", "อัตราการเกิดปฏิกิริยา", 16, "วิเคราะห์ข้อมูลได้ดี"),
        (m54_id, "ชีววิทยา", "โครงสร้างและหน้าที่ของเซลล์", 19, "ตอบครบและอธิบายเหตุผลชัดเจน"),
    ]
    for class_id, subject_name, title, score, feedback in preferred:
        a = cur.execute("""
            SELECT a.id, a.full_score FROM assignments a
            JOIN subjects s ON s.id=a.subject_id
            WHERE s.class_id=? AND s.name=? AND a.title=?
            ORDER BY a.id DESC LIMIT 1
        """, (class_id, subject_name, title)).fetchone()
        if not a:
            continue
        sub = cur.execute("SELECT id FROM submissions WHERE assignment_id=? AND student_id=?", (a[0], kanok_id)).fetchone()
        if not sub:
            sub_id = cur.execute("""
                INSERT INTO submissions (assignment_id,student_id,content,status)
                VALUES (?,?,?,'GRADED')
            """, (a[0], kanok_id, f"ส่งงาน{subject_name}เรื่อง {title} เรียบร้อยแล้วค่ะ")).lastrowid
        else:
            sub_id = sub[0]
            cur.execute("UPDATE submissions SET status='GRADED' WHERE id=?", (sub_id,))
        grade = cur.execute("SELECT id FROM grades WHERE submission_id=?", (sub_id,)).fetchone()
        if not grade:
            cur.execute("""
                INSERT INTO grades (submission_id,score,feedback,graded_by_id)
                VALUES (?,?,?,?)
            """, (sub_id, score, feedback, bio_id if subject_name == "ชีววิทยา" else suthep_id))

    # One more submitted-but-not-yet-graded assignment for Kanokporn.
    waiting = cur.execute("""
        SELECT a.id FROM assignments a JOIN subjects s ON s.id=a.subject_id
        WHERE s.class_id=? AND s.name='ภาษาอังกฤษ'
        ORDER BY a.id DESC LIMIT 1
    """, (m54_id,)).fetchone()
    if waiting:
        exists = cur.execute("SELECT id FROM submissions WHERE assignment_id=? AND student_id=?", (waiting[0], kanok_id)).fetchone()
        if not exists:
            cur.execute("""
                INSERT INTO submissions (assignment_id,student_id,content,status)
                VALUES (?,?,?,'SUBMITTED')
            """, (waiting[0], kanok_id, "ส่งงานภาษาอังกฤษแล้วค่ะ รอคุณครูตรวจ"))

    # Keep Montol's biology submission attached to the biology teacher's M.4 work.
    bio_a = cur.execute("""
        SELECT a.id FROM assignments a JOIN subjects s ON s.id=a.subject_id
        WHERE s.class_id=? AND s.name='ชีววิทยา'
        ORDER BY a.id ASC LIMIT 1
    """, (m44_id,)).fetchone()
    if bio_a:
        sub = cur.execute("SELECT id FROM submissions WHERE assignment_id=? AND student_id=?", (bio_a[0], montol_id)).fetchone()
        if not sub:
            sub_id = cur.execute("""
                INSERT INTO submissions (assignment_id,student_id,content,status)
                VALUES (?,?,?,'GRADED')
            """, (bio_a[0], montol_id, "ส่งงานชีววิทยาแล้วครับ")).lastrowid
            cur.execute("""
                INSERT INTO grades (submission_id,score,feedback,graded_by_id)
                VALUES (?,?,?,?)
            """, (sub_id, 18, "ทำได้ดี อธิบายองค์ประกอบของเซลล์ได้ครบ", bio_id))
        else:
            # If the old submission was waiting, let the biology teacher see it as graded.
            cur.execute("UPDATE submissions SET status='GRADED' WHERE id=?", (sub[0],))
            if not cur.execute("SELECT id FROM grades WHERE submission_id=?", (sub[0],)).fetchone():
                cur.execute("""INSERT INTO grades (submission_id,score,feedback,graded_by_id)
                               VALUES (?,?,?,?)""", (sub[0], 18, "ทำได้ดี อธิบายองค์ประกอบของเซลล์ได้ครบ", bio_id))

    # Add a couple of assignments due within the next 2 days.
    due_soon = date.today() + timedelta(days=2)
    due_defs = [
        (m44_id, "ชีววิทยา", "ใบงานทบทวนชีววิทยา", "ทบทวนโครงสร้างและหน้าที่ของเซลล์ก่อนสอบ", bio_id, 20),
        (m54_id, "คณิตศาสตร์", "แบบฝึกหัดทบทวน ม.5", "ทบทวนลำดับและอนุกรมก่อนเรียนบทถัดไป", suthep_id, 20),
    ]
    due_assignment_ids = []
    for class_id, subject_name, title, desc, owner_id, score in due_defs:
        sr = cur.execute("SELECT id FROM subjects WHERE class_id=? AND name=?", (class_id, subject_name)).fetchone()
        if not sr:
            continue
        a = cur.execute("SELECT id FROM assignments WHERE subject_id=? AND title=?", (sr[0], title)).fetchone()
        if not a:
            a_id = cur.execute("""
                INSERT INTO assignments (subject_id,created_by_id,title,description,due_date,full_score)
                VALUES (?,?,?,?,?,?)
            """, (sr[0], owner_id, title, desc, due_soon.isoformat(), score)).lastrowid
        else:
            a_id = a[0]
            cur.execute("UPDATE assignments SET due_date=?, created_by_id=? WHERE id=?", (due_soon.isoformat(), owner_id, a_id))
        due_assignment_ids.append((a_id, subject_name, title, class_id))

    # Notify every account about work due within the next 2 days. Avoid duplicates.
    users = cur.execute("SELECT id FROM users").fetchall()
    for a_id, subject_name, title, class_id in due_assignment_ids:
        class_name = cur.execute("SELECT name FROM classes WHERE id=?", (class_id,)).fetchone()[0]
        msg = f"{class_name}: {title} ({subject_name}) ต้องส่งภายใน 2 วัน — กำหนด {fmt_date(due_soon.isoformat())}"
        for u in users:
            exists = cur.execute("""
                SELECT id FROM notifications
                WHERE user_id=? AND related_assignment_id=? AND type='DUE_SOON'
            """, (u[0], a_id)).fetchone()
            if not exists:
                cur.execute("""
                    INSERT INTO notifications (user_id,title,message,type,related_assignment_id)
                    VALUES (?,?,?,?,?)
                """, (u[0], "งานใกล้ครบกำหนด", msg, "DUE_SOON", a_id))

    db.commit()

def cleanup_and_expand_demo_data(db):
    """Final demo cleanup: remove duplicate biology work, populate M.4/4 submissions,
    and keep the advisor strictly read-only."""
    cur = db.cursor()

    bio = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("umaphorn@school.ac.th",)).fetchone()
    m44 = cur.execute("SELECT id FROM classes WHERE name='ม.4/4' LIMIT 1").fetchone()
    if not bio or not m44:
        return
    bio_id, m44_id = bio[0], m44[0]

    # 1) Biology: keep exactly ONE assignment for each title in BOTH M.4/4 and M.5/4.
    # If older versions created duplicates, move useful submissions to the
    # oldest copy and then remove the duplicate assignment safely.
    for class_name in ("ม.4/4", "ม.5/4"):
        class_row = cur.execute("SELECT id FROM classes WHERE name=? LIMIT 1", (class_name,)).fetchone()
        if not class_row:
            continue
        bio_subjects = cur.execute(
            "SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา'", (class_row[0],)
        ).fetchall()
        for sr in bio_subjects:
            assignments = cur.execute(
                "SELECT id,title FROM assignments WHERE subject_id=? ORDER BY id ASC", (sr['id'],)
            ).fetchall()
            by_title = {}
            for a in assignments:
                by_title.setdefault(a['title'], []).append(a['id'])
            for title, ids in by_title.items():
                if len(ids) <= 1:
                    continue
                keeper = ids[0]
                for dup in ids[1:]:
                    dup_subs = cur.execute("SELECT id,student_id FROM submissions WHERE assignment_id=?", (dup,)).fetchall()
                    for sub in dup_subs:
                        existing = cur.execute(
                            "SELECT id FROM submissions WHERE assignment_id=? AND student_id=?",
                            (keeper, sub['student_id'])
                        ).fetchone()
                        if existing:
                            eg = cur.execute("SELECT id FROM grades WHERE submission_id=?", (existing[0],)).fetchone()
                            dg = cur.execute("SELECT * FROM grades WHERE submission_id=?", (sub['id'],)).fetchone()
                            if dg and not eg:
                                cur.execute("UPDATE grades SET submission_id=? WHERE id=?", (existing[0], dg['id']))
                            elif dg and eg:
                                cur.execute("DELETE FROM grades WHERE id=?", (dg['id'],))
                            cur.execute("DELETE FROM submissions WHERE id=?", (sub['id'],))
                        else:
                            cur.execute("UPDATE submissions SET assignment_id=? WHERE id=?", (keeper, sub['id']))
                    cur.execute("DELETE FROM assignments WHERE id=?", (dup,))
                cur.execute("UPDATE assignments SET created_by_id=? WHERE id=?", (bio_id, keeper))

    # 2) Make sure the five M.4/4 students all have realistic submitted work.
    students = cur.execute("""
        SELECT u.id, u.name FROM users u
        JOIN enrollments e ON e.student_id=u.id
        WHERE e.class_id=? AND u.role='STUDENT'
        ORDER BY u.id
    """, (m44_id,)).fetchall()

    # Use one common assignment per subject. Biology is owned by the biology teacher.
    subject_names = ["คณิตศาสตร์", "ฟิสิกส์", "เคมี", "ชีววิทยา", "ภาษาอังกฤษ", "ภาษาไทย"]
    sample_text = {
        "คณิตศาสตร์": "ส่งแบบฝึกหัดคณิตศาสตร์แล้วครับ",
        "ฟิสิกส์": "ส่งแบบฝึกหัดฟิสิกส์แล้วครับ",
        "เคมี": "ส่งแบบฝึกหัดเคมีแล้วครับ",
        "ชีววิทยา": "ส่งงานชีววิทยาแล้วครับ",
        "ภาษาอังกฤษ": "ส่งแบบฝึกหัดภาษาอังกฤษแล้วครับ",
        "ภาษาไทย": "ส่งแบบฝึกหัดภาษาไทยแล้วครับ",
    }
    for subject_name in subject_names:
        sr = cur.execute("SELECT id FROM subjects WHERE class_id=? AND name=?", (m44_id, subject_name)).fetchone()
        if not sr:
            continue
        a = cur.execute(
            "SELECT id,full_score FROM assignments WHERE subject_id=? ORDER BY id ASC LIMIT 1", (sr[0],)
        ).fetchone()
        if not a:
            continue
        for idx, student in enumerate(students):
            sub = cur.execute(
                "SELECT id FROM submissions WHERE assignment_id=? AND student_id=?",
                (a['id'], student['id'])
            ).fetchone()
            if not sub:
                sub_id = cur.execute("""
                    INSERT INTO submissions (assignment_id,student_id,content,status)
                    VALUES (?,?,?,'SUBMITTED')
                """, (a['id'], student['id'], sample_text[subject_name])).lastrowid
            else:
                sub_id = sub['id']

            # Give some students grades so the teacher can see both graded and waiting work.
            should_grade = (subject_name != 'ชีววิทยา' and idx in (0, 2, 4)) or (subject_name == 'ชีววิทยา' and idx in (0, 3))
            if should_grade and not cur.execute("SELECT id FROM grades WHERE submission_id=?", (sub_id,)).fetchone():
                score = max(1, int(float(a['full_score']) - (idx + 1)))
                cur.execute("""
                    INSERT INTO grades (submission_id,score,feedback,graded_by_id)
                    VALUES (?,?,?,?)
                """, (sub_id, score, "ทำได้ดี มีรายละเอียดครบถ้วน", bio_id if subject_name == 'ชีววิทยา' else cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("suthep@school.ac.th",)).fetchone()[0]))
                cur.execute("UPDATE submissions SET status='GRADED' WHERE id=?", (sub_id,))

    # 3) Advisor is view-only. Keep him as owner of M.4/4 for room/advisor context,
    # but all biology assignments remain owned by the biology teacher.
    suthep = cur.execute("SELECT id FROM users WHERE lower(email)=lower(?)", ("suthep@school.ac.th",)).fetchone()
    if suthep:
        cur.execute("UPDATE classes SET teacher_id=?, homeroom_teacher_name=? WHERE id=?", (suthep[0], "ครูสุเทพ ชื่นบาน", m44_id))
        cur.execute("""
            UPDATE assignments SET created_by_id=?
            WHERE subject_id IN (SELECT id FROM subjects WHERE class_id=? AND name='ชีววิทยา')
        """, (bio_id, m44_id))

    db.commit()

def current_user():
    uid = session.get("uid")
    if not uid:
        return None
    return get_db().execute(
        "SELECT * FROM users WHERE id=?", (uid,)
    ).fetchone()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not current_user():
            return redirect(url_for("login"))
        return fn(*args, **kwargs)
    return wrapper

def role_required(role):
    def deco(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            u = current_user()
            if not u:
                return redirect(url_for("login"))
            if u["role"] != role:
                return redirect(url_for("home"))
            return fn(*args, **kwargs)
        return wrapper
    return deco

def status_of(assignment, submission, grade):
    today = date.today()
    due = date.fromisoformat(assignment["due_date"])

    if grade is not None:
        return "GRADED"
    if submission is not None:
        return "WAITING"
    if due < today:
        return "OVERDUE"
    if due == today:
        return "DUE_TODAY"
    return "UPCOMING"

STATUS_LABEL = {
    "GRADED": "ตรวจแล้ว",
    "WAITING": "รอตรวจ",
    "OVERDUE": "เกินกำหนด",
    "DUE_TODAY": "ครบกำหนดวันนี้",
    "UPCOMING": "กำลังจะถึง",
}

def fmt_date(s):
    d = date.fromisoformat(s)
    months = [
        "ม.ค.", "ก.พ.", "มี.ค.", "เม.ย.", "พ.ค.", "มิ.ย.",
        "ก.ค.", "ส.ค.", "ก.ย.", "ต.ค.", "พ.ย.", "ธ.ค."
    ]
    return f"{d.day} {months[d.month-1]} {d.year}"

def fmt_dt(s):
    d = datetime.fromisoformat(s)
    return d.strftime("%d %b %Y %H:%M")

app.jinja_env.globals.update(
    current_user=current_user,
    STATUS_LABEL=STATUS_LABEL,
    fmt_date=fmt_date,
    fmt_dt=fmt_dt,
)

BASE = """
<!doctype html>
<html lang="th">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{% block title %}ติดตามงานและคะแนน{% endblock %}</title>
<style>
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,"Segoe UI",sans-serif;background:#f6f7fb;color:#1f2937}
a{color:#2563eb;text-decoration:none}
.layout{display:flex;min-height:100vh}
.sidebar{width:220px;background:#fff;border-right:1px solid #e5e7eb;padding:16px;position:sticky;top:0;height:100vh}
.sidebar h1{font-size:16px;margin:0 0 20px}
.sidebar a.nav{display:block;padding:10px 12px;border-radius:8px;color:#374151;margin-bottom:4px}
.sidebar a.nav:hover{background:#f3f4f6}
.sidebar a.nav.active{background:#2563eb;color:#fff}
.sidebar .logout{margin-top:20px;color:#dc2626}
.main{flex:1;padding:28px;max-width:1100px}
.topbar{display:flex;justify-content:flex-end;margin-bottom:20px;gap:12px;align-items:center}
h2{margin:0 0 16px}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(160px,1fr));gap:12px}
.card{background:#fff;border:1px solid #e5e7eb;border-radius:10px;padding:16px}
.card .label{font-size:12px;color:#6b7280}
.card .value{font-size:24px;font-weight:700;margin-top:4px}
.list{background:#fff;border:1px solid #e5e7eb;border-radius:10px;overflow:hidden}
.list .row{padding:14px 16px;border-bottom:1px solid #f3f4f6;display:flex;justify-content:space-between;gap:12px}
.list .row:last-child{border-bottom:none}
.muted{color:#6b7280;font-size:13px}
.pill{display:inline-block;padding:2px 10px;border-radius:999px;font-size:12px;font-weight:600}
.pill.GRADED{background:#dcfce7;color:#15803d}
.pill.WAITING{background:#e0f2fe;color:#0369a1}
.pill.OVERDUE{background:#fee2e2;color:#b91c1c}
.pill.DUE_TODAY{background:#fef3c7;color:#b45309}
.pill.UPCOMING{background:#f3f4f6;color:#374151}
table{width:100%;border-collapse:collapse;background:#fff}
th,td{padding:12px 16px;text-align:left;border-bottom:1px solid #f3f4f6}
th{font-size:12px;color:#6b7280;font-weight:600}
.btn{display:inline-block;padding:8px 14px;border-radius:8px;background:#2563eb;color:#fff;border:none;cursor:pointer;font-size:14px}
.btn.secondary{background:#fff;color:#374151;border:1px solid #e5e7eb}
.btn.danger{background:#dc2626}
.btn.small{padding:5px 10px;font-size:12px}
input,textarea,select{width:100%;padding:9px 12px;border:1px solid #d1d5db;border-radius:8px;font-size:14px;margin-bottom:12px}
label{font-size:13px;font-weight:600;display:block;margin-bottom:4px}
.form{max-width:560px;background:#fff;padding:24px;border-radius:12px;border:1px solid #e5e7eb}
.auth-wrap{display:flex;align-items:center;justify-content:center;min-height:100vh}
.feedback{background:#f3f4f6;border-radius:8px;padding:10px 12px;margin-top:8px;font-size:13px}
.section{margin-bottom:28px}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:20px}
.alert{padding:10px 14px;border-radius:8px;background:#fff7ed;color:#9a3412;margin-bottom:15px}
@media(max-width:800px){
 .layout{flex-direction:column}
 .sidebar{width:100%;height:auto;position:static;display:flex;flex-wrap:wrap;gap:6px}
 .sidebar h1{width:100%}
 .grid2{grid-template-columns:1fr}
}

/* ===== Dark mode ===== */
body.dark{
  background:#111827;
  color:#e5e7eb;
}
body.dark a{color:#60a5fa}
body.dark .sidebar{
  background:#1f2937;
  border-right-color:#374151;
}
body.dark .sidebar a.nav{color:#d1d5db}
body.dark .sidebar a.nav:hover{background:#374151}
body.dark .sidebar a.nav.active{background:#2563eb;color:#fff}
body.dark .sidebar .logout{color:#f87171}
body.dark .card,
body.dark .list,
body.dark table,
body.dark .form{
  background:#1f2937;
  border-color:#374151;
}
body.dark .card .label,
body.dark .muted,
body.dark th{color:#9ca3af}
body.dark .list .row,
body.dark th,
body.dark td{border-color:#374151}
body.dark input,
body.dark textarea,
body.dark select{
  background:#111827;
  color:#e5e7eb;
  border-color:#4b5563;
}
body.dark input::placeholder,
body.dark textarea::placeholder{color:#6b7280}
body.dark .btn.secondary{
  background:#1f2937;
  color:#e5e7eb;
  border-color:#4b5563;
}
body.dark .feedback{background:#374151}
body.dark .alert{background:#431407;color:#fdba74}
body.dark .pill.UPCOMING{background:#374151;color:#d1d5db}
body.dark .pill.WAITING{background:#0c4a6e;color:#bae6fd}
body.dark .pill.GRADED{background:#14532d;color:#bbf7d0}
body.dark .pill.OVERDUE{background:#450a0a;color:#fecaca}
body.dark .pill.DUE_TODAY{background:#451a03;color:#fde68a}

.theme-toggle{
  position:fixed;
  right:18px;
  bottom:18px;
  z-index:9999;
  width:46px;
  height:46px;
  border:1px solid #d1d5db;
  border-radius:50%;
  background:#fff;
  color:#111827;
  cursor:pointer;
  font-size:20px;
  box-shadow:0 4px 14px rgba(0,0,0,.12);
}
body.dark .theme-toggle{
  background:#1f2937;
  color:#f9fafb;
  border-color:#4b5563;
}

</style>
</head>
<body>
<button class="theme-toggle" id="themeToggle" type="button" aria-label="เปลี่ยนโหมดสี">🌙</button>
<script>
(function(){
  const saved = localStorage.getItem("schoolTheme");
  if(saved === "dark") document.body.classList.add("dark");

  const btn = document.getElementById("themeToggle");
  function updateIcon(){
    btn.textContent = document.body.classList.contains("dark") ? "☀️" : "🌙";
    btn.title = document.body.classList.contains("dark")
      ? "เปลี่ยนเป็นโหมดสว่าง"
      : "เปลี่ยนเป็นโหมดมืด";
  }
  updateIcon();

  btn.addEventListener("click", function(){
    document.body.classList.toggle("dark");
    localStorage.setItem(
      "schoolTheme",
      document.body.classList.contains("dark") ? "dark" : "light"
    );
    updateIcon();
  });
})();
</script>

{% if current_user() %}
<div class="layout">
<aside class="sidebar">
<h1>ติดตามงานและคะแนน</h1>
{% if current_user().role == 'STUDENT' %}
<a class="nav {{ 'active' if active=='dashboard' }}" href="/student/dashboard">แดชบอร์ด</a>
<a class="nav {{ 'active' if active=='assignments' }}" href="/student/assignments">งานทั้งหมด</a>
<a class="nav {{ 'active' if active=='grades' }}" href="/student/grades">คะแนน</a>
<a class="nav {{ 'active' if active=='notifications' }}" href="/notifications">แจ้งเตือน</a>
<a class="nav {{ 'active' if active=='profile' }}" href="/student/profile">โปรไฟล์</a>
{% else %}
<a class="nav {{ 'active' if active=='dashboard' }}" href="/teacher/dashboard">แดชบอร์ด</a>
<a class="nav {{ 'active' if active=='classes' }}" href="/teacher/classes">ชั้นเรียน</a>
<a class="nav {{ 'active' if active=='assignments' }}" href="/teacher/assignments">งาน</a>
<a class="nav {{ 'active' if active=='notifications' }}" href="/notifications">แจ้งเตือน</a>
{% endif %}
<a class="nav logout" href="/logout">ออกจากระบบ</a>
</aside>
<main class="main">
<div class="topbar">
<span class="muted">{{ current_user().name }} · {{ 'ครู' if current_user().role=='TEACHER' else 'นักเรียน' }}</span>
</div>
{% with messages = get_flashed_messages() %}
{% if messages %}
{% for message in messages %}<div class="alert">{{ message }}</div>{% endfor %}
{% endif %}
{% endwith %}
{% block content %}{% endblock %}
</main>
</div>
{% else %}
{% block auth %}{% endblock %}
{% endif %}
</body>
</html>
"""

LOGIN = """
{% extends "base" %}
{% block title %}เข้าสู่ระบบ{% endblock %}
{% block auth %}
<div class="auth-wrap">
<div class="form">
<h2>เข้าสู่ระบบ</h2>
{% if error %}<p style="color:#dc2626">{{ error }}</p>{% endif %}
<form method="post">
<label>อีเมล</label><input name="email" type="email" required>
<label>รหัสผ่าน</label><input name="password" type="password" required>
<button class="btn" style="width:100%">เข้าสู่ระบบ</button>
</form>
<p class="muted" style="margin-top:12px">ยังไม่มีบัญชี? <a href="/register">สมัครสมาชิก</a></p>
<p class="muted">ทดสอบ: suthep@school.ac.th / 1234 (ครูที่ปรึกษา ม.4/4) · umaphorn@school.ac.th / 1234 (ครูชีววิทยา) · montol@school.ac.th / 1234 (ม.4/4) · kanokporn@school.ac.th / 1234 (ม.5/4)</p>
</div>
</div>
{% endblock %}
"""

REGISTER = """
{% extends "base" %}
{% block title %}สมัครสมาชิก{% endblock %}
{% block auth %}
<div class="auth-wrap">
<div class="form">
<h2>สมัครสมาชิก</h2>
{% if error %}<p style="color:#dc2626">{{ error }}</p>{% endif %}
<form method="post">
<label>ชื่อ</label><input name="name" required>
<label>อีเมล</label><input name="email" type="email" required>
<label>รหัสผ่าน</label><input name="password" type="password" required>
<label>บทบาท</label>
<select name="role"><option value="STUDENT">นักเรียน</option><option value="TEACHER">ครู</option></select>
<button class="btn" style="width:100%">สมัครสมาชิก</button>
</form>
<p class="muted" style="margin-top:12px">มีบัญชีแล้ว? <a href="/login">เข้าสู่ระบบ</a></p>
</div>
</div>
{% endblock %}
"""

STUDENT_DASHBOARD = """
{% extends "base" %}
{% block content %}
<h2>แดชบอร์ด</h2>
<div class="cards">
<div class="card"><div class="label">งานทั้งหมด</div><div class="value">{{ stats.total }}</div></div>
<div class="card"><div class="label">รอดำเนินการ</div><div class="value">{{ stats.pending }}</div></div>
<div class="card"><div class="label">ใกล้ถึงกำหนด</div><div class="value">{{ stats.upcoming }}</div></div>
<div class="card"><div class="label">ส่งแล้ว</div><div class="value">{{ stats.submitted }}</div></div>
<div class="card"><div class="label">ตรวจแล้ว</div><div class="value">{{ stats.graded }}</div></div>
<div class="card"><div class="label">เกินกำหนด</div><div class="value">{{ stats.overdue }}</div></div>
</div>
<div class="section" style="margin-top:28px">
<h2>คะแนนล่าสุด</h2>
<div class="list">
{% for g in recent_grades %}
<div class="row"><div><b>{{ g.title }}</b><div class="muted">{{ g.subject_name }} · {{ fmt_dt(g.graded_at) }}</div></div><div><b>{{ g.score }}/{{ g.full_score }}</b></div></div>
{% else %}<div class="row"><span class="muted">ยังไม่มีคะแนน</span></div>{% endfor %}
</div>
</div>
<div class="section">
<h2>การแจ้งเตือนล่าสุด</h2>
<div class="list">
{% for n in recent_notifications %}
<div class="row"><div><b>{{ n.title }}</b>{% if n.message %}<div class="muted">{{ n.message }}</div>{% endif %}</div></div>
{% else %}<div class="row"><span class="muted">ไม่มีการแจ้งเตือน</span></div>{% endfor %}
</div>
</div>
{% endblock %}
"""

STUDENT_ASSIGNMENTS = """
{% extends "base" %}
{% block content %}
<h2>งานทั้งหมด</h2>
<div class="list">
{% for a in assignments %}
<a class="row" href="/student/assignments/{{ a.assignment_id }}" style="color:inherit">
<div><b>{{ a.title }}</b><div class="muted">{{ a.subject_name }} · กำหนด {{ fmt_date(a.due_date) }}</div></div>
<div><span class="pill {{ a.status }}">{{ STATUS_LABEL[a.status] }}</span>{% if a.status == 'GRADED' %}<div class="muted">{{ a.score }}/{{ a.full_score }}</div>{% endif %}</div>
</a>
{% else %}<div class="row"><span class="muted">ไม่พบงาน</span></div>{% endfor %}
</div>
{% endblock %}
"""

STUDENT_ASSIGNMENT_DETAIL = """
{% extends "base" %}
{% block content %}
<a href="/student/assignments">&larr; งานทั้งหมด</a>
<h2 style="margin-top:8px">{{ a.title }} <span class="pill {{ status }}">{{ STATUS_LABEL[status] }}</span></h2>
<p class="muted">{{ a.subject_name }} · {{ a.class_name }} · คะแนนเต็ม {{ a.full_score }} · กำหนด {{ fmt_date(a.due_date) }}</p>
<p>{{ a.description or 'ไม่มีรายละเอียดเพิ่มเติม' }}</p>
<div class="section">
<h2>ส่งงานของคุณ</h2>
{% if submission %}
<div class="feedback">ส่งเมื่อ {{ fmt_dt(submission.submitted_at) }}<br>{{ submission.content or '' }}</div>
{% if grade %}
<div class="feedback" style="background:#dcfce7"><b>คะแนน {{ grade.score }}/{{ a.full_score }}</b><br>{% if grade.feedback %}ติชม: {{ grade.feedback }}{% endif %}</div>
{% else %}<p class="muted">รอครูตรวจงานอยู่</p>{% endif %}
{% else %}
<form method="post">
<label>เนื้อหางาน</label><textarea name="content" rows="5" required></textarea>
<button class="btn">ส่งงาน</button>
</form>
{% endif %}
</div>
{% endblock %}
"""

STUDENT_GRADES = """
{% extends "base" %}
{% block content %}
<h2>คะแนน</h2>
<div class="list">
{% for g in grades %}
<div class="row">
<div><b>{{ g.title }}</b><div class="muted">{{ g.subject_name }} · {{ g.class_name }}</div>
{% if g.feedback %}<div class="feedback">ติชม: {{ g.feedback }}</div>{% endif %}</div>
<div style="text-align:right"><b>{{ g.score }}/{{ g.full_score }}</b><div class="muted">{{ (g.score / g.full_score * 100)|round(0)|int }}%</div></div>
</div>
{% else %}<div class="row"><span class="muted">ยังไม่มีคะแนน</span></div>{% endfor %}
</div>
{% endblock %}
"""

PROFILE = """
{% extends "base" %}
{% block content %}
<h2>โปรไฟล์</h2>
<div class="form">
<label>ชื่อ</label><p>{{ user.name }}</p>
<label>อีเมล</label><p>{{ user.email }}</p>
<label>บทบาท</label><p>{{ "นักเรียน" if user.role=="STUDENT" else "ครู" }}</p>
{% if user.role=="STUDENT" %}
<label>ห้องเรียน</label><p>{{ class_name or "ยังไม่ได้เข้าชั้นเรียน" }}</p>
{% endif %}
</div>
{% endblock %}
"""

NOTIFICATIONS = """
{% extends "base" %}
{% block content %}
<h2>แจ้งเตือน</h2>
<div class="list">
{% for n in notifications %}
<div class="row"><div><b>{{ n.title }}</b><div class="muted">{{ fmt_dt(n.created_at) }}</div>{% if n.message %}<div>{{ n.message }}</div>{% endif %}</div></div>
{% else %}<div class="row"><span class="muted">ไม่มีการแจ้งเตือน</span></div>{% endfor %}
</div>
{% endblock %}
"""

TEACHER_DASHBOARD = """
{% extends "base" %}
{% block content %}
<h2>แดชบอร์ดครู</h2>
<div class="cards">
<div class="card"><div class="label">ชั้นเรียน</div><div class="value">{{ stats.classes }}</div></div>
<div class="card"><div class="label">งานทั้งหมด</div><div class="value">{{ stats.assignments }}</div></div>
<div class="card"><div class="label">งานที่ส่งแล้ว</div><div class="value">{{ stats.submissions }}</div></div>
<div class="card"><div class="label">รอตรวจ</div><div class="value">{{ stats.waiting }}</div></div>
</div>
<div class="section" style="margin-top:28px">
<h2>งานล่าสุดที่รอตรวจ</h2>
<div class="list">
{% for s in waiting %}
<div class="row">
<div><b>{{ s.student_name }}</b><div class="muted">{{ s.title }} · {{ s.subject_name }}</div></div>
{% if not is_advisor %}<a class="btn small" href="/teacher/submissions/{{ s.submission_id }}">ตรวจงาน</a>{% else %}<span class="muted">ดูอย่างเดียว</span>{% endif %}
</div>
{% else %}<div class="row"><span class="muted">ไม่มีงานรอตรวจ</span></div>{% endfor %}
</div>
</div>
{% endblock %}
"""

TEACHER_CLASSES = """
{% extends "base" %}
{% block content %}
<h2>ชั้นเรียน</h2>
<div class="list">
{% for c in classes %}
<div class="row">
<div><b>{{ c.name }}</b><div class="muted">{{ c.description }}</div><div class="muted">รหัสเข้าห้อง: {{ c.join_code }} · นักเรียน {{ c.student_count }} คน</div></div>
<a class="btn small" href="/teacher/classes/{{ c.id }}">ดูห้อง</a>
</div>
{% endfor %}
</div>
{% endblock %}
"""

TEACHER_CLASS_DETAIL = """
{% extends "base" %}
{% block content %}
<a href="/teacher/classes">&larr; ชั้นเรียน</a>
<h2 style="margin-top:8px">{{ c.name }}</h2>
<p class="muted">{{ c.description }} · รหัสเข้าห้อง {{ c.join_code }}</p>
<h2>นักเรียน</h2>
<div class="list">
{% for s in students %}
<div class="row"><div><b>{{ s.name }}</b><div class="muted">{{ s.email }}</div></div></div>
{% else %}<div class="row"><span class="muted">ยังไม่มีนักเรียน</span></div>{% endfor %}
</div>
{% endblock %}
"""

TEACHER_ASSIGNMENTS = """
{% extends "base" %}
{% block content %}
<div style="display:flex;justify-content:space-between;align-items:center;gap:10px">
<h2>งานทั้งหมด</h2>
{% if not is_advisor %}<a class="btn" href="/teacher/assignments/new">+ สร้างงาน</a>{% else %}<span class="muted">โหมดครูที่ปรึกษา · ดูอย่างเดียว</span>{% endif %}
</div>
<div class="list">
{% for a in assignments %}
<div class="row">
<div><b>{{ a.title }}</b><div class="muted">{{ a.subject_name }} · {{ a.class_name }} · กำหนด {{ fmt_date(a.due_date) }} · เต็ม {{ a.full_score }}</div></div>
<div><a class="btn small" href="/teacher/assignments/{{ a.id }}">ดูงาน</a></div>
</div>
{% else %}<div class="row"><span class="muted">ยังไม่มีงาน</span></div>{% endfor %}
</div>
{% endblock %}
"""

TEACHER_ASSIGNMENT_DETAIL = """
{% extends "base" %}
{% block content %}
<a href="/teacher/assignments">&larr; งานทั้งหมด</a>
<h2 style="margin-top:8px">{{ a.title }}</h2>
<p class="muted">{{ a.subject_name }} · {{ a.class_name }} · กำหนด {{ fmt_date(a.due_date) }} · คะแนนเต็ม {{ a.full_score }}</p>
<p>{{ a.description or 'ไม่มีรายละเอียด' }}</p>
<h2>การส่งงาน</h2>
<div class="list">
{% for s in submissions %}
<div class="row">
<div><b>{{ s.student_name }}</b><div class="muted">ส่งเมื่อ {{ fmt_dt(s.submitted_at) }}</div><div>{{ s.content or '' }}</div>{% if s.score is not none %}<div class="feedback">คะแนน {{ s.score }}/{{ a.full_score }}{% if s.feedback %} · {{ s.feedback }}{% endif %}</div>{% endif %}</div>
{% if s.score is none and not is_advisor %}<a class="btn small" href="/teacher/submissions/{{ s.submission_id }}">ตรวจ</a>{% elif s.score is none and is_advisor %}<span class="muted">รอตรวจ</span>{% endif %}
</div>
{% else %}<div class="row"><span class="muted">ยังไม่มีนักเรียนส่งงาน</span></div>{% endfor %}
</div>
{% endblock %}
"""

TEACHER_NEW_ASSIGNMENT = """
{% extends "base" %}
{% block content %}
<h2>สร้างงานใหม่</h2>
<form class="form" method="post">
<label>วิชา</label>
<select name="subject_id" required>
{% for s in subjects %}<option value="{{ s.id }}">{{ s.class_name }} · {{ s.name }}</option>{% endfor %}
</select>
<label>ชื่องาน</label><input name="title" required>
<label>รายละเอียด</label><textarea name="description" rows="5"></textarea>
<label>วันครบกำหนด</label><input name="due_date" type="date" required>
<label>คะแนนเต็ม</label><input name="full_score" type="number" min="0.1" step="0.1" value="100" required>
<button class="btn">สร้างงาน</button>
<a class="btn secondary" href="/teacher/assignments">ยกเลิก</a>
</form>
{% endblock %}
"""

TEACHER_GRADE = """
{% extends "base" %}
{% block content %}
<a href="/teacher/assignments/{{ a.id }}">&larr; กลับไปงาน</a>
<h2 style="margin-top:8px">ตรวจงาน</h2>
<div class="card" style="margin-bottom:20px">
<b>{{ s.student_name }}</b>
<div class="muted">{{ a.title }} · {{ a.subject_name }}</div>
<p>{{ s.content or 'ไม่มีเนื้อหา' }}</p>
</div>
<form class="form" method="post">
<label>คะแนน (เต็ม {{ a.full_score }})</label>
<input name="score" type="number" min="0" max="{{ a.full_score }}" step="0.1" value="{{ s.score if s.score is not none else '' }}" required>
<label>ความคิดเห็น</label>
<textarea name="feedback" rows="5">{{ s.feedback or '' }}</textarea>
<button class="btn">บันทึกคะแนน</button>
</form>
{% endblock %}
"""

TEMPLATES = {
    "base": BASE,
    "login": LOGIN,
    "register": REGISTER,
    "student_dashboard": STUDENT_DASHBOARD,
    "student_assignments": STUDENT_ASSIGNMENTS,
    "student_assignment_detail": STUDENT_ASSIGNMENT_DETAIL,
    "student_grades": STUDENT_GRADES,
    "profile": PROFILE,
    "notifications": NOTIFICATIONS,
    "teacher_dashboard": TEACHER_DASHBOARD,
    "teacher_classes": TEACHER_CLASSES,
    "teacher_class_detail": TEACHER_CLASS_DETAIL,
    "teacher_assignments": TEACHER_ASSIGNMENTS,
    "teacher_assignment_detail": TEACHER_ASSIGNMENT_DETAIL,
    "teacher_new_assignment": TEACHER_NEW_ASSIGNMENT,
    "teacher_grade": TEACHER_GRADE,
}

app.jinja_loader = DictLoader(TEMPLATES)

@app.context_processor
def inject_templates():
    return {}

def render(name, **kwargs):
    return render_template_string(
        TEMPLATES[name], **kwargs
    )

@app.route("/")
def home():
    u = current_user()
    if not u:
        return redirect(url_for("login"))
    if u["role"] == "TEACHER":
        return redirect(url_for("teacher_dashboard"))
    return redirect(url_for("student_dashboard"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        user = get_db().execute(
            "SELECT * FROM users WHERE lower(email)=?",
            (email,)
        ).fetchone()

        if not user or user["password"] != hashpw(password):
            return render("login", error="อีเมลหรือรหัสผ่านไม่ถูกต้อง")

        session.clear()
        session["uid"] = user["id"]
        return redirect(url_for("home"))

    return render("login", error=None)

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        role = request.form.get("role", "STUDENT")

        if not name or not email or not password:
            return render("register", error="กรุณากรอกข้อมูลให้ครบ")

        if role not in ("STUDENT", "TEACHER"):
            role = "STUDENT"

        db = get_db()
        try:
            db.execute(
                "INSERT INTO users (name,email,password,role) VALUES (?,?,?,?)",
                (name, email, hashpw(password), role)
            )
            db.commit()
        except sqlite3.IntegrityError:
            return render("register", error="อีเมลนี้มีบัญชีอยู่แล้ว")

        flash("สมัครสมาชิกสำเร็จ กรุณาเข้าสู่ระบบ")
        return redirect(url_for("login"))

    return render("register", error=None)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/student/dashboard")
@role_required("STUDENT")
def student_dashboard():
    db = get_db()
    uid = current_user()["id"]

    rows = db.execute("""
        SELECT a.*, s.name AS subject_name,
               sub.id AS submission_id, sub.submitted_at,
               g.score, g.id AS grade_id
        FROM assignments a
        JOIN subjects s ON s.id=a.subject_id
        JOIN classes c ON c.id=s.class_id
        JOIN enrollments e ON e.class_id=c.id
        LEFT JOIN submissions sub
          ON sub.assignment_id=a.id AND sub.student_id=?
        LEFT JOIN grades g ON g.submission_id=sub.id
        WHERE e.student_id=?
        ORDER BY a.due_date ASC
    """, (uid, uid)).fetchall()

    stats = {
        "total": len(rows),
        "pending": 0,
        "upcoming": 0,
        "submitted": 0,
        "graded": 0,
        "overdue": 0
    }

    for r in rows:
        status = status_of(r, r if r["submission_id"] else None,
                           r if r["grade_id"] else None)
        if status in ("UPCOMING", "DUE_TODAY", "OVERDUE"):
            if status == "UPCOMING":
                stats["upcoming"] += 1
            if status == "OVERDUE":
                stats["overdue"] += 1
            if status in ("UPCOMING", "DUE_TODAY", "OVERDUE"):
                stats["pending"] += 1
        if r["submission_id"]:
            stats["submitted"] += 1
        if r["grade_id"]:
            stats["graded"] += 1

    recent_grades = db.execute("""
        SELECT g.*, sub.subject_name, sub.title, sub.full_score
        FROM grades g
        JOIN (
            SELECT gr.id, s.name AS subject_name,
                   a.title, a.full_score, a.id AS assignment_id
            FROM grades gr
            JOIN submissions su ON su.id=gr.submission_id
            JOIN assignments a ON a.id=su.assignment_id
            JOIN subjects s ON s.id=a.subject_id
        ) sub ON sub.id=g.id
        WHERE EXISTS (
            SELECT 1 FROM submissions ss
            WHERE ss.id=g.submission_id AND ss.student_id=?
        )
        ORDER BY g.graded_at DESC LIMIT 5
    """, (uid,)).fetchall()

    recent_notifications = db.execute(
        """SELECT * FROM notifications
           WHERE user_id=? ORDER BY created_at DESC LIMIT 5""",
        (uid,)
    ).fetchall()

    return render(
        "student_dashboard",
        active="dashboard",
        stats=stats,
        recent_grades=recent_grades,
        recent_notifications=recent_notifications
    )

@app.route("/student/assignments")
@role_required("STUDENT")
def student_assignments():
    uid = current_user()["id"]
    rows = get_db().execute("""
        SELECT a.id AS assignment_id, a.title, a.description,
               a.due_date, a.full_score, s.name AS subject_name,
               c.name AS class_name, sub.id AS submission_id,
               g.id AS grade_id, g.score
        FROM assignments a
        JOIN subjects s ON s.id=a.subject_id
        JOIN classes c ON c.id=s.class_id
        JOIN enrollments e ON e.class_id=c.id
        LEFT JOIN submissions sub
          ON sub.assignment_id=a.id AND sub.student_id=?
        LEFT JOIN grades g ON g.submission_id=sub.id
        WHERE e.student_id=?
        ORDER BY a.due_date ASC, a.id DESC
    """, (uid, uid)).fetchall()

    assignments = []
    for r in rows:
        status = status_of(
            r,
            r if r["submission_id"] else None,
            r if r["grade_id"] else None
        )
        item = dict(r)
        item["status"] = status
        assignments.append(item)

    return render(
        "student_assignments",
        active="assignments",
        assignments=assignments
    )

@app.route("/student/assignments/<int:assignment_id>", methods=["GET", "POST"])
@role_required("STUDENT")
def student_assignment_detail(assignment_id):
    db = get_db()
    uid = current_user()["id"]

    a = db.execute("""
        SELECT a.*, s.name AS subject_name, c.name AS class_name
        FROM assignments a
        JOIN subjects s ON s.id=a.subject_id
        JOIN classes c ON c.id=s.class_id
        JOIN enrollments e ON e.class_id=c.id
        WHERE a.id=? AND e.student_id=?
    """, (assignment_id, uid)).fetchone()

    if not a:
        return "ไม่พบงาน", 404

    submission = db.execute("""
        SELECT * FROM submissions
        WHERE assignment_id=? AND student_id=?
    """, (assignment_id, uid)).fetchone()

    grade = None
    if submission:
        grade = db.execute(
            "SELECT * FROM grades WHERE submission_id=?",
            (submission["id"],)
        ).fetchone()

    if request.method == "POST":
        if submission:
            flash("งานนี้ถูกส่งไปแล้ว")
            return redirect(url_for(
                "student_assignment_detail",
                assignment_id=assignment_id
            ))

        content = request.form.get("content", "").strip()
        if not content:
            flash("กรุณากรอกเนื้อหางาน")
            return redirect(url_for(
                "student_assignment_detail",
                assignment_id=assignment_id
            ))

        db.execute("""
            INSERT INTO submissions
            (assignment_id,student_id,content,status)
            VALUES (?,?,?,'SUBMITTED')
        """, (assignment_id, uid, content))

        teacher_id = db.execute(
            "SELECT created_by_id FROM assignments WHERE id=?",
            (assignment_id,)
        ).fetchone()["created_by_id"]

        a_title = a["title"]
        db.execute("""
            INSERT INTO notifications
            (user_id,title,message,type,related_assignment_id)
            VALUES (?,?,?,?,?)
        """, (
            teacher_id,
            "มีนักเรียนส่งงาน",
            f"{current_user()['name']} ส่งงาน: {a_title}",
            "SUBMISSION",
            assignment_id
        ))

        db.commit()
        flash("ส่งงานเรียบร้อยแล้ว")
        return redirect(url_for(
            "student_assignment_detail",
            assignment_id=assignment_id
        ))

    status = status_of(
        a,
        submission,
        grade
    )

    return render(
        "student_assignment_detail",
        active="assignments",
        a=a,
        submission=submission,
        grade=grade,
        status=status
    )

@app.route("/student/grades")
@role_required("STUDENT")
def student_grades():
    uid = current_user()["id"]

    grades = get_db().execute("""
        SELECT g.*, a.title, a.full_score,
               s.name AS subject_name, c.name AS class_name
        FROM grades g
        JOIN submissions sub ON sub.id=g.submission_id
        JOIN assignments a ON a.id=sub.assignment_id
        JOIN subjects s ON s.id=a.subject_id
        JOIN classes c ON c.id=s.class_id
        WHERE sub.student_id=?
        ORDER BY g.graded_at DESC
    """, (uid,)).fetchall()

    return render(
        "student_grades",
        active="grades",
        grades=grades
    )

@app.route("/student/profile")
@role_required("STUDENT")
def student_profile():
    uid = current_user()["id"]
    db = get_db()

    class_row = db.execute("""
        SELECT c.name
        FROM classes c
        JOIN enrollments e ON e.class_id=c.id
        WHERE e.student_id=?
        ORDER BY c.id LIMIT 1
    """, (uid,)).fetchone()

    return render(
        "profile",
        active="profile",
        user=current_user(),
        class_name=class_row["name"] if class_row else None
    )

@app.route("/notifications")
@login_required
def notifications():
    uid = current_user()["id"]
    db = get_db()

    rows = db.execute(
        """SELECT * FROM notifications
           WHERE user_id=? ORDER BY created_at DESC""",
        (uid,)
    ).fetchall()

    db.execute(
        "UPDATE notifications SET is_read=1 WHERE user_id=?",
        (uid,)
    )
    db.commit()

    return render(
        "notifications",
        active="notifications",
        notifications=rows
    )

def is_advisor_teacher(uid):
    row = get_db().execute(
        "SELECT 1 FROM users WHERE id=? AND lower(email)=lower(?) AND role='TEACHER'",
        (uid, "suthep@school.ac.th")
    ).fetchone()
    return row is not None

def is_biology_teacher(uid):
    row = get_db().execute(
        "SELECT 1 FROM users WHERE id=? AND lower(email)=lower(?) AND role='TEACHER'",
        (uid, "umaphorn@school.ac.th")
    ).fetchone()
    return row is not None

@app.route("/teacher/dashboard")
@role_required("TEACHER")
def teacher_dashboard():
    db = get_db()
    uid = current_user()["id"]

    if is_biology_teacher(uid):
        classes = db.execute("""
            SELECT COUNT(DISTINCT c.id) AS n
            FROM classes c
            JOIN subjects s ON s.class_id=c.id
            WHERE s.name='ชีววิทยา'
        """).fetchone()["n"]
    else:
        classes = db.execute(
            "SELECT COUNT(*) AS n FROM classes WHERE teacher_id=?",
            (uid,)
        ).fetchone()["n"]

    if is_advisor_teacher(uid):
        scope = """
            JOIN subjects sx ON sx.id=a.subject_id
            WHERE sx.class_id=(SELECT id FROM classes WHERE name='ม.4/4' LIMIT 1)
        """
        assignments = db.execute(f"SELECT COUNT(*) AS n FROM assignments a {scope}").fetchone()["n"]
        submissions = db.execute(f"""
            SELECT COUNT(*) AS n FROM submissions sub
            JOIN assignments a ON a.id=sub.assignment_id
            {scope}
        """).fetchone()["n"]
        waiting_count = db.execute(f"""
            SELECT COUNT(*) AS n FROM submissions sub
            JOIN assignments a ON a.id=sub.assignment_id
            LEFT JOIN grades g ON g.submission_id=sub.id
            {scope} AND g.id IS NULL
        """).fetchone()["n"]
        waiting = db.execute(f"""
            SELECT sub.id AS submission_id, u.name AS student_name,
                   a.title, s.name AS subject_name
            FROM submissions sub
            JOIN users u ON u.id=sub.student_id
            JOIN assignments a ON a.id=sub.assignment_id
            JOIN subjects s ON s.id=a.subject_id
            LEFT JOIN grades g ON g.submission_id=sub.id
            {scope} AND g.id IS NULL
            ORDER BY sub.submitted_at DESC
            LIMIT 10
        """).fetchall()
    else:
        assignments = db.execute("""
            SELECT COUNT(*) AS n FROM assignments a WHERE a.created_by_id=?
        """, (uid,)).fetchone()["n"]
        submissions = db.execute("""
            SELECT COUNT(*) AS n FROM submissions sub
            JOIN assignments a ON a.id=sub.assignment_id
            WHERE a.created_by_id=?
        """, (uid,)).fetchone()["n"]
        waiting_count = db.execute("""
            SELECT COUNT(*) AS n FROM submissions sub
            JOIN assignments a ON a.id=sub.assignment_id
            LEFT JOIN grades g ON g.submission_id=sub.id
            WHERE a.created_by_id=? AND g.id IS NULL
        """, (uid,)).fetchone()["n"]
        waiting = db.execute("""
            SELECT sub.id AS submission_id, u.name AS student_name,
                   a.title, s.name AS subject_name
            FROM submissions sub
            JOIN users u ON u.id=sub.student_id
            JOIN assignments a ON a.id=sub.assignment_id
            JOIN subjects s ON s.id=a.subject_id
            LEFT JOIN grades g ON g.submission_id=sub.id
            WHERE a.created_by_id=? AND g.id IS NULL
            ORDER BY sub.submitted_at DESC
            LIMIT 10
        """, (uid,)).fetchall()

    return render(
        "teacher_dashboard",
        active="dashboard",
        stats={
            "classes": classes,
            "assignments": assignments,
            "submissions": submissions,
            "waiting": waiting_count
        },
        waiting=waiting,
        is_advisor=is_advisor_teacher(uid)
    )

@app.route("/teacher/classes")
@role_required("TEACHER")
def teacher_classes():
    uid = current_user()["id"]

    if is_biology_teacher(uid):
        classes = get_db().execute("""
            SELECT c.*, COUNT(e.id) AS student_count
            FROM classes c
            JOIN subjects s ON s.class_id=c.id AND s.name='ชีววิทยา'
            LEFT JOIN enrollments e ON e.class_id=c.id
            GROUP BY c.id
            ORDER BY c.id
        """).fetchall()
    else:
        classes = get_db().execute("""
            SELECT c.*,
                   COUNT(e.id) AS student_count
            FROM classes c
            LEFT JOIN enrollments e ON e.class_id=c.id
            WHERE c.teacher_id=?
            GROUP BY c.id
            ORDER BY c.id
        """, (uid,)).fetchall()

    return render(
        "teacher_classes",
        active="classes",
        classes=classes
    )

@app.route("/teacher/classes/<int:class_id>")
@role_required("TEACHER")
def teacher_class_detail(class_id):
    db = get_db()
    uid = current_user()["id"]

    if is_biology_teacher(uid):
        c = db.execute("""
            SELECT c.* FROM classes c
            JOIN subjects s ON s.class_id=c.id
            WHERE c.id=? AND s.name='ชีววิทยา'
            LIMIT 1
        """, (class_id,)).fetchone()
    else:
        c = db.execute(
            "SELECT * FROM classes WHERE id=? AND teacher_id=?",
            (class_id, uid)
        ).fetchone()

    if not c:
        return "ไม่พบชั้นเรียน", 404

    students = db.execute("""
        SELECT u.*
        FROM users u
        JOIN enrollments e ON e.student_id=u.id
        WHERE e.class_id=?
        ORDER BY u.name
    """, (class_id,)).fetchall()

    return render(
        "teacher_class_detail",
        active="classes",
        c=c,
        students=students
    )

@app.route("/teacher/assignments")
@role_required("TEACHER")
def teacher_assignments():
    uid = current_user()["id"]

    if is_advisor_teacher(uid):
        assignments = get_db().execute("""
            SELECT a.*, s.name AS subject_name, c.name AS class_name
            FROM assignments a
            JOIN subjects s ON s.id=a.subject_id
            JOIN classes c ON c.id=s.class_id
            WHERE c.name='ม.4/4'
            ORDER BY a.due_date ASC, a.id DESC
        """).fetchall()
    else:
        assignments = get_db().execute("""
            SELECT a.*, s.name AS subject_name, c.name AS class_name
            FROM assignments a
            JOIN subjects s ON s.id=a.subject_id
            JOIN classes c ON c.id=s.class_id
            WHERE a.created_by_id=?
            ORDER BY a.due_date ASC, a.id DESC
        """, (uid,)).fetchall()

    return render(
        "teacher_assignments",
        active="assignments",
        assignments=assignments
    )

@app.route("/teacher/assignments/new", methods=["GET", "POST"])
@role_required("TEACHER")
def teacher_new_assignment():
    db = get_db()
    uid = current_user()["id"]

    if is_biology_teacher(uid):
        subjects = db.execute("""
            SELECT s.*, c.name AS class_name
            FROM subjects s
            JOIN classes c ON c.id=s.class_id
            WHERE s.name='ชีววิทยา'
            ORDER BY c.name
        """).fetchall()
    elif is_advisor_teacher(uid):
        subjects = db.execute("""
            SELECT s.*, c.name AS class_name
            FROM subjects s
            JOIN classes c ON c.id=s.class_id
            WHERE c.name='ม.4/4'
            ORDER BY s.name
        """).fetchall()
    else:
        subjects = db.execute("""
            SELECT s.*, c.name AS class_name
            FROM subjects s
            JOIN classes c ON c.id=s.class_id
            WHERE c.teacher_id=?
            ORDER BY c.name, s.name
        """, (uid,)).fetchall()

    if request.method == "POST":
        subject_id = request.form.get("subject_id")
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date = request.form.get("due_date")
        full_score = request.form.get("full_score")

        try:
            full_score_num = float(full_score)
            due = date.fromisoformat(due_date)
        except (ValueError, TypeError):
            flash("ข้อมูลวันที่หรือคะแนนไม่ถูกต้อง")
            return redirect(url_for("teacher_new_assignment"))

        if is_biology_teacher(uid):
            owned = db.execute("""
                SELECT s.id
                FROM subjects s
                JOIN classes c ON c.id=s.class_id
                WHERE s.id=? AND s.name='ชีววิทยา'
            """, (subject_id,)).fetchone()
        elif is_advisor_teacher(uid):
            owned = db.execute("""
                SELECT s.id
                FROM subjects s
                JOIN classes c ON c.id=s.class_id
                WHERE s.id=? AND c.name='ม.4/4'
            """, (subject_id,)).fetchone()
        else:
            owned = db.execute("""
                SELECT s.id
                FROM subjects s
                JOIN classes c ON c.id=s.class_id
                WHERE s.id=? AND c.teacher_id=?
            """, (subject_id, uid)).fetchone()

        if not owned or not title or full_score_num <= 0:
            flash("กรุณากรอกข้อมูลให้ถูกต้อง")
            return redirect(url_for("teacher_new_assignment"))

        db.execute("""
            INSERT INTO assignments
            (subject_id,created_by_id,title,description,due_date,full_score)
            VALUES (?,?,?,?,?,?)
        """, (
            subject_id, uid, title, description,
            due.isoformat(), full_score_num
        ))
        db.commit()

        flash("สร้างงานเรียบร้อยแล้ว")
        return redirect(url_for("teacher_assignments"))

    return render(
        "teacher_new_assignment",
        active="assignments",
        subjects=subjects
    )

@app.route("/teacher/assignments/<int:assignment_id>")
@role_required("TEACHER")
def teacher_assignment_detail(assignment_id):
    db = get_db()
    uid = current_user()["id"]

    if is_advisor_teacher(uid):
        a = db.execute("""
            SELECT a.*, s.name AS subject_name, c.name AS class_name
            FROM assignments a
            JOIN subjects s ON s.id=a.subject_id
            JOIN classes c ON c.id=s.class_id
            WHERE a.id=? AND c.name='ม.4/4'
        """, (assignment_id,)).fetchone()
    else:
        a = db.execute("""
            SELECT a.*, s.name AS subject_name, c.name AS class_name
            FROM assignments a
            JOIN subjects s ON s.id=a.subject_id
            JOIN classes c ON c.id=s.class_id
            WHERE a.id=? AND a.created_by_id=?
        """, (assignment_id, uid)).fetchone()

    if not a:
        return "ไม่พบงาน", 404

    submissions = db.execute("""
        SELECT sub.id AS submission_id, sub.submitted_at,
               sub.content, u.name AS student_name,
               g.score, g.feedback
        FROM submissions sub
        JOIN users u ON u.id=sub.student_id
        LEFT JOIN grades g ON g.submission_id=sub.id
        WHERE sub.assignment_id=?
        ORDER BY sub.submitted_at DESC
    """, (assignment_id,)).fetchall()

    return render(
        "teacher_assignment_detail",
        active="assignments",
        a=a,
        submissions=submissions,
        is_advisor=is_advisor_teacher(uid)
    )

@app.route("/teacher/submissions/<int:submission_id>", methods=["GET", "POST"])
@role_required("TEACHER")
def teacher_grade(submission_id):
    db = get_db()
    uid = current_user()["id"]

    s = db.execute("""
        SELECT sub.*, u.name AS student_name,
               g.score, g.feedback,
               a.id AS assignment_id, a.title, a.full_score,
               a.created_by_id, su.name AS subject_name
        FROM submissions sub
        JOIN users u ON u.id=sub.student_id
        JOIN assignments a ON a.id=sub.assignment_id
        JOIN subjects su ON su.id=a.subject_id
        LEFT JOIN grades g ON g.submission_id=sub.id
        WHERE sub.id=? AND (
            a.created_by_id=? OR
            (?=1 AND a.subject_id IN (SELECT s.id FROM subjects s JOIN classes c ON c.id=s.class_id WHERE c.name='ม.4/4'))
        )
    """, (submission_id, uid, 1 if is_advisor_teacher(uid) else 0)).fetchone()

    if not s:
        return "ไม่พบงานที่ส่ง", 404

    a = {
        "id": s["assignment_id"],
        "title": s["title"],
        "full_score": s["full_score"],
        "subject_name": s["subject_name"]
    }

    if request.method == "POST":
        try:
            score = float(request.form.get("score", ""))
        except ValueError:
            flash("กรุณากรอกคะแนนเป็นตัวเลข")
            return redirect(url_for("teacher_grade", submission_id=submission_id))

        if score < 0 or score > float(s["full_score"]):
            flash("คะแนนต้องอยู่ระหว่าง 0 ถึงคะแนนเต็ม")
            return redirect(url_for("teacher_grade", submission_id=submission_id))

        feedback = request.form.get("feedback", "").strip()

        existing = db.execute(
            "SELECT id FROM grades WHERE submission_id=?",
            (submission_id,)
        ).fetchone()

        if existing:
            db.execute("""
                UPDATE grades
                SET score=?, feedback=?, graded_by_id=?,
                    graded_at=datetime('now'), updated_at=datetime('now')
                WHERE submission_id=?
            """, (score, feedback, uid, submission_id))
        else:
            db.execute("""
                INSERT INTO grades
                (submission_id,score,feedback,graded_by_id)
                VALUES (?,?,?,?)
            """, (submission_id, score, feedback, uid))

        db.execute("""
            UPDATE submissions
            SET status='GRADED', updated_at=datetime('now')
            WHERE id=?
        """, (submission_id,))

        db.execute("""
            INSERT INTO notifications
            (user_id,title,message,type,related_assignment_id)
            VALUES (?,?,?,?,?)
        """, (
            s["student_id"],
            "งานถูกตรวจแล้ว",
            f"งาน {s['title']} ได้คะแนน {score}/{s['full_score']}",
            "GRADE",
            s["assignment_id"]
        ))

        db.commit()
        flash("บันทึกคะแนนเรียบร้อยแล้ว")
        return redirect(url_for(
            "teacher_assignment_detail",
            assignment_id=s["assignment_id"]
        ))

    return render(
        "teacher_grade",
        active="assignments",
        s=s,
        a=a
    )

@app.before_request
def setup():
    if request.endpoint != "static":
        init_db()

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
