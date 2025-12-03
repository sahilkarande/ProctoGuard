"""
Application Routes - Fixed Version
Bug fixes: PRN/Roll number formatting, delete operations, selection handling
"""

# ============================
# Standard Library Imports
# ============================
import csv
import io
import json
import random
import sqlite3
import traceback
from datetime import datetime
from io import StringIO, BytesIO
import base64

# ============================
# Third-Party Library Imports
# ============================
import cv2
import numpy as np
import pandas as pd
from sqlalchemy import func, text

# Flask imports
from flask import (
    Blueprint, render_template, request, redirect, url_for,
    flash, jsonify, session, send_file, Response, current_app
)
from flask_login import (
    login_user, login_required, logout_user, current_user
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from flask import Flask


# ============================
# Local Application Imports
# ============================
from backend.database import db
from models import (
    User, Exam, Question, StudentExam,
    StudentAnswer, ActivityLog,
    ExamCalibration, ExamViolation
)

from backend.utils.email_utils import send_otp_email
from backend.services.pdf_generator import (
    generate_result_pdf,
    generate_batch_report_pdf
)

# Proctoring system
from backend.services.proctor_vision.openvino_vision import (
    ProctorState,
    OpenVINOProctor
)



# ═══════════════════════════════════════════════════════════════════════
# SOCKET.IO FOR BINARY PROCTORING
# ═══════════════════════════════════════════════════════════════════════
from flask_socketio import SocketIO, emit

# Initialize Socket.IO (will be bound to app in register_routes)
socketio = SocketIO(cors_allowed_origins="*", async_mode='threading')

print("✅ Socket.IO initialized for binary proctoring")


admin_sql_bp = Blueprint('admin_sql', __name__)

def is_authorized_sql_user():
    """Allow admin full access, faculty read-only."""
    role = getattr(current_user, "role", None)
    return role in ("admin", "faculty")

@admin_sql_bp.route('/admin/sql_console', methods=['GET'])
@login_required
def admin_sql_console():
    if not is_authorized_sql_user():
        return "Access denied", 403
    return render_template('admin_sql_console.html')

@admin_sql_bp.route('/admin/sql_console/run', methods=['POST'])
@login_required
def admin_sql_run():
    payload = request.get_json() or {}
    sql = (payload.get('sql') or '').strip()
    if not sql:
        return jsonify({"success": False, "error": "No SQL provided"}), 400

    role = getattr(current_user, "role", None)
    first_word = sql.split(None, 1)[0].lower()

    if role == "faculty" and first_word not in ("select", "pragma", "with"):
        return jsonify({
            "success": False,
            "error": "Faculty can only run SELECT queries"
        }), 403

    if role not in ("admin", "faculty"):
        return jsonify({"success": False, "error": "Access denied"}), 403

    try:
        engine = db.engine

        if first_word in ("select", "pragma", "with"):
            with engine.connect() as conn:
                result = conn.execute(text(sql))
                columns = result.keys()
                rows = [dict(r._mapping) for r in result.fetchall()]
            return jsonify({
                "success": True,
                "type": "select",
                "columns": columns,
                "rows": rows,
                "rowcount": len(rows)
            })
        else:
            with engine.begin() as conn:
                result = conn.execute(text(sql))
                affected = result.rowcount or 0
            return jsonify({
                "success": True,
                "type": "update",
                "message": f"✅ Query executed. Rows affected: {affected}"
            })

    except Exception as e:
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500

# Global proctoring instances (one per student_exam_id)
PROCTOR_INSTANCES = {}

def decode_base64_image(data_url: str):
    """Convert base64 image to OpenCV format"""
    try:
        if "," in data_url:
            _, encoded = data_url.split(",", 1)
        else:
            encoded = data_url
        img_bytes = base64.b64decode(encoded)
        img_array = np.frombuffer(img_bytes, dtype=np.uint8)
        img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        return img
    except Exception as e:
        print(f"Error decoding image: {e}")
        return None


def get_proctor_instance(student_exam_id: int, exam):
    """Get or create a ProctorState instance"""
    if student_exam_id not in PROCTOR_INSTANCES:
        max_warnings = getattr(exam, 'max_violations', 3) or 3
        proctor_state = ProctorState(
            session_id=f"exam-{student_exam_id}",
            max_warnings=max_warnings
        )
        vision = OpenVINOProctor(
            proctor_state,
            model_dir="models",  # Models folder in project root
            device="CPU"
        )
        PROCTOR_INSTANCES[student_exam_id] = (proctor_state, vision)
    return PROCTOR_INSTANCES[student_exam_id]




# ═══════════════════════════════════════════════════════════════════════
# SOCKET.IO EVENT HANDLERS FOR BINARY PROCTORING
# ═══════════════════════════════════════════════════════════════════════

@socketio.on('calibrationBinary')
def handle_calibration_binary(data):
    """Handle binary calibration frame - FAST VERSION"""
    try:
        student_exam_id = data.get('studentExamId')
        frame_buffer = data.get('frame')
        
        if not frame_buffer or not student_exam_id:
            emit('calibration_result', {'success': False, 'message': 'Invalid data'})
            return
        
        print(f"📸 Received calibration frame: {len(frame_buffer)} bytes")
        
        # Convert ArrayBuffer to numpy array
        nparr = np.frombuffer(frame_buffer, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            emit('calibration_result', {'success': False, 'message': 'Failed to decode frame'})
            return
        
        # Use face detection cascade
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        print(f"👤 Detected {len(faces)} face(s)")
        
        # Update StudentExam
        student_exam = StudentExam.query.get(student_exam_id)
        
        if len(faces) == 0:
            # No face detected
            emit('calibration_result', {
                'success': False,
                'message': 'No face detected. Please position yourself clearly in front of the camera.'
            })
            
        elif len(faces) > 1:
            # Multiple faces
            emit('calibration_result', {
                'success': False,
                'message': 'Multiple faces detected. Please ensure only you are visible.'
            })
            
        else:
            # Calibration successful
            if student_exam:
                student_exam.calibration_completed = True
                student_exam.calibration_timestamp = datetime.utcnow()
                db.session.commit()
                print(f"✅ Calibration completed for StudentExam {student_exam_id}")
            
            emit('calibration_result', {
                'success': True,
                'message': 'Face calibrated successfully!'
            })
        
    except Exception as e:
        print(f"❌ Calibration error: {e}")
        traceback.print_exc()
        emit('calibration_result', {'success': False, 'message': 'Calibration failed. Please try again.'})


@socketio.on('frameBinary')
def handle_frame_binary(data):
    """Handle binary proctoring frame - CONTINUOUS MONITORING"""
    try:
        student_exam_id = data.get('studentExamId')
        frame_buffer = data.get('frame')
        
        if not frame_buffer or not student_exam_id:
            return
        
        # Convert to numpy array
        nparr = np.frombuffer(frame_buffer, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        
        if frame is None:
            return
        
        # Detect faces
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        face_cascade = cv2.CascadeClassifier(cv2.data.haarcascades + 'haarcascade_frontalface_default.xml')
        faces = face_cascade.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(30, 30))
        
        # Get StudentExam
        student_exam = StudentExam.query.get(student_exam_id)
        
        if not student_exam:
            return
        
        # Initialize violation counts if None
        if student_exam.no_face_count is None:
            student_exam.no_face_count = 0
        if student_exam.multiple_faces_count is None:
            student_exam.multiple_faces_count = 0
        if student_exam.total_violations is None:
            student_exam.total_violations = 0
        
        # Check for violations
        if len(faces) == 0:
            # No face detected
            student_exam.no_face_count += 1
            student_exam.total_violations += 1
            
            # Log violation
            violation = ExamViolation(
                student_exam_id=student_exam_id,
                violation_type='no_face',
                message='No face detected in frame',
                severity='medium',
                timestamp=datetime.utcnow()
            )
            db.session.add(violation)
            db.session.commit()
            
            emit('proctor_result', {
                'success': False,
                'violation': 'no_face',
                'message': 'No face detected',
                'count': student_exam.no_face_count,
                'total_violations': student_exam.total_violations
            })
            
        elif len(faces) > 1:
            # Multiple faces
            student_exam.multiple_faces_count += 1
            student_exam.total_violations += 1
            
            # Log violation
            violation = ExamViolation(
                student_exam_id=student_exam_id,
                violation_type='multiple_faces',
                message=f'Multiple faces detected ({len(faces)} faces)',
                severity='high',
                timestamp=datetime.utcnow()
            )
            db.session.add(violation)
            db.session.commit()
            
            emit('proctor_result', {
                'success': False,
                'violation': 'multiple_faces',
                'message': 'Multiple faces detected',
                'count': student_exam.multiple_faces_count,
                'total_violations': student_exam.total_violations
            })
            
        else:
            # Face detected - all good
            emit('proctor_result', {
                'success': True,
                'faces': 1
            })
        
        # Check if total violations exceed threshold (15)
        if student_exam.total_violations >= 15 and student_exam.status == 'in_progress':
            # Auto-terminate exam
            student_exam.status = 'terminated'
            student_exam.submitted_at = datetime.utcnow()
            student_exam.proctoring_status = 'terminated'
            
            # Log termination
            violation = ExamViolation(
                student_exam_id=student_exam_id,
                violation_type='auto_terminated',
                message='Exam auto-terminated due to excessive violations',
                severity='critical',
                timestamp=datetime.utcnow()
            )
            db.session.add(violation)
            db.session.commit()
            
            print(f"🚨 Exam terminated for StudentExam {student_exam_id} due to violations")
            
            # Calculate score before termination
            calculate_student_score(student_exam_id)
        
    except Exception as e:
        print(f"❌ Frame processing error: {e}")
        traceback.print_exc()


@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print("✅ Socket.IO client connected")
    

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print("⚠️ Socket.IO client disconnected")


def calculate_student_score(student_exam_id):
    """Calculate and update the score for a completed student exam"""
    try:
        student_exam = StudentExam.query.get(student_exam_id)
        if not student_exam:
            return None
        
        exam = student_exam.exam
        questions = Question.query.filter_by(exam_id=exam.id).all()
        
        if not questions:
            student_exam.score = 0
            student_exam.total_points = 0
            student_exam.percentage = 0
            student_exam.passed = False
            db.session.commit()
            return {'score': 0, 'total_points': 0}
        
        student_answers = StudentAnswer.query.filter_by(student_exam_id=student_exam_id).all()
        answer_dict = {ans.question_id: ans for ans in student_answers}
        
        earned_points = 0
        total_points = 0
        
        for question in questions:
            points = question.points or 1.0
            total_points += points
            
            student_answer = answer_dict.get(question.id)
            
            if student_answer and student_answer.selected_answer:
                is_correct = (student_answer.selected_answer.upper() == question.correct_answer.upper())
                
                if is_correct:
                    earned_points += points
                    student_answer.is_correct = True
                    student_answer.points_earned = points
                else:
                    student_answer.is_correct = False
                    student_answer.points_earned = 0
            else:
                if not student_answer:
                    student_answer = StudentAnswer(
                        student_exam_id=student_exam_id,
                        question_id=question.id,
                        selected_answer="0",
                        is_correct=False,
                        points_earned=0
                    )
                    db.session.add(student_answer)
        
        percentage = (earned_points / total_points * 100) if total_points > 0 else 0
        passing_score = exam.passing_score or 50.0
        passed = percentage >= passing_score
        
        student_exam.score = round(earned_points, 2)
        student_exam.total_points = round(total_points, 2)
        student_exam.percentage = round(percentage, 2)
        student_exam.passed = passed
        student_exam.status = 'completed'
        student_exam.completed = True
        
        if student_exam.started_at and student_exam.submitted_at:
            time_taken = (student_exam.submitted_at - student_exam.started_at).total_seconds() / 60
            student_exam.time_taken_minutes = int(time_taken)
        
        db.session.commit()
        
        return {
            'score': earned_points,
            'total_points': total_points,
            'percentage': percentage,
            'passed': passed
        }
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.session.rollback()
        return None

def register_routes(app):
    """Register all routes with the Flask app"""

    # ═══════════════════════════════════════════════════════════════════
    # INITIALIZE SOCKET.IO WITH APP
    # ═══════════════════════════════════════════════════════════════════
    socketio.init_app(app)
    print("✅ Socket.IO bound to Flask app for binary proctoring")
    
    print("📝 Registering enhanced routes...")

    # ============================================================
    # Cache Control Middleware
    # ============================================================
    @app.after_request
    def add_cache_control(response):
        """Cache control to prevent back button showing login after logout"""
        endpoint = request.endpoint or ""

        # Auth routes should never cache
        if endpoint in ['login', 'logout', 'register', 'verify_otp']:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        # Allow short private caching for dashboards
        if current_user.is_authenticated:
            response.headers['Cache-Control'] = 'private, max-age=600, must-revalidate'
        else:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'

        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response



    # ============= Authentication Routes =============
    @app.route('/')
    def index():
        """Smart redirect based on login state"""
        if current_user.is_authenticated:
            if current_user.role == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            elif current_user.role == 'student':
                return redirect(url_for('student_dashboard'))
            elif current_user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
        return render_template('index.html')

    def clean_for_insert(self):
        """
        Cleans empty string fields before saving.
        Converts blank values ('') to None to prevent UNIQUE constraint issues.
        """
        string_fields = [
            "prn_number", "employee_id", "roll_id",
            "batch", "department", "phone"
        ]
        for field in string_fields:
            value = getattr(self, field, None)
            if isinstance(value, str) and value.strip() == "":
                setattr(self, field, None)


    @app.route('/register', methods=['GET', 'POST'])
    def register():
        """Final, stable registration route for students and faculty"""
        if request.method == 'POST':
            try:
                # Collect inputs safely
                username = request.form.get('username', '').strip()
                email = request.form.get('email', '').strip().lower()
                password = request.form.get('password', '')
                role = request.form.get('role', '').strip().lower()
                full_name = request.form.get('full_name', '').strip()
                phone = request.form.get('phone', '').strip()

                # Optional fields
                batch = request.form.get('batch', '').strip() or None
                department = request.form.get('department', '').strip() or "Education & Training"
                employee_id = request.form.get('employee_id', '').strip() or None
                prn_number = request.form.get('prn_number', '').strip() or None
                roll_id = request.form.get('roll_id', '').strip() or None

                print("📝 Registration attempt:", {
                    "username": username,
                    "email": email,
                    "role": role,
                    "employee_id": employee_id,
                    "prn_number": prn_number
                })

                # Basic validation
                if not username or not email or not password or not role:
                    flash("All required fields must be filled.", "error")
                    return redirect(url_for("register"))

                # Role-based validation
                if role == "student":
                    if not prn_number:
                        flash("PRN number required for students.", "error")
                        return redirect(url_for("register"))

                    prn_clean = prn_number.replace(".", "").replace(" ", "")
                    if not prn_clean.isdigit() or len(prn_clean) != 12:
                        flash("PRN number must be exactly 12 digits.", "error")
                        return redirect(url_for("register"))
                    prn_number = prn_clean
                else:
                    # Faculty path — ensure student-only fields are null
                    prn_number = None
                    roll_id = None
                    batch = None
                    if not department:
                        department = "Education & Training"

                # Duplicate checks
                if User.query.filter_by(username=username).first():
                    flash("Username already exists.", "error")
                    return redirect(url_for("register"))

                if User.query.filter_by(email=email).first():
                    flash("Email already exists.", "error")
                    return redirect(url_for("register"))

                if prn_number and User.query.filter_by(prn_number=prn_number).first():
                    flash("PRN already registered.", "error")
                    return redirect(url_for("register"))

                if employee_id and User.query.filter_by(employee_id=employee_id).first():
                    flash("Employee ID already registered.", "error")
                    return redirect(url_for("register"))

                # Hash password
                hashed_password = generate_password_hash(password)

                # Create new user
                new_user = User(
                    username=username,
                    email=email,
                    password_hash=hashed_password,
                    role=role,
                    full_name=full_name,
                    phone=phone,
                    prn_number=prn_number,
                    roll_id=roll_id,
                    batch=batch,
                    department=department,
                    employee_id=employee_id,
                    is_verified=(role == "faculty")  # Faculty auto-verified
                )

                # Clean empty strings
                for field in ["prn_number", "employee_id", "roll_id", "batch", "department", "phone"]:
                    val = getattr(new_user, field)
                    if isinstance(val, str) and val.strip() == "":
                        setattr(new_user, field, None)

                db.session.add(new_user)
                db.session.flush()  # Early validation check

                if role == "student":
                    # OTP verification flow
                    otp = new_user.generate_otp()
                    db.session.commit()
                    try:
                        send_otp_email(new_user.email, otp, new_user.username, new_user.role)
                    except Exception as e:
                        print("⚠️ OTP email failed:", e)
                    session["pending_user_id"] = new_user.id
                    flash("Student registered successfully! Please verify your email.", "success")
                    print(f"✅ Student created: {new_user.username}")
                    return redirect(url_for("verify_otp"))

                else:
                    # Faculty registration — verified immediately
                    db.session.commit()
                    flash("Faculty account created successfully! You can now log in.", "success")
                    print(f"✅ Faculty created: {new_user.username}")
                    return redirect(url_for("login"))

            except Exception as e:
                db.session.rollback()
                import traceback
                print("❌ Registration failed:", e)
                traceback.print_exc()
                flash(f"Registration failed: {str(e)}", "error")
                return redirect(url_for("register"))

        return render_template("register.html")





    @app.route('/verify-otp', methods=['GET', 'POST'])
    def verify_otp():
        """OTP verification page"""
        user_id = session.get('pending_user_id')
        
        if not user_id:
            flash('Please register first', 'error')
            return redirect(url_for('register'))
        
        user = User.query.get(user_id)
        
        if not user:
            flash('User not found', 'error')
            session.pop('pending_user_id', None)
            return redirect(url_for('register'))
        
        if user.is_verified:
            flash('Account already verified', 'info')
            session.pop('pending_user_id', None)
            return redirect(url_for('login'))
        
        if request.method == 'POST':
            otp = request.form.get('otp')
            
            if user.verify_otp(otp):
                db.session.commit()
                session.pop('pending_user_id', None)
                flash('Email verified! You can now login.', 'success')
                return redirect(url_for('login'))
            else:
                flash('Invalid or expired OTP. Please try again.', 'error')
        
        return render_template('verify_otp.html', email=user.email, username=user.username)

    @app.route('/resend-otp', methods=['POST'])
    def resend_otp():
        """Resend OTP"""
        user_id = session.get('pending_user_id')
        
        if not user_id:
            return jsonify({'success': False, 'error': 'No pending verification'})
        
        user = User.query.get(user_id)
        
        if not user:
            return jsonify({'success': False, 'error': 'User not found'})
        
        if user.is_verified:
            return jsonify({'success': False, 'error': 'Already verified'})
        
        otp = user.generate_otp()
        send_otp_email(user.email, otp, user.username, user.role)
        db.session.commit()
        
        return jsonify({'success': True, 'message': 'OTP sent! Check your email.'})

    @app.route('/login', methods=['GET', 'POST'])
    def login():
        """User login with verification check, password change enforcement, and smart session handling."""
        
        # ✅ If user is already logged in, redirect them immediately
        if current_user.is_authenticated:
            if current_user.role == 'faculty':
                return redirect(url_for('faculty_dashboard'))
            elif current_user.role == 'student':
                return redirect(url_for('student_dashboard'))
            elif current_user.role == 'admin':
                return redirect(url_for('admin_dashboard'))
            else:
                return redirect(url_for('index'))

        # Normal login flow
        if request.method == 'POST':
            username = request.form.get('username')
            password = request.form.get('password')

            # Validate input
            if not username or not password:
                flash('❌ Please enter both username and password', 'error')
                return redirect(url_for('login'))

            user = User.query.filter_by(username=username).first()

            # FIXED: use password_hash
            if user and check_password_hash(user.password_hash, password):
                # ✅ Check if user is verified
                if not user.is_verified:
                    session['pending_user_id'] = user.id
                    flash('⚠️ Please verify your email first. Check inbox for OTP.', 'warning')
                    return redirect(url_for('verify_otp'))

                # ✅ Login user
                login_user(user)
                session.permanent = True  # ensures session lasts until logout
                
                # ✅ CRITICAL: Check if student needs to change password (first-time login)
                if user.role == 'student' and not getattr(user, 'password_changed', False):
                    flash('⚠️ Welcome! For security, please change your password to continue.', 'warning')
                    return redirect(url_for('change_password'))
                
                # ✅ Success message
                flash(f'✅ Welcome back, {user.full_name or user.username}!', 'success')

                # ✅ Redirect based on role
                if user.role == 'faculty':
                    return redirect(url_for('faculty_dashboard'))
                elif user.role == 'student':
                    return redirect(url_for('student_dashboard'))
                elif user.role == 'admin':
                    return redirect(url_for('admin_dashboard'))
                else:
                    return redirect(url_for('index'))
            else:
                flash('❌ Invalid username or password', 'error')
                return redirect(url_for('login'))

        return render_template('login.html')

    @app.route('/logout')
    @login_required
    def logout():
        """Secure logout: clear session and prevent cache."""
        from flask import make_response, session
        logout_user()
        session.clear()

        # Create response
        response = make_response(redirect(url_for('login')))

        # No caching after logout
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'

        flash('You have been logged out securely.', 'info')
        return response





    # ============= Faculty Routes =============

    @app.route('/faculty/dashboard')
    @login_required
    def faculty_dashboard():
        """Faculty dashboard"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        exams = Exam.query.filter_by(creator_id=current_user.id).order_by(Exam.created_at.desc()).all()
        
        total_exams = len(exams)
        active_exams = len([e for e in exams if e.is_active])
        total_attempts = sum([len(e.student_exams) for e in exams])
        
        return render_template('faculty/dashboard.html', 
                             exams=exams,
                             total_exams=total_exams,
                             active_exams=active_exams,
                             total_attempts=total_attempts)

    @app.route('/faculty/exam/create', methods=['GET', 'POST'])
    @login_required
    def create_exam():
        """Create a new exam"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        if request.method == 'POST':
            title = request.form.get('title')
            description = request.form.get('description')
            duration_minutes = int(request.form.get('duration_minutes'))
            passing_score = float(request.form.get('passing_score', 50.0))
            max_tab_switches = int(request.form.get('max_tab_switches', 3))
            
            exam = Exam(
                title=title,
                description=description,
                duration_minutes=duration_minutes,
                passing_score=passing_score,
                max_tab_switches=max_tab_switches,
                creator_id=current_user.id
            )
            
            db.session.add(exam)
            db.session.commit()
            
            flash('Exam created successfully! Now upload questions.', 'success')
            return redirect(url_for('upload_questions', exam_id=exam.id))
        
        return render_template('faculty/create_exam.html')

    @app.route('/faculty/exam/<int:exam_id>/delete', methods=['POST'])
    @login_required
    def delete_exam(exam_id):
        """Securely delete an exam and all related data."""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        exam = Exam.query.get_or_404(exam_id)

        if exam.creator_id != current_user.id:
            flash('Access denied: You can only delete your own exams.', 'error')
            return redirect(url_for('faculty_dashboard'))

        try:
            # 🔥 Step 1: Manually delete all related data (defensive cleanup)
            from models import Question, StudentExam, StudentAnswer, ActivityLog
            
            # Delete related questions, student exams, and logs
            Question.query.filter_by(exam_id=exam.id).delete()
            StudentExam.query.filter_by(exam_id=exam.id).delete()
            ActivityLog.query.filter(ActivityLog.student_exam_id.in_(
                db.session.query(StudentExam.id).filter_by(exam_id=exam.id)
            )).delete()

            # 🔥 Step 2: Delete the exam itself
            db.session.delete(exam)
            db.session.commit()

            flash('✅ Exam and all related questions, attempts, and logs deleted successfully.', 'success')

        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error deleting exam: {str(e)}', 'error')

        return redirect(url_for('faculty_dashboard'))

    @app.route('/faculty/exam/<int:exam_id>/preview', methods=['POST'])
    @login_required
    def preview_questions(exam_id):
        """
        Secure server-side preview of uploaded exam questions before final import.
        Supports CSV, Excel, and JSON files.
        Returns up to 100 rows for client-side validation and display.
        """
        # ---------- Access Control ----------
        if current_user.role != 'faculty':
            return jsonify({"success": False, "error": "Access denied"}), 403

        exam = Exam.query.get_or_404(exam_id)
        if exam.creator_id != current_user.id:
            return jsonify({"success": False, "error": "Access denied"}), 403

        # ---------- File Validation ----------
        if 'file' not in request.files:
            return jsonify({"success": False, "error": "No file uploaded"}), 400

        file = request.files['file']
        filename = secure_filename(file.filename or "")
        if filename == "":
            return jsonify({"success": False, "error": "Empty filename"}), 400

        ext = filename.rsplit('.', 1)[-1].lower()

        try:
            rows = []
            max_preview = 100  # preview limit

            # ---------- CSV ----------
            if ext == 'csv':
                df = pd.read_csv(file, nrows=max_preview)
                df.columns = [c.strip().lower() for c in df.columns]
                rows = df.to_dict(orient='records')

            # ---------- Excel ----------
            elif ext in ('xls', 'xlsx'):
                df = pd.read_excel(file, nrows=max_preview)
                df.columns = [c.strip().lower() for c in df.columns]
                rows = df.to_dict(orient='records')

            # ---------- JSON ----------
            elif ext == 'json':
                try:
                    data = json.load(file)
                except Exception as e:
                    return jsonify({"success": False, "error": f"Invalid JSON: {str(e)}"}), 400

                if not isinstance(data, list):
                    return jsonify({"success": False, "error": "JSON must be an array of objects"}), 400

                # convert only first N records to DataFrame (for consistency)
                df = pd.DataFrame(data[:max_preview])
                df.columns = [c.strip().lower() for c in df.columns]
                rows = df.to_dict(orient='records')

            # ---------- Unsupported ----------
            else:
                return jsonify({
                    "success": False,
                    "error": "Unsupported file type. Please upload CSV, Excel, or JSON."
                }), 400

            # ---------- Response ----------
            return jsonify({
                "success": True,
                "count": len(rows),
                "rows": rows
            })

        except Exception as e:
            current_app.logger.exception("❌ Error in question preview:")
            return jsonify({
                "success": False,
                "error": f"Server error: {str(e)}"
            }), 500



    # ---------------------
    # Real upload endpoint (FIXED + CLEANED)
    # ---------------------
    @app.route('/faculty/exam/<int:exam_id>/upload', methods=['GET', 'POST'])
    @login_required
    def upload_questions(exam_id):
        """Upload questions from CSV / Excel / JSON (production-ready, fully cleaned)."""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        exam = Exam.query.get_or_404(exam_id)
        if exam.creator_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('faculty_dashboard'))

        if request.method == 'POST':
            if 'file' not in request.files:
                flash('No file uploaded.', 'error')
                return redirect(request.url)

            file = request.files['file']
            filename = secure_filename(file.filename or "")
            if filename == "":
                flash('No file selected.', 'error')
                return redirect(request.url)

            ext = filename.rsplit('.', 1)[-1].lower()

            try:
                if ext == 'csv':
                    df = pd.read_csv(file)
                elif ext in ('xls', 'xlsx'):
                    df = pd.read_excel(file)
                elif ext == 'json':
                    try:
                        data = json.load(file)
                    except Exception:
                        flash('Invalid JSON file.', 'error')
                        return redirect(request.url)
                    if not isinstance(data, list):
                        flash('JSON must be an array of objects.', 'error')
                        return redirect(request.url)
                    df = pd.DataFrame(data)
                else:
                    flash('Unsupported file type. Upload CSV, Excel, or JSON.', 'error')
                    return redirect(request.url)

                # Normalize column names
                df.columns = [c.strip().lower() for c in df.columns]

                # Validate required columns
                required_columns = {'question', 'option_a', 'option_b', 'correct_answer'}
                missing = required_columns - set(df.columns)
                if missing:
                    flash(f"Missing required columns: {', '.join(missing)}", 'error')
                    return redirect(request.url)

                # Limit for safety
                MAX_IMPORT = 20000
                if len(df) > MAX_IMPORT:
                    flash(f"File too large: maximum {MAX_IMPORT} questions allowed.", 'error')
                    return redirect(request.url)

                
                for idx, row in df.iterrows():
                    count = 0
                    # Clean and normalize fields
                    q_text = str(row.get('question', '')).strip()
                    a = str(row.get('option_a', '')).strip()
                    b = str(row.get('option_b', '')).strip()
                    c = str(row.get('option_c', '')).strip() if 'option_c' in df.columns else None
                    d = str(row.get('option_d', '')).strip() if 'option_d' in df.columns else None
                    correct = str(row.get('correct_answer', '')).strip().upper()

                    # Normalize points
                    try:
                        points_val = float(row.get('points', 1.0))
                    except Exception:
                        points_val = 1.0

                    # Skip malformed rows
                    if not q_text or not a or not b or correct == "":
                        continue

                    # Normalize correct answer (should be A/B/C/D)
                    if correct not in ('A', 'B', 'C', 'D'):
                        correct = correct[0].upper() if correct else 'A'

                    # Convert blanks to None
                    def none_if_blank(x):
                        return x if x and x.strip() != "" else None

                    a, b, c, d = map(none_if_blank, [a, b, c, d])

                    # Create Question
                    new_q = Question(
                        exam_id=exam.id,
                        question_text=q_text,
                        option_a=a,
                        option_b=b,
                        option_c=c,
                        option_d=d,
                        correct_answer=correct,
                        points=points_val,
                        order_number=idx + 1,
                        enhanced=False
                    )

                    db.session.add(new_q)
                    count += 1

                db.session.commit()
                flash(f"✅ Successfully uploaded {count} questions to {exam.title}!", 'success')
                return redirect(url_for('view_exam', exam_id=exam.id))

            except Exception as e:
                db.session.rollback()
                current_app.logger.exception("❌ Upload error")
                flash(f"Error processing file: {str(e)}", 'error')
                return redirect(request.url)

        # GET
        return render_template('faculty/upload_questions.html', exam=exam)



    # ========================================
    # REPLACE THE EXISTING view_exam ROUTE (around line 718-744)
    # WITH THIS ENHANCED VERSION
    # ========================================

    @app.route('/faculty/exam/<int:exam_id>')
    @login_required
    def view_exam(exam_id):
        """View exam details with enhanced access control"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        exam = Exam.query.get_or_404(exam_id)
        
        if exam.creator_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('faculty_dashboard'))
        
        questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.order_number).all()
        question_count = len(questions)
        total_attempts = len(exam.student_exams)
        completed = len([se for se in exam.student_exams if se.status == 'submitted'])
        
        # Get all students for access control
        all_students = User.query.filter_by(role='student').order_by(User.full_name).all()
        
        # Get all unique batches
        batches = db.session.query(User.batch).filter(
            User.role == 'student',
            User.batch.isnot(None),
            User.batch != ''
        ).distinct().order_by(User.batch).all()
        all_batches = [b[0] for b in batches]
        student_exams = StudentExam.query.filter_by(exam_id=exam_id).all()
        
        return render_template(
            'faculty/view_exam.html',
            exam=exam,
            questions=questions,
            total_attempts=total_attempts,
            completed_attempts=completed,
            question_count=question_count,
            all_students=all_students,
            all_batches=all_batches,
            student_exams=student_exams  # ← ADD THIS LINE
        )

    @app.route('/faculty/exam/<int:exam_id>/analytics')
    @login_required
    def exam_analytics(exam_id):
        """View exam analytics"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        exam = Exam.query.get_or_404(exam_id)
        
        if exam.creator_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('faculty_dashboard'))
        
        student_exams = StudentExam.query.filter_by(exam_id=exam_id, status='submitted').all()
        
        total_attempts = len(student_exams)
        passed = len([se for se in student_exams if se.passed])
        failed = total_attempts - passed
        
        avg_score = sum([se.percentage for se in student_exams]) / total_attempts if total_attempts > 0 else 0
        avg_time = sum([se.time_taken_minutes for se in student_exams if se.time_taken_minutes]) / total_attempts if total_attempts > 0 else 0
        
        questions = Question.query.filter_by(exam_id=exam_id).order_by(Question.order_number).all()
        question_stats = []
        
        for question in questions:
            # Total answers per question
            total_answers = StudentAnswer.query.join(StudentExam).filter(
                StudentAnswer.question_id == question.id,
                StudentExam.exam_id == exam_id,
                StudentExam.status == 'submitted'
            ).count()
            
            # Correct answers per question
            correct_answers = StudentAnswer.query.join(StudentExam).filter(
                StudentAnswer.question_id == question.id,
                StudentExam.exam_id == exam_id,
                StudentExam.status == 'submitted',
                StudentAnswer.is_correct == True
            ).count()
            
            accuracy = (correct_answers / total_answers * 100) if total_answers > 0 else 0
            
            question_stats.append({
                'question': question.question_text[:100] + '...' if len(question.question_text) > 100 else question.question_text,
                'total_answers': total_answers,
                'correct_answers': correct_answers,
                'accuracy': round(accuracy, 2),
                'difficulty': 'Easy' if accuracy > 70 else 'Medium' if accuracy > 40 else 'Hard'
            })
        
        flagged_exams = [se for se in student_exams if se.tab_switch_count > exam.max_tab_switches]
        
        return render_template(
            'faculty/analytics.html', 
            exam=exam,
            total_attempts=total_attempts,
            passed=passed,
            failed=failed,
            avg_score=round(avg_score, 2),
            avg_time=round(avg_time, 2),
            question_stats=question_stats,
            flagged_exams=flagged_exams,
            student_exams=student_exams
        )

    from fpdf import FPDF
    from flask import request, render_template, Response
    from datetime import datetime

    @app.route('/faculty/student_report', methods=['GET'])
    @login_required
    def faculty_student_report():
        """Display student report page with filters"""
        
        if current_user.role != 'faculty':
            flash('Access denied. Faculty only.', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Get all batches
        batches = db.session.query(User.batch).filter(
            User.role == 'student',
            User.batch.isnot(None),
            User.batch != ''
        ).distinct().order_by(User.batch).all()
        all_batches = [b[0] for b in batches]
        
        # Get all exams created by this faculty
        exams = Exam.query.filter_by(creator_id=current_user.id).order_by(Exam.created_at.desc()).all()
        
        # Get filters from request
        selected_batch = request.args.get('batch', '')
        selected_exam_ids_str = request.args.getlist('exam_ids')
        selected_exam_ids = [int(id) for id in selected_exam_ids_str if id.isdigit()]
        
        report_data = None
        exam_titles = []
        summary = None
        
        if selected_batch and selected_exam_ids:
            # Get students in selected batch
            students = User.query.filter_by(
                role='student',
                batch=selected_batch
            ).order_by(User.prn_number).all()
            
            # Get exam details
            selected_exams = Exam.query.filter(Exam.id.in_(selected_exam_ids)).all()
            exam_titles = [exam.title for exam in selected_exams]
            
            # Get total possible marks for each exam
            exam_total_marks = {}
            for exam in selected_exams:
                total = sum(q.points for q in exam.questions)
                exam_total_marks[exam.id] = total
            
            # Build report data
            report_data = []
            total_students = len(students)
            appeared_count = 0
            passed_count = 0
            failed_count = 0
            absent_count = 0
            total_marks_sum = 0
            
            for student in students:
                student_row = {
                    'prn_number': student.prn_number,
                    'full_name': student.full_name,
                    'exam_marks': [],
                    'total_marks': 0,
                    'percentage': 0
                }
                
                student_appeared = False
                student_total_obtained = 0
                student_total_possible = 0
                
                # Get marks for each exam
                for exam in selected_exams:
                    student_exam = StudentExam.query.filter_by(
                        student_id=student.id,
                        exam_id=exam.id,
                        status='submitted'
                    ).first()
                    
                    if student_exam and student_exam.score is not None:
                        # Student attempted this exam
                        marks = student_exam.score
                        student_row['exam_marks'].append(f"{marks:.2f}")
                        student_total_obtained += marks
                        student_total_possible += exam_total_marks[exam.id]
                        student_appeared = True
                    else:
                        # Student didn't attempt
                        student_row['exam_marks'].append('Absent')
                        student_total_possible += exam_total_marks[exam.id]
                
                # Calculate totals and percentage
                student_row['total_marks'] = student_total_obtained
                
                if student_total_possible > 0:
                    student_row['percentage'] = (student_total_obtained / student_total_possible) * 100
                else:
                    student_row['percentage'] = 0
                
                report_data.append(student_row)
                
                # Update summary stats
                if student_appeared:
                    appeared_count += 1
                    total_marks_sum += student_row['total_marks']
                    
                    if student_row['percentage'] >= 50:
                        passed_count += 1
                    else:
                        failed_count += 1
                else:
                    absent_count += 1
            
            # Calculate summary
            summary = {
                'total_students': total_students,
                'appeared': appeared_count,
                'passed': passed_count,
                'failed': failed_count,
                'absent': absent_count,
                'average_marks': total_marks_sum / appeared_count if appeared_count > 0 else 0,
                'pass_percentage': (passed_count / appeared_count * 100) if appeared_count > 0 else 0
            }
        
        return render_template(
            'faculty/student_report.html',
            batches=all_batches,
            exams=exams,
            selected_batch=selected_batch,
            selected_exam_ids=selected_exam_ids,
            report_data=report_data,
            exam_titles=exam_titles,
            summary=summary
        )

    @app.route('/faculty/student_report/pdf', methods=['GET'])
    @login_required
    def faculty_student_report_pdf_multi():
        """Generate PDF report for selected batch and exams"""
        
        if current_user.role != 'faculty':
            flash('Access denied. Faculty only.', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Get parameters
        batch_name = request.args.get('batch_name', '')
        exam_ids_str = request.args.get('exam_ids', '')
        exam_ids = [int(id) for id in exam_ids_str.split(',') if id.strip().isdigit()]
        
        if not batch_name or not exam_ids:
            flash('Invalid parameters for PDF generation', 'error')
            return redirect(url_for('faculty_student_report'))
        
        # Get students in batch
        students = User.query.filter_by(
            role='student',
            batch=batch_name
        ).order_by(User.prn_number).all()
        
        # Get exam details
        exams = Exam.query.filter(Exam.id.in_(exam_ids)).all()
        exam_titles = [exam.title for exam in exams]
        
        # Get total possible marks for each exam
        exam_total_marks = {}
        for exam in exams:
            total = sum(q.points for q in exam.questions)
            exam_total_marks[exam.id] = total
        
        # Build report data
        report_data = []
        total_students = len(students)
        appeared_count = 0
        passed_count = 0
        failed_count = 0
        absent_count = 0
        total_marks_sum = 0
        
        for student in students:
            student_row = {
                'prn_number': student.prn_number,
                'full_name': student.full_name,
                'exam_marks': [],
                'total_marks': 0,
                'percentage': 0
            }
            
            student_appeared = False
            student_total_obtained = 0
            student_total_possible = 0
            
            # Get marks for each exam
            for exam in exams:
                student_exam = StudentExam.query.filter_by(
                    student_id=student.id,
                    exam_id=exam.id,
                    status='submitted'
                ).first()
                
                if student_exam and student_exam.score is not None:
                    marks = student_exam.score
                    student_row['exam_marks'].append(f"{marks:.2f}")
                    student_total_obtained += marks
                    student_total_possible += exam_total_marks[exam.id]
                    student_appeared = True
                else:
                    student_row['exam_marks'].append('Absent')
                    student_total_possible += exam_total_marks[exam.id]
            
            # Calculate totals
            student_row['total_marks'] = student_total_obtained
            
            if student_total_possible > 0:
                student_row['percentage'] = (student_total_obtained / student_total_possible) * 100
            else:
                student_row['percentage'] = 0
            
            report_data.append(student_row)
            
            # Update summary
            if student_appeared:
                appeared_count += 1
                total_marks_sum += student_row['total_marks']
                
                if student_row['percentage'] >= 50:
                    passed_count += 1
                else:
                    failed_count += 1
            else:
                absent_count += 1
        
        # Summary data
        summary_data = {
            'total_students': total_students,
            'appeared': appeared_count,
            'passed': passed_count,
            'failed': failed_count,
            'absent': absent_count,
            'average_marks': total_marks_sum / appeared_count if appeared_count > 0 else 0,
            'pass_percentage': (passed_count / appeared_count * 100) if appeared_count > 0 else 0
        }
        
        # Generate PDF
        pdf_buffer = generate_batch_report_pdf(
            batch_name=batch_name,
            exam_titles=exam_titles,
            report_data=report_data,
            summary_data=summary_data
        )
        
        # Send PDF
        filename = f"Student_Report_{batch_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    @app.route('/faculty/student/<int:student_id>/profile')
    @login_required
    def faculty_student_profile(student_id):
        """View student profile with analytics (Faculty view)"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        student = User.query.get_or_404(student_id)
        
        if student.role != 'student':
            flash('Invalid student', 'error')
            return redirect(url_for('faculty_dashboard'))
        
        student_exams = StudentExam.query.filter_by(
            student_id=student_id,
            status='submitted'
        ).order_by(StudentExam.submitted_at.desc()).all()
        
        total_exams = len(student_exams)
        passed_exams = len([se for se in student_exams if se.passed])
        failed_exams = total_attempts - passed_exams
        avg_score = sum([se.percentage for se in student_exams]) / total_exams if total_exams > 0 else 0
        avg_time = sum([se.time_taken_minutes for se in student_exams if se.time_taken_minutes]) / total_exams if total_exams > 0 else 0
        
        recent_exams = student_exams[:10]
        chart_data = {
            'labels': [se.exam.title[:30] for se in reversed(recent_exams)],
            'scores': [se.percentage for se in reversed(recent_exams)],
            'dates': [se.submitted_at.strftime('%d/%m') for se in reversed(recent_exams)],
            'passed': [1 if se.passed else 0 for se in reversed(recent_exams)]
        }
        
        return render_template('faculty/student_profile.html',
                             student=student,
                             student_exams=student_exams,
                             total_exams=total_exams,
                             passed_exams=passed_exams,
                             failed_exams=failed_exams,
                             avg_score=avg_score,
                             avg_time=avg_time,
                             chart_data=chart_data)

    # ============= Student Routes =============

    @app.route('/student/dashboard')
    @login_required
    def student_dashboard():
        """Enhanced Student Dashboard - Safe from None/Undefined values"""
        if current_user.role != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('faculty_dashboard'))
        
        # Fetch student exams
        completed_exams = StudentExam.query.filter_by(
            student_id=current_user.id,
            status='submitted'
        ).order_by(StudentExam.submitted_at.desc()).all()
        
        in_progress = StudentExam.query.filter_by(
            student_id=current_user.id,
            status='in_progress'
        ).first()
        
        available_exams = Exam.query.filter(Exam.is_active == True).all()

        # ✅ Filter valid percentages
        percentages = [se.percentage for se in completed_exams if se.percentage is not None]

        total_exams_taken = len(completed_exams)
        avg_score = (sum(percentages) / len(percentages)) if percentages else 0
        passed_count = len([se for se in completed_exams if se.passed])
        pass_rate = (passed_count / len(completed_exams) * 100) if completed_exams else 0
        best_score = max(percentages) if percentages else 0

        # ✅ Always define it
        max_percentage = best_score if best_score is not None else 0
        top_students = top_students if 'top_students' in locals() else []

        # ✅ Now pass clean, guaranteed serializable values
        return render_template(
            'student/dashboard.html',
            completed_exams=completed_exams or [],
            available_exams=available_exams or [],
            total_exams_taken=total_exams_taken or 0,
            avg_score=avg_score or 0,
            passed_count=passed_count or 0,
            pass_rate=pass_rate or 0,
            best_score=best_score or 0,
            max_percentage=(locals().get("max_percentage") or 0),
            top_students=top_students or [],
            in_progress=in_progress or None
        )

    @app.route("/start-exam/<int:exam_id>", methods=["POST", "GET"])
    @login_required
    def start_exam(exam_id):

        # -------------------------
        # 1. STUDENT ROLE CHECK
        # -------------------------
        if current_user.role != "student":
            flash("Only students can start exams.", "error")
            return redirect(url_for("faculty_dashboard"))

        exam = Exam.query.get_or_404(exam_id)

        # -------------------------
        # 2. EXAM ACTIVE CHECK
        # -------------------------
        if not exam.is_active:
            flash("This exam is not active.", "error")
            return redirect(url_for("student_dashboard"))

        # -------------------------
        # 3. EXAM ACCESS CONTROL
        # -------------------------
        # If faculty allowed only specific students
        if not exam.allow_all_students:
            allowed = exam.allowed_students or []  # list of IDs in string form
            if str(current_user.id) not in allowed:
                flash("You are not allowed to access this exam.", "error")
                return redirect(url_for("student_dashboard"))

        # -------------------------
        # 4. CHECK IF EXAM ALREADY STARTED
        # -------------------------
        existing_attempt = StudentExam.query.filter_by(
            student_id=current_user.id,
            exam_id=exam.id
        ).first()

        # If an attempt exists and is IN PROGRESS → resume
        if existing_attempt and existing_attempt.status == "in_progress":
            return redirect(url_for("take_exam", exam_id=exam_id))

        # If attempt exists and is already submitted → prevent restart
        if existing_attempt and existing_attempt.status == "submitted":
            flash("You have already completed this exam.", "error")
            return redirect(url_for("student_dashboard"))

        # -------------------------
        # 5. RANDOMIZE QUESTIONS
        # -------------------------
        questions = exam.questions[:]  # copy

        if exam.randomize_questions:
            random.shuffle(questions)

        # -------------------------
        # 6. CREATE NEW STUDENT EXAM ATTEMPT
        # -------------------------
        student_exam = StudentExam(
            student_id=current_user.id,
            exam_id=exam.id,
            started_at=datetime.utcnow(),  
            status="in_progress",
            time_taken_minutes=0,
            tab_switch_count=0,
            
        )
        db.session.add(student_exam)
        db.session.commit()

        # -------------------------
        # 7. LINK QUESTIONS → STORE ORDER SAFELY
        # -------------------------
        # Store question order as JSON list for consistent navigation
        student_exam.question_order = json.dumps([q.id for q in questions])
        db.session.commit()

        # -------------------------
        # 8. REDIRECT TO TAKE EXAM
        # -------------------------
        return redirect(url_for("take_exam", exam_id=exam_id))



    # ========================================
    # ADD THIS NEW ROUTE AFTER view_exam
    # ========================================

    @app.route('/faculty/exam/<int:exam_id>/update_access', methods=['POST'])
    @login_required
    def update_exam_access(exam_id):
        """Update exam access control settings"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        exam = Exam.query.get_or_404(exam_id)
        
        if exam.creator_id != current_user.id:
            flash("You don't have permission to modify this exam", 'error')
            return redirect(url_for('faculty_dashboard'))
        
        access_mode = request.form.get('access_mode')
        
        if access_mode == 'stopped':
            # Stop access for all students
            exam.is_active = False
            exam.allow_all_students = False
            exam.allowed_students = None
            
            # Log activity for all active attempts
            active_attempts = StudentExam.query.filter_by(
                exam_id=exam_id,
                status='in_progress'
            ).all()
            
            for attempt in active_attempts:
                log = ActivityLog(
                    student_exam_id=attempt.id,
                    activity_type='exam_disabled',
                    description='Exam access was stopped by faculty',
                    severity='high',
                    created_at=datetime.utcnow()
                )
                db.session.add(log)
            
            db.session.commit()
            flash("⚠️ Exam access has been stopped for all students", 'warning')
            
        elif access_mode == 'all':
            # Allow all students
            exam.is_active = True
            exam.allow_all_students = True
            exam.allowed_students = None
            db.session.commit()
            flash("✅ Exam is now open to all students", 'success')
            
        elif access_mode == 'specific':
            # Allow specific students only
            allowed_students = request.form.get('allowed_students', '')
            
            if not allowed_students:
                flash("⚠️ Please select at least one student", 'warning')
                return redirect(url_for('view_exam', exam_id=exam_id))
            
            exam.is_active = True
            exam.allow_all_students = False
            exam.allowed_students = allowed_students
            
            # Count selected students
            student_ids = [s.strip() for s in allowed_students.split(',') if s.strip()]
            count = len(student_ids)
            
            db.session.commit()
            flash(f"✅ Exam access granted to {count} selected student(s)", 'success')
        
        else:
            flash("Invalid access mode", 'error')
        
        return redirect(url_for('view_exam', exam_id=exam_id))

    def calculate_student_score(student_exam_id):
        """
        Calculate and update the score for a completed student exam
        
        Args:
            student_exam_id: ID of the StudentExam record to score
        
        Returns:
            dict: Scoring results with score, total_points, percentage, passed
        """
        try:
            from models import StudentExam, StudentAnswer, Question
            
            # Get student exam
            student_exam = StudentExam.query.get(student_exam_id)
            if not student_exam:
                print(f"❌ StudentExam {student_exam_id} not found")
                return None
            
            # Get exam
            exam = student_exam.exam
            if not exam:
                print(f"❌ Exam not found for StudentExam {student_exam_id}")
                return None
            
            # Get all questions for this exam
            questions = Question.query.filter_by(exam_id=exam.id).all()
            
            if not questions:
                print(f"⚠️ No questions found for exam {exam.id}")
                student_exam.score = 0
                student_exam.total_points = 0
                student_exam.percentage = 0
                student_exam.passed = False
                db.session.commit()
                return {
                    'score': 0,
                    'total_points': 0,
                    'percentage': 0,
                    'passed': False
                }
            
            # Get student's answers
            student_answers = StudentAnswer.query.filter_by(
                student_exam_id=student_exam_id
            ).all()
            
            # Create answer lookup dict
            answer_dict = {ans.question_id: ans for ans in student_answers}
            
            # Calculate score
            earned_points = 0
            total_points = 0
            correct_count = 0
            
            for question in questions:
                points = question.points or 1.0
                total_points += points
                
                # Check if student answered this question
                student_answer = answer_dict.get(question.id)
                
                if student_answer and student_answer.selected_answer:
                    # Check if answer is correct
                    is_correct = (student_answer.selected_answer.upper() == 
                                question.correct_answer.upper())
                    
                    if is_correct:
                        earned_points += points
                        correct_count += 1
                        student_answer.is_correct = True
                        student_answer.points_earned = points
                    else:
                        student_answer.is_correct = False
                        student_answer.points_earned = 0
                else:
                    # No answer provided - create a record with 0 points
                    if not student_answer:
                        student_answer = StudentAnswer(
                            student_exam_id=student_exam_id,
                            question_id=question.id,
                            selected_answer="0",
                            is_correct=False,
                            points_earned=0
                        )
                        db.session.add(student_answer)
                    else:
                        student_answer.is_correct = False
                        student_answer.points_earned = 0
            
            # Calculate percentage
            percentage = (earned_points / total_points * 100) if total_points > 0 else 0
            
            # Determine if passed
            passing_score = exam.passing_score or 50.0
            passed = percentage >= passing_score
            
            # Update student exam record
            student_exam.score = round(earned_points, 2)
            student_exam.total_points = round(total_points, 2)
            student_exam.percentage = round(percentage, 2)
            student_exam.passed = passed
            student_exam.status = 'completed'
            student_exam.completed = True
            
            # Calculate time taken
            if student_exam.started_at and student_exam.submitted_at:
                time_taken = (student_exam.submitted_at - student_exam.started_at).total_seconds() / 60
                student_exam.time_taken_minutes = int(time_taken)
            
            db.session.commit()
            
            print(f"✅ Scored StudentExam {student_exam_id}:")
            print(f"   Score: {earned_points}/{total_points} ({percentage:.1f}%)")
            print(f"   Passed: {passed}")
            print(f"   Correct Answers: {correct_count}/{len(questions)}")
            
            return {
                'score': earned_points,
                'total_points': total_points,
                'percentage': percentage,
                'passed': passed,
                'correct_count': correct_count,
                'total_questions': len(questions)
            }
            
        except Exception as e:
            print(f"❌ Error calculating score for StudentExam {student_exam_id}: {e}")
            import traceback
            traceback.print_exc()
            db.session.rollback()
            return None

    @app.route('/exam/<int:exam_id>/take', methods=['GET'])
    @login_required
    def take_exam(exam_id):
        """Student exam taking interface - tracks absolute start time with AI Proctoring"""
        if current_user.role != 'student':
            flash('Only students can take exams.', 'error')
            return redirect(url_for('index'))

        exam = Exam.query.get_or_404(exam_id)
        
        # Check if exam is active
        exam_status = getattr(exam, 'status', 'active')
        force_ended = getattr(exam, 'force_ended', False)
        
        if exam_status == 'ended' or force_ended:
            flash('This exam has been ended by the instructor.', 'error')
            return redirect(url_for('student_dashboard'))
        
        # Get or create student exam record
        student_exam = StudentExam.query.filter_by(
            student_id=current_user.id,
            exam_id=exam_id
        ).first()

        from datetime import datetime, timedelta
        
        if not student_exam:
            # Create new exam attempt
            student_exam = StudentExam(
                student_id=current_user.id,
                exam_id=exam_id,
                started_at=datetime.utcnow(),
                tab_switch_count=0,
                force_ended=False
            )
            
            # Set proctoring defaults
            enable_proctoring = getattr(exam, 'enable_proctoring', True)
            student_exam.proctoring_enabled = enable_proctoring
            student_exam.calibration_completed = False
            student_exam.total_violations = 0
            student_exam.proctoring_status = 'active'
            
            db.session.add(student_exam)
            db.session.commit()
            
            # Calculate time remaining (new exam, so full duration)
            time_remaining = exam.duration_minutes or 60
            
        else:
            # Check if already submitted
            if student_exam.submitted_at:
                flash('You have already submitted this exam.', 'info')
                return redirect(url_for('student_dashboard'))
            
            # Calculate remaining time based on start time
            elapsed = (datetime.utcnow() - student_exam.started_at).total_seconds() / 60
            time_remaining = max(0, (exam.duration_minutes or 60) - elapsed)
            
            # Auto-submit if time expired
            if time_remaining <= 0:
                student_exam.submitted_at = datetime.utcnow()
                calculate_student_score(student_exam.id)
                db.session.commit()
                flash('Exam time expired. Your answers have been submitted.', 'warning')
                return redirect(url_for('student_dashboard'))

        # Get questions and existing answers
        questions = Question.query.filter_by(exam_id=exam_id).all()
        
        existing_answers = {}
        for answer in StudentAnswer.query.filter_by(student_exam_id=student_exam.id).all():
            existing_answers[answer.question_id] = answer.selected_answer
        
        # Debug logging
        print("\n" + "="*70)
        print("🔍 EXAM DEBUG - TAKE_EXAM ROUTE")
        print("="*70)
        print(f"Student Exam ID: {student_exam.id}")
        print(f"Exam Duration: {exam.duration_minutes} minutes")
        print(f"Time Remaining: {time_remaining} minutes")
        print(f"Time Remaining (seconds): {time_remaining * 60}")
        print(f"Proctoring Enabled: {getattr(exam, 'enable_proctoring', True)}")
        print(f"Max Violations: {getattr(exam, 'max_violations', 3)}")
        print("="*70 + "\n")
        
        return render_template(
            'student/take_exam.html',
            exam=exam,
            questions=questions,
            student_exam=student_exam,
            time_remaining=time_remaining,
            existing_answers=existing_answers
        )

    @app.route('/api/save-answer/<int:student_exam_id>', methods=['POST'])
    @login_required
    def api_save_answer(student_exam_id):
        """Save or update a student's answer (AJAX endpoint)."""
        data = request.get_json() or {}
        question_id = data.get('question_id')
        selected_answer = str(data.get('selected_answer', '0')).strip()

        # Validate ownership
        student_exam = StudentExam.query.get_or_404(student_exam_id)
        if student_exam.student_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        # Check if exam already submitted
        if student_exam.status == 'submitted':
            return jsonify({"error": "Exam already submitted"}), 400

        # Find or create answer
        answer = StudentAnswer.query.filter_by(
            student_exam_id=student_exam.id,
            question_id=question_id
        ).first()

        if not answer:
            answer = StudentAnswer(
                student_exam_id=student_exam.id,
                question_id=question_id,
                selected_answer=selected_answer
            )
            db.session.add(answer)
        else:
            answer.selected_answer = selected_answer

        db.session.commit()
        return jsonify({"status": "success", "saved_answer": selected_answer})

    @app.route('/api/update-tabcount/<int:student_exam_id>', methods=['POST'])
    @login_required
    def api_update_tabcount(student_exam_id):
        """Update the number of tab switches."""
        data = request.get_json() or {}
        new_count = int(data.get('tab_switch_count', 0))

        student_exam = StudentExam.query.get_or_404(student_exam_id)
        if student_exam.student_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        student_exam.tab_switch_count = new_count
        db.session.commit()

        return jsonify({"status": "updated", "tab_switch_count": new_count})
    # ================================
    # Log Activity
    # ================================
    @app.route('/api/log-activity/<int:student_exam_id>', methods=['POST'])
    @login_required
    def api_log_activity(student_exam_id):
        """Log tab switches, screenshot attempts, or other suspicious activities."""
        data = request.get_json() or {}
        activity_type = data.get('activity_type', 'unknown')
        description = data.get('description', '')
        severity = data.get('severity', 'low')

        student_exam = StudentExam.query.get_or_404(student_exam_id)
        if student_exam.student_id != current_user.id:
            return jsonify({"error": "Unauthorized"}), 403

        log = ActivityLog(
            student_exam_id=student_exam.id,
            activity_type=activity_type,
            description=description,
            severity=severity
        )
        db.session.add(log)
        db.session.commit()

        return jsonify({"status": "logged"})
    def assign_shuffle(student_exam):
        """Create a persistent shuffled question & option order for a new StudentExam."""
        import random, json

        exam = student_exam.exam
        questions = Question.query.filter_by(exam_id=exam.id).all()
        random.shuffle(questions)
        q_order = [q.id for q in questions]
        option_mapping = {}

        for q in questions:
            options = ['A', 'B', 'C', 'D']
            random.shuffle(options)
            option_mapping[str(q.id)] = options

        student_exam.question_order = json.dumps(q_order)
        student_exam.option_mapping = json.dumps(option_mapping)
        db.session.commit()

    @app.route("/api/check-exam-status/<int:student_exam_id>")
    @login_required
    def api_check_exam_status(student_exam_id):
        """Check if exam was force-ended by faculty"""
        try:
            # Use SQLAlchemy ORM instead of raw SQL
            student_exam = StudentExam.query.get(student_exam_id)
            
            if not student_exam:
                return jsonify({"error": "Not found"}), 404
            
            # Verify student access
            if student_exam.student_id != current_user.id:
                return jsonify({"error": "Unauthorized"}), 403
            
            # Get exam to check force_ended status
            exam = student_exam.exam
            
            # Check if exam was force-ended
            force_ended = getattr(exam, 'force_ended', False) or False
            force_ended_at = getattr(exam, 'force_ended_at', None)
            
            # Get updated end time if duration was extended
            updated_end_time = None
            if hasattr(exam, 'end_time') and exam.end_time:
                updated_end_time = exam.end_time.isoformat()
            elif student_exam.started_at and exam.duration_minutes:
                from datetime import timedelta
                end_time = student_exam.started_at + timedelta(minutes=exam.duration_minutes)
                updated_end_time = end_time.isoformat()
            
            return jsonify({
                "force_ended": force_ended,
                "force_ended_at": force_ended_at.isoformat() if force_ended_at else None,
                "updated_end_time": updated_end_time,
                "exam_status": getattr(exam, 'status', 'active')
            })
            
        except Exception as e:
            print(f"❌ Error checking exam status: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route('/api/save-answer', methods=['POST'])
    @login_required
    def save_answer():
        """Save answer"""
        data = request.json
        student_exam_id = data.get('student_exam_id')
        question_id = data.get('question_id')
        selected_answer = data.get('selected_answer')
        
        student_exam = StudentExam.query.get(student_exam_id)
        
        if not student_exam or student_exam.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        answer = Answer.query.filter_by(
            student_exam_id=student_exam_id,
            question_id=question_id
        ).first()
        
        if answer:
            answer.selected_answer = selected_answer
            answer.answered_at = datetime.utcnow()
        else:
            answer = Answer(
                student_exam_id=student_exam_id,
                question_id=question_id,
                selected_answer=selected_answer
            )
            db.session.add(answer)
        
        db.session.commit()
        
        return jsonify({'success': True})

    @app.route('/api/log-activity', methods=['POST'])
    @login_required
    def log_activity():
        """Log activity"""
        data = request.json
        student_exam_id = data.get('student_exam_id')
        activity_type = data.get('activity_type')
        description = data.get('description', '')
        severity = data.get('severity', 'low')
        
        student_exam = StudentExam.query.get(student_exam_id)
        
        if not student_exam or student_exam.student_id != current_user.id:
            return jsonify({'success': False, 'error': 'Unauthorized'}), 403
        
        activity_log = ActivityLog(
            student_exam_id=student_exam_id,
            activity_type=activity_type,
            description=description,
            severity=severity
        )
        
        db.session.add(activity_log)
        
        if activity_type == 'tab_switch':
            student_exam.tab_switch_count += 1
        
        student_exam.suspicious_activity_count += 1
        
        db.session.commit()
        
        return jsonify({
            'success': True,
            'tab_switch_count': student_exam.tab_switch_count,
            'max_allowed': student_exam.exam.max_tab_switches
        })

    @app.route('/submit_exam/<int:student_exam_id>', methods=['POST', 'GET'])
    @login_required
    def submit_exam(student_exam_id):
        """
        Finalize and grade a student's exam.
        This endpoint will:
        - treat missing answers as "0"
        - mark StudentAnswer.is_correct and points_earned
        - compute StudentExam.score, total_points, percentage, passed flag
        - mark status='submitted' and set submitted_at
        """
        student_exam = StudentExam.query.get_or_404(student_exam_id)

        # Security checks
        if current_user.role != 'student' or student_exam.student_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        if student_exam.status == 'submitted':
            flash('Exam already submitted', 'info')
            return redirect(url_for('exam_result', student_exam_id=student_exam_id))

        exam = student_exam.exam
        if not exam:
            flash('Exam record missing or deleted', 'error')
            return redirect(url_for('student_dashboard'))

        # Load questions for this exam ONLY
        questions = Question.query.filter_by(exam_id=exam.id).all()
        total_questions = len(questions)

        # Build quick lookup for existing StudentAnswer rows
        existing_answers = {a.question_id: a for a in StudentAnswer.query.filter_by(student_exam_id=student_exam.id).all()}

        total_points = 0.0
        score = 0.0

        for q in questions:
            total_points += (q.points or 0.0)

            ans = existing_answers.get(q.id)
            if ans is None:
                # create unanswered answer with "0"
                ans = StudentAnswer(
                    student_exam_id=student_exam.id,
                    question_id=q.id,
                    selected_answer="0",
                    is_correct=False,
                    points_earned=0.0,
                    answered_at=datetime.utcnow()
                )
                db.session.add(ans)
            else:
                # normalize selected_answer to string
                sel = (ans.selected_answer or "").strip()
                if sel == "" or sel == "0":
                    ans.selected_answer = "0"
                    ans.is_correct = False
                    ans.points_earned = 0.0
                else:
                    # check correctness (compare to q.correct_answer)
                    if q.correct_answer and sel.upper() == q.correct_answer.upper():
                        ans.is_correct = True
                        ans.points_earned = q.points or 0.0
                    else:
                        ans.is_correct = False
                        ans.points_earned = 0.0

                # update answered_at if missing
                if not ans.answered_at:
                    ans.answered_at = datetime.utcnow()

            # sum score
            score += (ans.points_earned or 0.0)

        # Avoid division by zero
        percentage = (score / total_points * 100.0) if total_points > 0 else 0.0
        passed = (percentage >= (exam.passing_score or 0.0))

        # Update student_exam
        student_exam.score = score
        student_exam.total_points = total_points
        student_exam.percentage = round(percentage, 2)
        student_exam.passed = passed
        student_exam.submitted_at = datetime.utcnow()
        student_exam.status = 'submitted'
        student_exam.completed = True

        # time_taken_minutes: difference between submitted_at and started_at
        if student_exam.started_at:
            delta_min = (student_exam.submitted_at - student_exam.started_at).total_seconds() / 60.0
            student_exam.time_taken_minutes = int(round(delta_min))
        else:
            student_exam.time_taken_minutes = None

        db.session.commit()

        flash('Exam submitted successfully.', 'success')
        return redirect(url_for('exam_result', student_exam_id=student_exam.id))

    @app.route('/student/exam/<int:student_exam_id>/result')
    @login_required
    def exam_result(student_exam_id):
        """View result"""
        if current_user.role != 'student':
            flash('Access denied', 'error')
            return redirect(url_for('faculty_dashboard'))
        
        student_exam = StudentExam.query.get_or_404(student_exam_id)
        
        if student_exam.student_id != current_user.id:
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        if student_exam.status != 'submitted':
            flash('Exam not yet submitted', 'error')
            return redirect(url_for('take_exam', student_exam_id=student_exam_id))
        
        answers_with_questions = []
        for answer in student_exam.answers:
            question = Question.query.get(answer.question_id)
            answers_with_questions.append({
                'question': question,
                'answer': answer
            })
        
        return render_template('student/result.html',
                             student_exam=student_exam,
                             exam=student_exam.exam,
                             answers_with_questions=answers_with_questions)

    @app.route('/student/<int:student_id>/profile')
    @login_required
    def student_profile(student_id):
        """View student profile (Public view)"""
        student = User.query.get_or_404(student_id)
        
        if student.role != 'student':
            flash('Invalid student', 'error')
            return redirect(url_for('index'))
        
        student_exams = StudentExam.query.filter_by(
            student_id=student.id,
            status='submitted'
        ).order_by(StudentExam.submitted_at.desc()).all()

        completed_exams = student_exams
        total_exams = len(completed_exams)
        avg_score = sum(se.percentage for se in completed_exams) / total_exams if total_exams else 0
        passed_exams = [se for se in completed_exams if se.passed]
        pass_rate = (len(passed_exams) / total_exams * 100) if total_exams else 0
        best_score = max((se.percentage for se in completed_exams), default=0)

        return render_template(
            'student/student_profile.html',
            student=student,
            completed_exams=completed_exams,
            total_exams=total_exams,
            avg_score=avg_score,
            pass_rate=pass_rate,
            best_score=best_score
        )


    @app.route('/faculty/students')
    @login_required
    def faculty_student_list():
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        q = request.args.get('q', '').strip()
        batch = request.args.get('batch')
        department = request.args.get('department')
        verified = request.args.get('verified')
        has_phone = request.args.get('has_phone')
        sort = request.args.get('sort')

        query = User.query.filter(User.role == 'student')

        if q:
            like = f"%{q}%"
            query = query.filter(
                db.or_(
                    User.full_name.ilike(like),
                    User.username.ilike(like),
                    User.email.ilike(like),
                    User.prn_number.ilike(like),
                    User.roll_id.ilike(like),
                    User.batch.ilike(like)
                )
            )

        if batch:
            query = query.filter(User.batch == batch)
        if department:
            query = query.filter(User.department == department)
        if verified == 'true':
            query = query.filter(User.is_verified == True)
        if verified == 'false':
            query = query.filter(User.is_verified == False)
        if has_phone == '1':
            query = query.filter(User.phone != None).filter(User.phone != '')

        if sort == 'name':
            query = query.order_by(User.full_name.asc())
        elif sort == 'batch':
            query = query.order_by(User.batch.asc())
        else:
            query = query.order_by(User.created_at.desc())

        students = query.all()

        batches = [b[0] for b in db.session.query(User.batch).distinct().all() if b[0]]
        departments = [d[0] for d in db.session.query(User.department).distinct().all() if d[0]]

        return render_template(
            'faculty/manage_students.html',
            students=students,
            batches=batches,
            departments=departments
        )

    @app.route('/faculty/import_students', methods=['POST'])
    @login_required
    def faculty_import_students():
        """
        Faculty imports students from CSV, Excel, or JSON files with proper number formatting
        Optionally assigns them to an exam and generates shuffled question/option orders
        """
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        file = request.files.get('file')
        if not file or file.filename == '':
            flash('No file selected', 'error')
            return redirect(url_for('faculty_student_list'))

        filename = secure_filename(file.filename)
        ext = filename.rsplit('.', 1)[-1].lower()

        # ✅ Allow JSON too
        if ext not in ('csv', 'xlsx', 'xls', 'json'):
            flash('Invalid file format. Please upload CSV, Excel, or JSON file.', 'error')
            return redirect(url_for('faculty_student_list'))

        print(f"[DEBUG] Received file: {file.filename}")

        try:
            # ✅ Step 1: Read file
            if ext == 'csv':
                try:
                    df = pd.read_csv(file, encoding='utf-8', dtype=str)
                except UnicodeDecodeError:
                    file.stream.seek(0)
                    df = pd.read_csv(file, encoding='utf-8-sig', dtype=str)
            elif ext in ('xlsx', 'xls'):
                df = pd.read_excel(file, dtype=str)
            elif ext == 'json':
                try:
                    data = json.load(file)
                except Exception as e:
                    flash(f'Invalid JSON file: {str(e)}', 'error')
                    return redirect(url_for('faculty_student_list'))

                if not isinstance(data, list):
                    flash('JSON must be an array of student objects.', 'error')
                    return redirect(url_for('faculty_student_list'))

                df = pd.DataFrame(data, dtype=str)

            print(f"[DEBUG] Columns: {df.columns.tolist()}")
            print(f"[DEBUG] Total rows: {len(df)}")

            if df.empty:
                flash('The file is empty or has no data rows.', 'error')
                return redirect(url_for('faculty_student_list'))

            # Normalize column names
            df.columns = df.columns.str.strip().str.lower().str.replace(' ', '_')

            added, skipped = 0, 0
            errors = []

            def clean_string(value):
                if pd.isna(value) or value == '':
                    return ''
                return str(value).strip()

            def validate_prn(prn):
                if not prn:
                    return True
                prn_clean = prn.replace('.', '').replace(' ', '')
                return prn_clean.isdigit() and len(prn_clean) == 12

            # ✅ Optional: attach students directly to a specific exam
            exam_id = request.args.get('exam_id', type=int)
            exam = Exam.query.get(exam_id) if exam_id else None

            # ✅ Process each row
            for index, row in df.iterrows():
                try:
                    email = clean_string(row.get('email')).lower()
                    if not email:
                        errors.append(f"Row {index + 2}: Missing required email")
                        skipped += 1
                        continue

                    existing = User.query.filter_by(email=email).first()
                    if existing:
                        print(f"[DEBUG] Skipped duplicate email: {email}")
                        skipped += 1
                        continue

                    prn_raw = clean_string(row.get('prn_number'))
                    prn_clean = prn_raw.replace('.', '').replace(' ', '') if prn_raw else ''

                    if prn_clean and not validate_prn(prn_raw):
                        errors.append(f"Row {index + 2}: PRN must be exactly 12 digits (got '{prn_raw}')")
                        skipped += 1
                        continue

                    if prn_clean:
                        existing_prn = User.query.filter_by(prn_number=prn_clean).first()
                        if existing_prn:
                            errors.append(f"Row {index + 2}: PRN {prn_clean} already exists")
                            skipped += 1
                            continue

                    password = clean_string(row.get('password')) or 'Student@123'
                    hashed_pw = generate_password_hash(password)

                    student_data = {
                        "username": clean_string(row.get('username')) or email.split('@')[0],
                        "email": email,
                        "full_name": clean_string(row.get('full_name')),
                        "prn_number": prn_clean,
                        "roll_id": clean_string(row.get('roll_id')),
                        "batch": clean_string(row.get('batch')),
                        "department": clean_string(row.get('department')),
                        "phone": clean_string(row.get('phone')),
                        "gender": clean_string(row.get('gender')).capitalize(),
                        "password_hash": hashed_pw
                    }

                    is_verified = False
                    if 'is_verified' in row and str(row['is_verified']).lower() in ('true', '1', 'yes'):
                        is_verified = True

                    if not student_data["username"] or not student_data["email"]:
                        errors.append(f"Row {index + 2}: Missing username/email")
                        skipped += 1
                        continue

                    # ✅ Create the student
                    student = User()
                    student.set_as_student(student_data, verified=is_verified)
                    db.session.add(student)
                    db.session.commit()

                    # ✅ If exam provided, assign and shuffle
                    if exam:
                        student_exam = StudentExam(student_id=student.id, exam_id=exam.id)
                        db.session.add(student_exam)
                        db.session.commit()

                        # 🔀 Assign shuffled question & option order
                        assign_shuffle(student_exam)

                    added += 1

                    if added % 50 == 0:
                        db.session.commit()
                        print(f"[DEBUG] Interim commit after {added} records")

                except Exception as e:
                    traceback.print_exc()
                    error_msg = f"Row {index + 2}: {str(e)}"
                    print(f"[DEBUG] Error -> {error_msg}")
                    errors.append(error_msg)
                    skipped += 1
                    db.session.rollback()
                    continue

            db.session.commit()

            summary = f"✅ {added} added | ⚠️ {skipped} skipped"
            flash(summary, 'success')

            if errors:
                print("[DEBUG] --- ERRORS SUMMARY ---")
                for err in errors:
                    print(err)
                flash(f"{len(errors)} issue(s) encountered.", 'warning')

            print(f"[DEBUG] Import complete: {added} added, {skipped} skipped.")
            return redirect(url_for('faculty_student_list'))

        except Exception as e:
            db.session.rollback()
            traceback.print_exc()
            flash(f"Error processing file: {str(e)}", 'error')
            return redirect(url_for('faculty_student_list'))



    @app.route('/faculty/export_students')
    @login_required
    def faculty_export_students():
        """Export students to CSV"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))

        q = request.args.get('q', '').strip()
        batch = request.args.get('batch')
        department = request.args.get('department')
        verified = request.args.get('verified')
        has_phone = request.args.get('has_phone')
        sort_by = request.args.get('sort')
        selected_ids = request.args.getlist('ids')

        query = User.query.filter(User.role == 'student')

        if selected_ids:
            try:
                id_list = [int(id_str) for id_str in selected_ids if id_str.isdigit()]
                query = query.filter(User.id.in_(id_list))
            except ValueError:
                flash('Invalid student IDs provided', 'error')
                return redirect(url_for('faculty_student_list'))
        else:
            if q:
                like = f"%{q}%"
                query = query.filter(
                    db.or_(
                        User.full_name.ilike(like),
                        User.username.ilike(like),
                        User.email.ilike(like),
                        User.prn_number.ilike(like),
                        User.roll_id.ilike(like),
                        User.batch.ilike(like)
                    )
                )
            
            if batch:
                query = query.filter(User.batch == batch)
            if department:
                query = query.filter(User.department == department)
            if verified == 'true':
                query = query.filter(User.is_verified == True)
            elif verified == 'false':
                query = query.filter(User.is_verified == False)
            if has_phone == '1':
                query = query.filter(User.phone.isnot(None), User.phone != '')

        if sort_by == 'name':
            query = query.order_by(User.full_name.asc())
        elif sort_by == 'batch':
            query = query.order_by(User.batch.asc(), User.roll_id.asc())
        else:
            query = query.order_by(User.created_at.desc())

        students = query.all()

        if not students:
            flash('No students found to export', 'warning')
            return redirect(url_for('faculty_student_list'))

        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'ID', 'Username', 'Email', 'Full Name', 'PRN Number', 'Roll ID',
            'Batch', 'Department', 'Phone', 'Gender', 'Verified', 'Created Date',
            'Total Exams', 'Average Score'
        ])
        
        for student in students:
            student_exams = StudentExam.query.filter_by(
                student_id=student.id,
                status='submitted'
            ).all()
            
            total_exams = len(student_exams)
            avg_score = (sum(se.percentage for se in student_exams) / total_exams) if total_exams > 0 else 0
            
            writer.writerow([
                student.id,
                student.username,
                student.email,
                student.full_name or '',
                student.prn_number or '',
                student.roll_id or '',
                student.batch or '',
                student.department or '',
                student.phone or '',
                student.gender or '',
                'Yes' if student.is_verified else 'No',
                student.created_at.strftime('%Y-%m-%d %H:%M:%S') if student.created_at else '',
                total_exams,
                f"{avg_score:.2f}%" if total_exams > 0 else 'N/A'
            ])
        
        output.seek(0)
        
        timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
        
        if selected_ids:
            filename = f"students_selected_{len(students)}_{timestamp}.csv"
        elif q or batch or department or verified:
            filename = f"students_filtered_{len(students)}_{timestamp}.csv"
        else:
            filename = f"students_all_{len(students)}_{timestamp}.csv"
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )

    @app.route('/faculty/download_template')
    @login_required
    def download_student_template():
        """Download CSV template"""
        if current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('student_dashboard'))
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        writer.writerow([
            'username', 'email', 'full_name', 'prn_number', 'roll_id',
            'batch', 'department', 'phone', 'gender', 'password', 'is_verified'
        ])
        
        writer.writerow([
            'johndoe', 'john.doe@university.edu', 'John Doe', '2508403250',
            'CS-2024-001', '2024', 'Computer Science', '+1234567890',
            'Male', 'Student@123', 'true'
        ])
        
        writer.writerow([
            'janesmith', 'jane.smith@university.edu', 'Jane Smith', '2508403251',
            'CS-2024-002', '2024', 'Computer Science', '+1234567891',
            'Female', 'Student@123', 'false'
        ])
        
        output.seek(0)
        
        return Response(
            output.getvalue(),
            mimetype='text/csv',
            headers={
                "Content-Disposition": "attachment; filename=student_import_template.csv",
                "Content-Type": "text/csv; charset=utf-8"
            }
        )

    @app.route('/faculty/delete_student/<int:student_id>', methods=['POST'])
    @login_required
    def faculty_delete_student(student_id):
        """Delete single student"""
        if current_user.role != 'faculty':
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        student = User.query.get(student_id)
        if not student:
            return jsonify({'success': False, 'error': 'Student not found'}), 404
        
        if student.role != 'student':
            return jsonify({'success': False, 'error': 'Can only delete students'}), 400
        
        try:
            # Delete related records first
            StudentExam.query.filter_by(student_id=student_id).delete()
            db.session.delete(student)
            db.session.commit()
            return jsonify({'success': True, 'message': 'Student deleted successfully'})
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Delete failed: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/faculty/delete_students', methods=['POST'])
    @login_required
    def faculty_delete_students():
        """Delete multiple students"""
        if current_user.role != 'faculty':
            return jsonify({'success': False, 'error': 'Access denied'}), 403
        
        data = request.get_json() or {}
        ids = data.get('ids') or []
        
        if not ids:
            return jsonify({'success': False, 'error': 'No IDs provided'}), 400
        
        try:
            # Delete related records first
            StudentExam.query.filter(StudentExam.student_id.in_(ids)).delete(synchronize_session=False)
            
            # Delete students
            deleted_count = User.query.filter(
                User.id.in_(ids),
                User.role == 'student'
            ).delete(synchronize_session=False)
            
            db.session.commit()
            
            return jsonify({
                'success': True,
                'message': f'Successfully deleted {deleted_count} student(s)',
                'deleted_count': deleted_count
            })
        except Exception as e:
            db.session.rollback()
            print(f"[ERROR] Bulk delete failed: {str(e)}")
            traceback.print_exc()
            return jsonify({'success': False, 'error': str(e)}), 500

    @app.route('/student/exam/<int:student_exam_id>/download-pdf')
    @login_required
    def download_result_pdf(student_exam_id):
        """Download PDF - accessible by student and faculty"""
        student_exam = StudentExam.query.get_or_404(student_exam_id)
        
        # Allow access for the student who took the exam or faculty members
        if current_user.role == 'student':
            if student_exam.student_id != current_user.id:
                flash('Access denied', 'error')
                return redirect(url_for('student_dashboard'))
        elif current_user.role != 'faculty':
            flash('Access denied', 'error')
            return redirect(url_for('index'))
        
        if student_exam.status != 'submitted':
            flash('Exam not yet submitted', 'error')
            if current_user.role == 'student':
                return redirect(url_for('take_exam', student_exam_id=student_exam_id))
            else:
                return redirect(url_for('faculty_dashboard'))
        
        answers_with_questions = []
        for answer in student_exam.answers:
            question = Question.query.get(answer.question_id)
            answers_with_questions.append({
                'question': question,
                'answer': answer
            })
        
        # Get the actual student for the PDF (in case faculty is downloading)
        student = User.query.get(student_exam.student_id)
        
        pdf_buffer = generate_result_pdf(
            student_exam,
            student_exam.exam,
            student,  # Use the student who took the exam, not current_user
            answers_with_questions
        )
        
        filename = f"Result_{student.username}_{student_exam.exam.title.replace(' ', '_')}.pdf"
        
        return send_file(
            pdf_buffer,
            as_attachment=True,
            download_name=filename,
            mimetype='application/pdf'
        )

    @app.route('/faculty/student/<int:student_id>/edit', methods=['GET', 'POST'])
    @login_required
    def faculty_edit_student(student_id):
        """Edit student details"""
        if current_user.role != 'faculty':
            flash('Access denied. Faculty only.', 'error')
            return redirect(url_for('faculty_dashboard'))

        student = User.query.get_or_404(student_id)

        if request.method == 'POST':
            student.full_name = request.form.get('full_name')
            student.email = request.form.get('email')
            student.phone = request.form.get('phone')
            student.gender = request.form.get('gender')
            student.prn_number = request.form.get('prn_number')
            student.roll_id = request.form.get('roll_id')
            student.batch = request.form.get('batch')
            student.department = request.form.get('department')
            student.is_verified = request.form.get('is_verified') == 'true'

            db.session.commit()
            flash('Student information updated successfully!', 'success')
            return redirect(url_for('faculty_student_list'))

        return render_template('faculty/edit_student.html', student=student)

    @app.route('/global_leaderboard', methods=['GET'])
    @login_required
    def global_leaderboard():
        # Date filters (strings from query)
        start_date = request.args.get('start')
        end_date = request.args.get('end')

        # Parse to datetime objects (or None)
        try:
            start_dt = datetime.strptime(start_date, "%Y-%m-%d") if start_date else None
            end_dt = datetime.strptime(end_date, "%Y-%m-%d") if end_date else None
        except Exception:
            start_dt = end_dt = None

        # Batch filter (passed from front-end)
        batch = request.args.get('batch')

        # Fetch exams within date range
        exam_query = Exam.query
        if start_dt:
            exam_query = exam_query.filter(Exam.created_at >= start_dt)
        if end_dt:
            # include the whole end day by setting to end of day if desired; keeping simple <= end_dt
            exam_query = exam_query.filter(Exam.created_at <= end_dt)

        exams = exam_query.all()
        exam_ids = [e.id for e in exams]

        # Calculate total possible marks
        exam_total_map = {}
        total_possible_marks = 0
        for ex in exams:
            tm = getattr(ex, "total_marks", None)
            if not tm:
                # sum question points fallback
                tm = db.session.query(func.coalesce(func.sum(Question.points), 0)).filter(Question.exam_id == ex.id).scalar() or 0
            exam_total_map[ex.id] = tm
            total_possible_marks += tm

        # Fetch students; apply batch filter if provided
        students_q = User.query.filter_by(role='student').order_by(User.full_name.asc())
        if batch:
            # assume User has attribute 'batch'
            students_q = students_q.filter(getattr(User, 'batch') == batch)
        students = students_q.all()

        leaderboard_data = []

        for student in students:
            # Student exams in selected range (only exams we fetched)
            student_exams = StudentExam.query.filter(
                StudentExam.student_id == student.id,
                StudentExam.exam_id.in_(exam_ids)
            ).all()

            exams_attempted = len(student_exams)

            # Total questions solved: count StudentAnswer rows joined to StudentExam and restricted by submitted_at if dates provided
            sa_query = db.session.query(StudentAnswer).join(StudentExam, StudentAnswer.student_exam_id == StudentExam.id).filter(
                StudentExam.student_id == student.id,
                StudentExam.exam_id.in_(exam_ids)
            )

            if start_dt and end_dt:
                sa_query = sa_query.filter(StudentExam.submitted_at.between(start_dt, end_dt))
            elif start_dt:
                sa_query = sa_query.filter(StudentExam.submitted_at >= start_dt)
            elif end_dt:
                sa_query = sa_query.filter(StudentExam.submitted_at <= end_dt)

            total_questions_attempted = sa_query.count()

            # Total marks obtained (use StudentExam.score if present else sum StudentAnswer.points_earned)
            total_marks_obtained = 0
            for se in student_exams:
                if se.score is not None:
                    try:
                        total_marks_obtained += float(se.score)
                    except Exception:
                        # ignore bad types, fallback to answers
                        pts = db.session.query(func.coalesce(func.sum(StudentAnswer.points_earned), 0)).filter(
                            StudentAnswer.student_exam_id == se.id
                        ).scalar() or 0
                        total_marks_obtained += pts
                else:
                    pts = db.session.query(func.coalesce(func.sum(StudentAnswer.points_earned), 0)).filter(
                        StudentAnswer.student_exam_id == se.id
                    ).scalar() or 0
                    total_marks_obtained += pts

            percentage = (total_marks_obtained / total_possible_marks * 100) if total_possible_marks else 0

            leaderboard_data.append({
                "name": student.full_name,
                "prn": student.prn_number,
                "exams_attempted": exams_attempted,
                "total_questions": total_questions_attempted,
                "marks_obtained": round(total_marks_obtained, 2),
                "possible_marks": total_possible_marks,
                "percentage": round(percentage, 2)
            })

        # ===== Server-side column filters (optional; frontend will send col_xxx params) =====
        # Supported params:
        #   col_1_txt -> PRN substring
        #   col_2_txt -> Name substring
        #   col_3_min -> Min attempts (exams_attempted)
        #   col_4_min -> Min total_questions
        #   col_5_min -> Min marks_obtained
        #   col_7_min -> Min percentage
        def apply_column_filters(data):
            # read relevant query params
            filters = {
                'prn_txt': request.args.get('col_1_txt'),
                'name_txt': request.args.get('col_2_txt'),
                'attempts_min': request.args.get('col_3_min'),
                'answered_min': request.args.get('col_4_min'),
                'marks_min': request.args.get('col_5_min'),
                'pct_min': request.args.get('col_7_min'),
            }

            def keep(item):
                # text filters (case-insensitive)
                if filters['prn_txt']:
                    if filters['prn_txt'].strip().lower() not in str(item.get('prn', '')).lower():
                        return False
                if filters['name_txt']:
                    if filters['name_txt'].strip().lower() not in str(item.get('name', '')).lower():
                        return False

                # numeric min filters
                try:
                    if filters['attempts_min']:
                        if int(item.get('exams_attempted', 0)) < int(filters['attempts_min']):
                            return False
                except ValueError:
                    pass
                try:
                    if filters['answered_min']:
                        if int(item.get('total_questions', 0)) < int(filters['answered_min']):
                            return False
                except ValueError:
                    pass
                try:
                    if filters['marks_min']:
                        if float(item.get('marks_obtained', 0)) < float(filters['marks_min']):
                            return False
                except ValueError:
                    pass
                try:
                    if filters['pct_min']:
                        if float(item.get('percentage', 0)) < float(filters['pct_min']):
                            return False
                except ValueError:
                    pass

                return True

            return [it for it in data if keep(it)]

        leaderboard_data = apply_column_filters(leaderboard_data)

        # Sort leaderboard (best first)
        leaderboard_data.sort(
            key=lambda x: (x["marks_obtained"], x["exams_attempted"], x["total_questions"]),
            reverse=True
        )

        # Compute "how behind"
        if leaderboard_data:
            top_marks = leaderboard_data[0]["marks_obtained"]
            top_attempt = leaderboard_data[0]["exams_attempted"]

            for item in leaderboard_data:
                item["behind_marks"] = round(top_marks - item["marks_obtained"], 2)
                item["behind_attempts"] = top_attempt - item["exams_attempted"]

        # Prepare batches list for template (unique sorted values from users)
        # If User doesn't have batch attribute, this will safely produce an empty list
        try:
            batches = sorted({ getattr(u, 'batch') for u in User.query.filter_by(role='student').all() if getattr(u, 'batch', None) })
        except Exception:
            batches = []

        return render_template(
            "leaderboard.html",
            leaderboard=leaderboard_data,
            start_date=start_date,
            end_date=end_date,
            batches=batches
        )
    @app.route('/api/check-exam-status/<int:student_exam_id>', methods=['GET'])
    @login_required
    def check_exam_status(student_exam_id):
        """
        Check if exam has been force-ended by faculty or time extended
        Students poll this endpoint every 5 seconds during exam
        """
        try:
            student_exam = StudentExam.query.get_or_404(student_exam_id)
            
            # Verify student owns this exam
            if student_exam.student_id != current_user.id:
                return jsonify({"error": "Unauthorized"}), 403
            
            exam = Exam.query.get(student_exam.exam_id)
            
            if not exam:
                return jsonify({"error": "Exam not found"}), 404
            
            response = {
                "force_ended": getattr(exam, 'force_ended', False),
                "exam_status": getattr(exam, 'status', 'active'),
                "updated_end_time": None,
                "current_time": datetime.utcnow().isoformat()
            }
            
            # Calculate expected end time based on start + duration
            if student_exam.started_at and exam.duration_minutes:
                from datetime import timedelta
                expected_end = student_exam.started_at + timedelta(minutes=exam.duration_minutes)
                response["updated_end_time"] = expected_end.isoformat()
                
                # Calculate remaining time in seconds
                now = datetime.utcnow()
                remaining = (expected_end - now).total_seconds()
                response["remaining_seconds"] = max(0, int(remaining))
            
            return jsonify(response)
            
        except Exception as e:
            print(f"❌ Error checking exam status: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500


    @app.route('/faculty/force-end-exam/<int:exam_id>', methods=['POST'])
    @login_required
    def faculty_force_end_exam(exam_id):
        if current_user.role not in ['faculty', 'admin']:
            flash('❌ Unauthorized access.', 'error')
            return redirect(url_for('index'))
        
        try:
            exam = Exam.query.get_or_404(exam_id)
            
            if getattr(exam, 'force_ended', False) or getattr(exam, 'status', 'active') == 'ended':
                flash('⚠️ This exam has already been ended.', 'warning')
                return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
            exam.force_ended = True
            exam.status = 'ended'
            
            active_exams = StudentExam.query.filter_by(
                exam_id=exam_id,
                submitted_at=None
            ).all()
            
            print(f"🔴 Force-ending exam '{exam.title}' (ID: {exam_id})")
            print(f"📊 Found {len(active_exams)} active student exam(s)")
            
            from datetime import datetime
            submission_time = datetime.utcnow()
            
            for student_exam in active_exams:
                student_exam.submitted_at = submission_time
                student_exam.force_ended = True
                student_exam.status = 'completed'
                student_exam.completed = True
                
                if student_exam.started_at:
                    time_taken = (submission_time - student_exam.started_at).total_seconds() / 60
                    student_exam.time_taken_minutes = int(time_taken)
                
                try:
                    calculate_student_score(student_exam.id)
                    print(f"✅ Scored student exam ID: {student_exam.id}")
                except Exception as score_error:
                    print(f"⚠️ Error scoring student exam {student_exam.id}: {score_error}")
            
            db.session.commit()
            
            print(f"✅ Exam force-ended successfully. {len(active_exams)} student(s) auto-submitted.")
            
            flash(
                f'✅ Exam "{exam.title}" has been ended. '
                f'{len(active_exams)} student(s) auto-submitted and scored.',
                'success'
            )
            return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error ending exam: {e}")
            import traceback
            traceback.print_exc()
            flash(f'❌ Error ending exam: {str(e)}', 'error')
            return redirect(url_for('faculty_dashboard'))


    @app.route('/faculty/extend-exam-time/<int:exam_id>', methods=['POST'])
    @login_required
    def faculty_extend_exam_time(exam_id):
        if current_user.role not in ['faculty', 'admin']:
            return jsonify({"error": "Unauthorized"}), 403
        
        try:
            exam = Exam.query.get_or_404(exam_id)
            extra_minutes = int(request.form.get('extra_minutes', 0))
            
            if extra_minutes <= 0:
                flash('❌ Invalid extension time. Must be at least 1 minute.', 'error')
                return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
            if extra_minutes > 120:
                flash('❌ Cannot extend by more than 120 minutes at once.', 'error')
                return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
            if getattr(exam, 'force_ended', False) or getattr(exam, 'status', 'active') == 'ended':
                flash('⚠️ Cannot extend time for an ended exam.', 'warning')
                return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
            old_duration = exam.duration_minutes or 60
            exam.duration_minutes = old_duration + extra_minutes
            db.session.commit()
            
            print(f"⏰ Exam '{exam.title}' extended from {old_duration} to {exam.duration_minutes} minutes")
            
            flash(
                f'✅ Exam time extended by {extra_minutes} minutes. '
                f'New duration: {exam.duration_minutes} minutes.',
                'success'
            )
            return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
        except ValueError:
            flash('❌ Invalid input. Please enter a valid number.', 'error')
            return redirect(url_for('faculty_dashboard'))
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error extending time: {e}")
            import traceback
            traceback.print_exc()
            flash(f'❌ Error extending time: {str(e)}', 'error')
            return redirect(url_for('faculty_dashboard'))    
        # ==========================================
    # OPTIONAL: Reactivate Exam Route
    # ==========================================

    @app.route('/faculty/reactivate-exam/<int:exam_id>', methods=['POST'])
    @login_required
    def faculty_reactivate_exam(exam_id):
        if current_user.role not in ['faculty', 'admin']:
            flash('❌ Unauthorized access.', 'error')
            return redirect(url_for('index'))
        
        try:
            exam = Exam.query.get_or_404(exam_id)
            exam.force_ended = False
            exam.status = 'active'
            db.session.commit()
            
            flash(f'✅ Exam "{exam.title}" has been reactivated.', 'success')
            return redirect(url_for('faculty_dashboard'))  # ← CHANGED
            
        except Exception as e:
            db.session.rollback()
            flash(f'❌ Error reactivating exam: {str(e)}', 'error')
            return redirect(url_for('faculty_dashboard'))


    # ==========================================
    # HELPER: Get Active Student Count
    # ==========================================

    def get_active_student_count(exam_id):
        """
        Get count of students currently taking the exam
        
        Args:
            exam_id: ID of the exam
            
        Returns:
            int: Number of active students
        """
        try:
            count = StudentExam.query.filter_by(
                exam_id=exam_id,
                submitted_at=None
            ).count()
            return count
        except Exception as e:
            print(f"Error getting active student count: {e}")
            return 0


    # ==========================================
    # API: Get Live Exam Statistics
    # ==========================================

    @app.route('/api/exam-stats/<int:exam_id>', methods=['GET'])
    @login_required
    def get_exam_stats(exam_id):
        """
        Get live statistics for an exam
        Faculty can poll this for real-time updates
        """
        if current_user.role not in ['faculty', 'admin']:
            return jsonify({"error": "Unauthorized"}), 403
        
        try:
            exam = Exam.query.get_or_404(exam_id)
            
            # Get counts
            total_attempts = StudentExam.query.filter_by(exam_id=exam_id).count()
            active_attempts = StudentExam.query.filter_by(exam_id=exam_id, submitted_at=None).count()
            completed_attempts = StudentExam.query.filter_by(exam_id=exam_id).filter(
                StudentExam.submitted_at.isnot(None)
            ).count()
            
            # Get average score for completed attempts
            completed_exams = StudentExam.query.filter_by(exam_id=exam_id).filter(
                StudentExam.submitted_at.isnot(None)
            ).all()
            
            avg_score = 0
            if completed_exams:
                scores = [se.percentage for se in completed_exams if se.percentage is not None]
                if scores:
                    avg_score = round(sum(scores) / len(scores), 2)
            
            return jsonify({
                "exam_id": exam_id,
                "exam_title": exam.title,
                "status": getattr(exam, 'status', 'active'),
                "force_ended": getattr(exam, 'force_ended', False),
                "total_attempts": total_attempts,
                "active_attempts": active_attempts,
                "completed_attempts": completed_attempts,
                "average_score": avg_score,
                "timestamp": datetime.utcnow().isoformat()
            })
            
        except Exception as e:
            print(f"Error getting exam stats: {e}")
            return jsonify({"error": str(e)}), 500

    @app.route("/faculty/force-end/<int:student_exam_id>", methods=["POST"])
    @login_required
    def force_end_exam(student_exam_id):
        """Force end a student's exam attempt"""
        try:
            # Verify faculty access
            if current_user.role not in ['faculty', 'admin']:
                return jsonify({"error": "Unauthorized - Faculty only"}), 403
            
            # Get student exam
            student_exam = StudentExam.query.get(student_exam_id)
            
            if not student_exam:
                return jsonify({"error": "Student exam not found"}), 404
            
            # Check if already submitted
            if student_exam.submitted_at:
                return jsonify({
                    "success": False,
                    "message": "Exam already submitted"
                }), 400
            
            # Force end the exam
            from datetime import datetime
            
            student_exam.force_ended = True
            student_exam.status = 'force_ended'
            student_exam.submitted_at = datetime.utcnow()
            
            # Also mark the exam as force-ended (affects all students)
            exam = student_exam.exam
            if exam:
                exam.force_ended = True
                if hasattr(exam, 'force_ended_at'):
                    exam.force_ended_at = datetime.utcnow()
            
            db.session.commit()
            
            print(f"✅ Faculty {current_user.username} force-ended exam for student_exam_id: {student_exam_id}")
            
            return jsonify({
                "success": True,
                "force_ended": True,
                "message": "Exam force-ended successfully"
            })
            
        except Exception as e:
            print(f"❌ Error force-ending exam: {e}")
            db.session.rollback()
            return jsonify({"error": str(e)}), 500

# ==========================================
# COPY-PASTE THIS SECTION INTO YOUR ROUTES.PY
# Add this RIGHT AFTER the force_end_exam route (after line 3008)
# BEFORE adding this, DELETE lines 3010-3473
# ==========================================

    # ==========================================
    # AI PROCTORING ROUTES
    # ==========================================
    
    @app.route('/api/proctor/calibrate/<int:student_exam_id>', methods=['POST'])
    @login_required
    def proctor_calibrate(student_exam_id):
        """Calibrate baseline face position"""
        print(f"🎯 Calibration request for student_exam_id: {student_exam_id}")
        
        try:
            student_exam = StudentExam.query.get_or_404(student_exam_id)
            if student_exam.student_id != current_user.id:
                print("❌ Unauthorized access")
                return jsonify({"status": "error", "message": "Unauthorized"}), 403

            exam = student_exam.exam
            enable_proctoring = getattr(exam, 'enable_proctoring', True)
            
            if not enable_proctoring:
                return jsonify({"status": "ok", "message": "Proctoring disabled", "proctoring_enabled": False})

            data = request.get_json()
            frames_b64 = data.get("frames", [])
            
            print(f"📸 Received {len(frames_b64)} frames")

            if len(frames_b64) < 5:
                return jsonify({"status": "error", "message": "At least 5 frames required"}), 400

            frames = []
            for i, frame_b64 in enumerate(frames_b64):
                img = decode_base64_image(frame_b64)
                if img is not None:
                    frames.append(img)

            if len(frames) < 5:
                return jsonify({"status": "error", "message": "Failed to decode frames"}), 400

            print(f"✅ Decoded {len(frames)} frames")

            proctor_state, vision = get_proctor_instance(student_exam_id, exam)
            
            print("🔍 Performing calibration...")
            ok, info = vision.calibrate(frames)
            
            if not ok:
                print(f"❌ Calibration failed: {info}")
                return jsonify({"status": "error", "message": info}), 400

            calibration = ExamCalibration.query.filter_by(student_exam_id=student_exam_id).first()
            if not calibration:
                calibration = ExamCalibration(student_exam_id=student_exam_id)
                db.session.add(calibration)

            calibration.baseline_yaw = proctor_state.baseline_yaw
            calibration.baseline_pitch = proctor_state.baseline_pitch
            calibration.baseline_roll = proctor_state.baseline_roll
            calibration.calibration_frames = len(frames)

            student_exam.calibration_completed = True
            student_exam.proctoring_enabled = True
            
            db.session.commit()
            print("💾 Saved to database")

            return jsonify({
                "status": "ok",
                "message": "Calibration successful",
                "baseline": {
                    "yaw": float(proctor_state.baseline_yaw),
                    "pitch": float(proctor_state.baseline_pitch),
                    "roll": float(proctor_state.baseline_roll)
                }
            })

        except Exception as e:
            print(f"❌ Calibration error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"status": "error", "message": str(e)}), 500


    @app.route('/api/proctor/analyze/<int:student_exam_id>', methods=['POST'])
    @login_required
    def proctor_analyze_frame(student_exam_id):
        """Analyze frame during exam"""
        try:
            student_exam = StudentExam.query.get_or_404(student_exam_id)
            if student_exam.student_id != current_user.id:
                return jsonify({"status": "error", "message": "Unauthorized"}), 403

            if student_exam.submitted_at:
                return jsonify({"status": "TERMINATED", "message": "Exam submitted"})

            exam = student_exam.exam
            enable_proctoring = getattr(exam, 'enable_proctoring', True)
            proctoring_enabled = getattr(student_exam, 'proctoring_enabled', True)
            
            if not enable_proctoring or not proctoring_enabled:
                return jsonify({"status": "NORMAL", "message": "Proctoring disabled"})

            calibration_completed = getattr(student_exam, 'calibration_completed', False)
            if not calibration_completed:
                return jsonify({"status": "ERROR", "message": "Not calibrated"}), 400

            data = request.get_json()
            frame_b64 = data.get("frame")
            
            if not frame_b64:
                return jsonify({"status": "ERROR", "message": "No frame"}), 400

            frame = decode_base64_image(frame_b64)
            if frame is None:
                return jsonify({"status": "ERROR", "message": "Decode failed"}), 400

            proctor_state, vision = get_proctor_instance(student_exam_id, exam)
            status, details = vision.check_frame(frame)

            if status in ("WARNING", "TERMINATE", "NO_FACE"):
                violation = ExamViolation(
                    student_exam_id=student_exam_id,
                    violation_type=status,
                    severity="high" if status == "TERMINATE" else "medium",
                    message=details.get("message", ""),
                    yaw=details.get("yaw"),
                    pitch=details.get("pitch"),
                    roll=details.get("roll"),
                    deviation_yaw=details.get("dyaw"),
                    deviation_pitch=details.get("dpitch"),
                    deviation_roll=details.get("droll"),
                    faces_detected=details.get("faces_detected", 0)
                )
                db.session.add(violation)

                current_violations = getattr(student_exam, 'total_violations', 0) or 0
                student_exam.total_violations = current_violations + 1
                
                if status == "TERMINATE":
                    student_exam.proctoring_status = "terminated"
                elif student_exam.total_violations >= 3:
                    student_exam.proctoring_status = "warning"
                
                db.session.commit()

            max_violations = getattr(exam, 'max_violations', 3) or 3
            
            return jsonify({
                "status": status,
                "warning_count": proctor_state.warning_count,
                "total_violations": student_exam.total_violations or 0,
                "message": details.get("message", ""),
                "should_terminate": (student_exam.total_violations or 0) >= max_violations,
                "debug": {
                    "yaw": details.get("yaw"),
                    "pitch": details.get("pitch"),
                    "roll": details.get("roll")
                }
            })

        except Exception as e:
            print(f"❌ Analysis error: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"status": "ERROR", "message": str(e)}), 500


    @app.route('/api/proctor/status/<int:student_exam_id>', methods=['GET'])
    @login_required
    def proctor_get_status(student_exam_id):
        """Get proctoring status"""
        try:
            student_exam = StudentExam.query.get_or_404(student_exam_id)
            if student_exam.student_id != current_user.id:
                # For faculty viewing, allow access
                if current_user.role not in ['faculty', 'admin']:
                    return jsonify({"error": "Unauthorized"}), 403

            print(f"🔍 Getting violations for student_exam_id: {student_exam_id}")
            
            violations = ExamViolation.query.filter_by(
                student_exam_id=student_exam_id
            ).order_by(ExamViolation.timestamp.desc()).all()  # Remove .limit(10) for now
            
            print(f"📊 Found {len(violations)} violations in database")
            
            for v in violations:
                print(f"  - {v.violation_type}: {v.message} at {v.timestamp}")

            return jsonify({
                "calibration_completed": getattr(student_exam, 'calibration_completed', False),
                "total_violations": getattr(student_exam, 'total_violations', 0) or 0,
                "proctoring_status": getattr(student_exam, 'proctoring_status', 'active'),
                "recent_violations": [{
                    "type": v.violation_type,
                    "message": v.message,
                    "timestamp": v.timestamp.isoformat()
                } for v in violations]
            })

        except Exception as e:
            print(f"❌ Error getting violations: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({"error": str(e)}), 500

    @app.route('/change-password', methods=['GET', 'POST'])
    @login_required
    def change_password():
        """Change password page - forced for first-time students, optional for faculty"""

        from datetime import datetime
        
        # Check if this is a forced change (student first login)
        is_forced = (current_user.role == 'student' and not getattr(current_user, 'password_changed', False))
        
        if request.method == 'POST':
            old_password = request.form.get('old_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Validation
            if not old_password or not new_password or not confirm_password:
                flash('❌ All fields are required!', 'error')
                return redirect(url_for('change_password'))
            
            # Check old password - FIXED: use password_hash instead of password
            if not check_password_hash(current_user.password_hash, old_password):
                flash('❌ Current password is incorrect!', 'error')
                return redirect(url_for('change_password'))
            
            # Check new passwords match
            if new_password != confirm_password:
                flash('❌ New passwords do not match!', 'error')
                return redirect(url_for('change_password'))
            
            # Check password length
            if len(new_password) < 6:
                flash('❌ New password must be at least 6 characters long!', 'error')
                return redirect(url_for('change_password'))
            
            # Check new password is different from old - FIXED: use password_hash
            if check_password_hash(current_user.password_hash, new_password):
                flash('❌ New password must be different from current password!', 'error')
                return redirect(url_for('change_password'))
            
            # Update password - FIXED: use password_hash
            try:
                current_user.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
                current_user.password_changed = True
                current_user.password_changed_at = datetime.utcnow()
                db.session.commit()
                
                flash('✅ Password changed successfully!', 'success')
                
                # Redirect based on role
                if current_user.role == 'student':
                    return redirect(url_for('student_dashboard'))
                elif current_user.role == 'faculty':
                    return redirect(url_for('faculty_dashboard'))
                else:
                    return redirect(url_for('admin_dashboard'))
                    
            except Exception as e:
                db.session.rollback()
                print(f"❌ Error changing password: {e}")
                import traceback
                traceback.print_exc()
                flash(f'❌ Error changing password: {str(e)}', 'error')
                return redirect(url_for('change_password'))
        
        return render_template('change_password.html', is_forced=is_forced)


    @app.route('/check-password-status')
    @login_required
    def check_password_status():
        """API endpoint to check if user needs to change password"""
        needs_change = (current_user.role == 'student' and not current_user.password_changed)
        
        return jsonify({
            'needs_change': needs_change,
            'role': current_user.role,
            'password_changed': current_user.password_changed
        })

    @app.route('/exam/<int:exam_id>/log_activity', methods=['POST'])
    def log_activity_fix(exam_id):
        return jsonify({"success": True})

        
    @app.route('/faculty/change-student-password/<int:student_id>', methods=['POST'])
    @login_required
    def faculty_change_student_password(student_id):
        """Faculty can reset a student's password"""
        from datetime import datetime
        
        # Authorization check
        if current_user.role not in ['faculty', 'admin']:
            return jsonify({"success": False, "message": "Unauthorized"}), 403
        
        try:
            # Get student
            student = User.query.get_or_404(student_id)
            
            # Verify it's a student
            if student.role != 'student':
                return jsonify({
                    "success": False,
                    "message": "Can only change passwords for students"
                }), 400
            
            # Get new password from form
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')
            
            # Validation
            if not new_password or not confirm_password:
                return jsonify({
                    "success": False,
                    "message": "Both password fields are required"
                }), 400
            
            if new_password != confirm_password:
                return jsonify({
                    "success": False,
                    "message": "Passwords do not match"
                }), 400
            
            if len(new_password) < 6:
                return jsonify({
                    "success": False,
                    "message": "Password must be at least 6 characters long"
                }), 400
            
            # Update password
            student.password_hash = generate_password_hash(new_password, method='pbkdf2:sha256')
            student.password_changed = False  # Force student to change on next login
            student.password_changed_at = None
            db.session.commit()
            
            # Log activity
            print(f"✅ Faculty {current_user.username} reset password for student {student.username}")
            
            return jsonify({
                "success": True,
                "message": f"Password reset successfully for {student.full_name or student.username}. Student will be required to change it on next login."
            })
            
        except Exception as e:
            db.session.rollback()
            print(f"❌ Error changing student password: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({
                "success": False,
                "message": f"Error: {str(e)}"
            }), 500


    print("✅ All enhanced routes registered!")