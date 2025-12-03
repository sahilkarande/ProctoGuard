"""
Secure Proctored Exam Platform
Main Application File - Enhanced Version with Socket.IO Binary Proctoring
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session
from flask_login import login_required, current_user, logout_user
import os
from dotenv import load_dotenv
from sqlalchemy import text
from backend.database import db, login_manager
import traceback
from datetime import timedelta
from models import User, Exam, Question, StudentExam, StudentAnswer, ActivityLog

# Load environment variables
load_dotenv()

def create_app():
    """Application factory"""
    app = Flask(
        __name__,
        template_folder='frontend/templates',
        static_folder='frontend/static'
    )
    
    # Configuration
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'sqlite:///exam_platform.db')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.config['MAX_CONTENT_LENGTH'] = int(os.getenv('MAX_CONTENT_LENGTH', 16 * 1024 * 1024))
    
    # Session configuration
    app.config['SESSION_COOKIE_SECURE'] = False  # Set True in production with HTTPS
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = 3600  # 1 hour
    app.config['SESSION_REFRESH_EACH_REQUEST'] = True

    # ==============================================================
    # INITIALIZE EXTENSIONS
    # ==============================================================
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'login'
    login_manager.login_message = 'Please log in to access this page.'
    login_manager.login_message_category = 'info'
    login_manager.session_protection = 'strong'

    # ==============================================================
    # INITIALIZE SOCKET.IO ⚠️ CRITICAL FOR BINARY PROCTORING
    # ==============================================================
    from backend.routes import socketio
    socketio.init_app(app)
    print("✅ Socket.IO initialized for binary proctoring")

    # ==============================================================
    # CACHE CONTROL (SMART BACK BUTTON FIX)
    # ==============================================================
    @app.after_request
    def add_cache_control(response):
        """Strict cache control: prevent showing old dashboards after logout"""
        endpoint = request.endpoint or ""

        # Never cache authentication or dashboard routes
        if endpoint in [
            'login', 'logout', 'register', 'verify_otp',
            'student_dashboard', 'faculty_dashboard', 'admin_dashboard'
        ]:
            response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response

        # Public pages
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        return response

    # ==============================================================
    # LOGIN MANAGER HELPERS
    # ==============================================================
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        flash('Please log in to access this page.', 'warning')
        return redirect(url_for('login'))

    # ==============================================================
    # ROUTE REGISTRATION
    # ==============================================================
    with app.app_context():
        from backend.routes import register_routes
        register_routes(app)
        db.create_all()
        print("✅ Database initialized!")

    # ==============================================================
    # ADMIN SQL CONSOLE (For Admin Only)
    # ==============================================================
    def is_admin_user():
        """Check if current user is admin"""
        return getattr(current_user, "role", None) == "admin"

    @app.route("/admin/sql_console", methods=["GET"])
    @login_required
    def admin_sql_console():
        if not is_admin_user():
            return "Access Denied", 403
        return render_template("admin_sql_console.html")

    @app.route("/admin/sql_console/run", methods=["POST"])
    @login_required
    def admin_sql_run():
        if not is_admin_user():
            return jsonify({"success": False, "error": "Access denied"}), 403

        payload = request.get_json() or {}
        sql = (payload.get("sql") or "").strip()
        if not sql:
            return jsonify({"success": False, "error": "Empty SQL query"}), 400

        try:
            engine = db.engine
            first_word = sql.split(None, 1)[0].lower()

            # SELECT / DQL
            if first_word in ("select", "with", "pragma"):
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

            # DML / DDL
            else:
                with engine.begin() as conn:
                    result = conn.execute(text(sql))
                    affected = result.rowcount if result.rowcount is not None else 0
                return jsonify({
                    "success": True,
                    "type": "update",
                    "message": f"Statement executed successfully. Rows affected: {affected}"
                })

        except Exception as e:
            traceback.print_exc()
            return jsonify({"success": False, "error": str(e)}), 500

    # ==============================================================
    # ROUTE LIST DEBUG INFO
    # ==============================================================
    print("\n" + "=" * 70)
    print("📋 REGISTERED ROUTES")
    print("=" * 70)
    for rule in app.url_map.iter_rules():
        if rule.endpoint != 'static':
            methods = ','.join(sorted(rule.methods - {'HEAD', 'OPTIONS'}))
            print(f"{rule.endpoint:40s} {methods:10s} {rule.rule}")
    print("=" * 70 + "\n")

    return app


# ==============================================================
# MAIN ENTRY POINT
# ==============================================================
if __name__ == '__main__':
    app = create_app()

    print("\n" + "=" * 70)
    print("🎯 PROCTORED EXAM PLATFORM - PRODUCTION READY")
    print("=" * 70)
    print("🌐 Server URL: http://localhost:5000")
    print("🌐 Network URL: http://0.0.0.0:5000")
    print("\n💡 Enhanced Features:")
    print("   ✓ PRN Validation (12-digit)")
    print("   ✓ Roll ID & Employee ID Support")
    print("   ✓ OTP Email Verification")
    print("   ✓ Smart Session Management")
    print("   ✓ Back Button Fix (no reload to login)")
    print("   ✓ PDF Result Download")
    print("   ✓ Student Analytics Dashboard")
    print("   ✓ Real-time Binary Proctoring (Socket.IO)")  # ← UPDATED
    print("   ✓ Fast Face Calibration (<0.5s)")           # ← NEW
    print("   ✓ Violation Detection & Auto-Submit")       # ← NEW
    print("   ✓ Admin SQL Console")
    print("   ✓ Bulk Import/Export (CSV/Excel)")
    print("   ✓ Secure Cache Control")
    print("\n📚 Documentation: IMPLEMENTATION_GUIDE.md")
    print("🆘 Help: START_HERE.txt")
    print("=" * 70 + "\n")

    # ==============================================================
    # ⚠️ CRITICAL: USE SOCKETIO.RUN() NOT APP.RUN()
    # ==============================================================
    from backend.routes import socketio
    
    socketio.run(
        app,
        debug=os.getenv('FLASK_DEBUG', 'True') == 'True',
        host='0.0.0.0',
        port=8900,
        ssl_context=('cert.pem', 'key.pem'),
        allow_unsafe_werkzeug=True
    )
