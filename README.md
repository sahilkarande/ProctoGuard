# ProctoGuard - Advanced AI-Powered Proctored Exam Platform

A comprehensive, enterprise-grade Python-based web application for conducting secure, proctored online examinations with cutting-edge AI vision proctoring, automated question enhancement, and advanced analytics. Built with Flask, OpenVINO, and modern web technologies for maximum security and reliability.

## Features

### Advanced AI Vision Proctoring

- **Real-time Face Detection**: Uses OpenVINO and OpenCV for high-performance face detection
- **Head Pose Estimation**: Monitors head orientation and detects unusual movements
- **Calibration System**: Learns student's baseline head position for personalized monitoring
- **Multi-face Detection**: Automatically flags multiple faces in frame
- **Fatigue-friendly Design**: Allows natural movements while detecting deliberate cheating
- **Adaptive Thresholds**: Soft and hard deviation thresholds with cooldown periods

### For Faculty Members

- **Intuitive Exam Creation**: User-friendly interface for exam setup and management
- **Bulk Data Import**: Support for CSV, Excel, and JSON file formats
- **AI Question Enhancement**: Claude AI integration for automatic question improvement
- **Advanced Analytics Dashboard**:
  - Real-time pass/fail statistics
  - Detailed question performance analysis
  - Student-wise performance metrics
  - Comprehensive proctoring reports
  - Batch-wise result aggregation
- **Professional PDF Reports**: Automated generation of detailed result reports
- **Email Notifications**: Automated result notifications to students
- **Admin SQL Console**: Direct database access for advanced users
- **Role-based Access Control**: Separate dashboards for faculty and admin users

### For Students

- **Modern UI/UX**: Clean, responsive interface inspired by Google Forms
- **Real-time Countdown Timer**: Visual timer with automatic submission
- **Auto-save Functionality**: Answers saved automatically every few seconds
- **Instant Result Access**: Immediate score and detailed breakdown after submission
- **Performance Analytics**: Visual representation of correct/incorrect answers
- **Secure Exam Environment**: Multiple layers of anti-cheating protection

### Enterprise-Grade Security Features

- **Multi-layered Proctoring**:
  - Browser tab switch detection with violation counting
  - Copy/paste prevention with clipboard monitoring
  - Right-click and context menu blocking
  - Developer tools detection (F12, Ctrl+Shift+I, etc.)
  - Keyboard shortcut blocking
- **AI Vision Monitoring**: Real-time analysis of student behavior
- **Activity Logging**: Timestamped logging of all suspicious activities
- **Automatic Flagging System**: Intelligent detection of cheating attempts
- **Session Security**: Secure session management with proper timeouts
- **Data Encryption**: Secure password hashing and data protection

### Advanced Analytics & Reporting

- **Comprehensive Statistics**:
  - Pass/fail rates with visual charts
  - Average scores and performance trends
  - Question difficulty analysis
  - Time-based performance metrics
- **Detailed Student Reports**:
  - Individual performance breakdowns
  - Proctoring violation summaries
  - Time spent per question
  - Comparative analytics
- **Batch Processing**: Multi-student result aggregation and reporting
- **Export Capabilities**: PDF reports with professional formatting
- **Real-time Monitoring**: Live dashboard for ongoing exams

### AI-Powered Features

- **Question Enhancement**: Claude AI improves grammar, clarity, and formatting
- **Vision-based Proctoring**: OpenVINO-powered real-time monitoring
- **Automated Grading**: Intelligent scoring with partial credit options
- **Smart Flagging**: AI-driven detection of suspicious behavior patterns

### Communication Features

- **OTP Email Verification**: Secure registration with email verification
- **Result Notifications**: Automated email delivery of exam results
- **SMTP Integration**: Configurable email server support
- **Fallback Console Display**: Development-friendly OTP display

### Technical Features

- **Scalable Architecture**: Modular design with Blueprint organization
- **Database Flexibility**: SQLite for development, PostgreSQL/MySQL ready
- **RESTful API Design**: Clean API endpoints for future integrations
- **File Upload Handling**: Secure handling of bulk data imports
- **Error Handling**: Comprehensive error management and logging
- **Performance Optimization**: Efficient database queries and caching

## Quick Start

### Prerequisites

- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Install Dependencies**

```bash
pip install -r requirements.txt
```

2. **Configure Environment Variables**

```bash
# Copy the example file
cp .env.example .env

# Edit .env and set your values (see .env.example for all options)
# At minimum, set SECRET_KEY for Flask sessions
```

3. **Initialize Database**

```bash
python app.py
```

This will create the SQLite database and start the development server.

4. **Access the Application**
   Open your browser and navigate to:

```
http://localhost:5000
```

## Usage Guide

### For Faculty

1. **Register an Account**

   - Go to the registration page
   - Select "Faculty" as your role
   - Complete registration

2. **Create an Exam**

   - Click "Create New Exam" from your dashboard
   - Fill in exam details:
     - Title
     - Description
     - Duration (in minutes)
     - Passing score (percentage)

3. **Upload Questions**
   - After creating an exam, you'll be directed to upload questions
   - Prepare a CSV or Excel file with the following columns:
     - `question`: The question text
     - `option_a`: First option
     - `option_b`: Second option
     - `option_c`: Third option (optional)
     - `option_d`: Fourth option (optional)
     - `correct_answer`: Correct option (A, B, C, or D)
     - `points`: Points for the question (optional, default: 1.0)
4. **AI Enhancement (Optional)**

   - Check the "Enhance questions with AI" option when uploading
   - Requires valid ANTHROPIC_API_KEY in .env file
   - AI will improve grammar, clarity, and formatting

5. **View Analytics**
   - Access detailed analytics from the exam view
   - See pass/fail rates, average scores, and question performance
   - Review flagged attempts for suspicious activity

### For Students

1. **Register an Account**

   - Go to the registration page
   - Select "Student" as your role
   - Complete registration

2. **Take an Exam**

   - View available exams on your dashboard
   - Click "Start Exam" to begin
   - Read the security warnings carefully

3. **During the Exam**

   - Answer questions by selecting radio buttons
   - Answers are automatically saved
   - Watch the countdown timer
   - Avoid:
     - Switching tabs or windows
     - Copying or pasting
     - Right-clicking
     - Opening developer tools

4. **Submit and View Results**
   - Click "Submit Exam" when finished
   - View your score and detailed breakdown immediately
   - See which questions were answered correctly/incorrectly

## 📊 Sample Questions File

A sample questions file (`sample_questions.csv`) is included. Format:

```csv
question,option_a,option_b,option_c,option_d,correct_answer,points
What is 2+2?,3,4,5,6,B,1.0
Capital of France?,London,Paris,Berlin,Rome,B,1.0
```

## 🔧 Configuration

### Environment Variables

The application uses the following environment variables (see `.env.example` for complete list):

**Required Settings:**

- `SECRET_KEY`: Flask secret key for session management (change in production)
- `DATABASE_URL`: Database connection string (defaults to SQLite)

**Optional AI Features:**

- `ANTHROPIC_API_KEY`: API key for Claude AI question enhancement
- `OPENVINO_DEVICE`: Device for OpenVINO inference (CPU/GPU, defaults to CPU)

**Email Configuration:**

- `SMTP_SERVER`: SMTP server for email notifications
- `SMTP_PORT`: SMTP port (587 for TLS)
- `SMTP_USERNAME`: SMTP username
- `SMTP_PASSWORD`: SMTP password/app password
- `FROM_EMAIL`: Sender email address

**Application Settings:**

- `FLASK_DEBUG`: Enable/disable debug mode (default: True in development)
- `MAX_CONTENT_LENGTH`: Maximum file upload size in bytes (default: 16MB)
- `SESSION_TIMEOUT_MINUTES`: Session timeout duration
- `EXAM_TIME_BUFFER_MINUTES`: Extra time buffer for exams

### Security Settings (Database Configurable)

Each exam has configurable security settings stored in the database:

- `allow_tab_switch`: Allow/disallow tab switching during exam
- `max_tab_switches`: Maximum allowed tab switches before flagging
- `randomize_questions`: Randomize question order for each student
- `show_results_immediately`: Show results immediately after submission
- `enable_proctoring`: Enable/disable AI vision proctoring
- `strict_mode`: Enable strict proctoring rules

### AI Vision Proctoring Configuration

Vision proctoring thresholds can be configured in `backend/services/proctor_vision/openvino_vision.py`:

- `SOFT_DEVIATION_THRESHOLD`: Soft threshold for head pose deviation
- `HARD_DEVIATION_THRESHOLD`: Hard threshold for head pose deviation
- `COOLDOWN_PERIOD`: Cooldown period between violations
- `CALIBRATION_FRAMES`: Number of frames for initial calibration

##  Project Structure

```
ProctoGuard/
│
├── app.py                          # Main Flask application entry point
├── models.py                       # SQLAlchemy database models and schemas
├── requirements.txt                # Python dependencies and versions
├── .env.example                    # Environment variables template
├── .gitignore                      # Git ignore patterns
├── README.md                       # Project documentation
│
├── backend/                        # Backend application logic
│   ├── __init__.py
│   ├── routes.py                   # Flask routes and API endpoints
│   ├── database.py                 # Database connection and utilities
│   ├── services/                   # Business logic services
│   │   └── proctor_vision/         # AI vision proctoring services
│   │       └── openvino_vision.py  # OpenVINO face detection and head pose estimation
│   └── utils/                      # Utility functions and helpers
│       ├── __init__.py
│       ├── create_db.py            # Database initialization script
│       ├── email_utils.py          # Email sending utilities
│       └── view_users.py           # User management utilities
│
├── frontend/                       # Frontend templates and static files
│   ├── templates/                  # Jinja2 HTML templates
│   │   ├── base.html               # Base template with common layout
│   │   ├── index.html              # Landing page
│   │   ├── login.html              # User login page
│   │   ├── register.html           # User registration page
│   │   ├── otp_verification.html   # OTP verification page
│   │   ├── reset_password.html     # Password reset page
│   │   ├── faculty/                # Faculty-specific templates
│   │   │   ├── dashboard.html      # Faculty dashboard
│   │   │   ├── create_exam.html    # Exam creation form
│   │   │   ├── upload_questions.html # Question upload interface
│   │   │   ├── view_exam.html      # Exam details and management
│   │   │   ├── analytics.html      # Analytics and reporting dashboard
│   │   │   ├── manage_students.html # Student management interface
│   │   │   ├── import_students.html # Bulk student import
│   │   │   ├── edit_student.html   # Individual student editing
│   │   │   └── student_report.html # Individual student reports
│   │   └── student/                # Student-specific templates
│   │       ├── dashboard.html      # Student dashboard
│   │       ├── take_exam.html      # Exam taking interface
│   │       └── result.html         # Exam results display
│   └── static/                     # Static assets (CSS, JS, images)
│       ├── css/
│       │   └── style.css           # Main stylesheet
│       └── js/
│           ├── exam_proctoring.js  # Client-side proctoring logic
│           ├── exam_timer.js       # Countdown timer functionality
│           └── security.js         # Security measures (copy-paste prevention, etc.)
│
├── core/                           # Core application components
│   └── __init__.py                 # Core module initialization
│
├── operations/                     # Operational scripts and utilities
│   └── __init__.py                 # Operations module initialization
│
├── Files/                          # File storage and uploads
│   └── student_data_aug_2025.json  # Sample student data
│
├── instance/                       # Instance-specific files (database, etc.)
│   └── exam_platform.db            # SQLite database (created at runtime)
│
├── venv/                           # Python virtual environment (optional)
│
├── .vscode/                        # VS Code configuration
│   └── settings.json               # IDE settings
│
└── __pycache__/                    # Python bytecode cache (auto-generated)
```

### 📂 **Directory Explanations**

#### **🔧 Backend Architecture**

- **`backend/`**: Contains all server-side logic organized into modular components
- **`backend/routes.py`**: RESTful API endpoints for user management, exams, and analytics
- **`backend/services/`**: Business logic layer with AI vision proctoring services
- **`backend/utils/`**: Helper functions for database operations, email sending, and user management

#### **🎨 Frontend Structure**

- **`frontend/templates/`**: Jinja2 templates organized by user roles (faculty/student)
- **`frontend/static/`**: Client-side assets with security-focused JavaScript
- **Template Organization**: Separate directories for faculty and student interfaces

#### **📊 Data & Configuration**

- **`models.py`**: SQLAlchemy ORM models defining database schema
- **`instance/`**: Runtime-generated files like SQLite database
- **`Files/`**: Sample data and upload storage directory

#### **🛠️ Development & Operations**

- **`operations/`**: Scripts for maintenance and operational tasks
- **`core/`**: Shared core functionality and configurations
- **`.env.example`**: Template for environment variables with all configuration options

### 🗂️ **Key Files Overview**

| File                                                 | Purpose                 | Key Features                                      |
| ---------------------------------------------------- | ----------------------- | ------------------------------------------------- |
| `app.py`                                             | Application entry point | Flask app initialization, blueprint registration  |
| `models.py`                                          | Database schema         | User, Exam, Question, Answer, ActivityLog models  |
| `backend/routes.py`                                  | API endpoints           | CRUD operations, authentication, exam management  |
| `backend/services/proctor_vision/openvino_vision.py` | AI proctoring           | Face detection, head pose estimation, calibration |
| `frontend/templates/base.html`                       | UI foundation           | Responsive layout, navigation, security scripts   |
| `requirements.txt`                                   | Dependencies            | Flask, OpenVINO, OpenCV, SQLAlchemy, etc.         |

## 🗄️ Database Schema

The application uses SQLite with the following models:

- **User**: Faculty and student accounts
- **Exam**: Exam information
- **Question**: Individual questions
- **StudentExam**: Student exam attempts
- **Answer**: Student answers
- **ActivityLog**: Proctoring activity logs

## 🔐 Security Features Explained

### 1. Tab Switch Detection

- Monitors visibility changes in the browser
- Alerts student when they switch tabs
- Counts violations and logs them
- Flags attempts exceeding threshold

### 2. Copy/Paste Prevention

- Blocks clipboard operations during exam
- Prevents students from copying questions
- Prevents pasting answers from external sources

### 3. Right-Click Disabled

- Prevents access to context menu
- Blocks "View Source" and similar options

### 4. Developer Tools Detection

- Detects keyboard shortcuts for dev tools
- Blocks F12, Ctrl+Shift+I, Ctrl+Shift+J
- Logs attempts as high-severity violations

### 5. Activity Logging

- Every suspicious action is logged with timestamp
- Categorized by severity (low, medium, high)
- Available for faculty review in analytics

## 📈 Analytics & Reporting

Faculty can access comprehensive analytics including:

1. **Overall Statistics**

   - Total attempts
   - Pass/fail counts
   - Average score
   - Flagged attempts

2. **Question Performance**

   - How many students answered each question
   - Accuracy percentage per question
   - Visual progress bars

3. **Student Results**

   - Individual scores and percentages
   - Time taken per student
   - Tab switch counts
   - Submission timestamps

4. **Flagged Attempts**
   - Students who exceeded security thresholds
   - Detailed suspicious activity counts
   - Sortable and filterable

## 🤖 AI Enhancement

The AI enhancement feature uses Anthropic's Claude to:

- Fix grammar and spelling errors
- Improve question clarity
- Standardize option formatting
- Maintain technical accuracy
- Ensure professional tone

**Requirements:**

- Valid Anthropic API key
- Internet connection during upload
- Compatible question format

## 🛠️ Troubleshooting

### Database Issues

```bash
# Delete and recreate database
rm exam_platform.db
python app.py
```

### Import Errors

```bash
# Reinstall dependencies
pip install --upgrade -r requirements.txt
```

### AI Enhancement Not Working

- Check that ANTHROPIC_API_KEY is set in .env
- Verify API key is valid
- Check internet connection
- Review console logs for errors

## 🚀 Production Deployment

For production use:

1. **Change SECRET_KEY** to a strong random value
2. **Use production WSGI server** (Gunicorn, uWSGI)
3. **Use production database** (PostgreSQL, MySQL)
4. **Enable HTTPS**
5. **Set debug=False** in app.py
6. **Configure proper logging**
7. **Implement rate limiting**
8. **Add user email verification**
9. **Implement password reset**
10. **Add CSRF protection** (already included in Flask-WTF)

## 📝 Future Enhancements

Potential additions to further enhance the platform:

### 🔄 Already Implemented Features

- [x] **AI Vision Proctoring**: Real-time face detection and head pose monitoring
- [x] **PDF Report Generation**: Professional result reports with detailed analytics
- [x] **Email Notifications**: OTP verification and result notifications
- [x] **Multiple File Formats**: CSV, Excel, and JSON support for bulk uploads
- [x] **Advanced Analytics**: Comprehensive performance dashboards

### 🚀 Planned Enhancements

- [ ] **Live Webcam Proctoring**: Real-time video streaming with cloud processing
- [ ] **Screen Recording**: Capture and analyze screen activity during exams
- [ ] **Additional File Formats**: Word documents and PDF question imports
- [ ] **Advanced Export Options**: Excel reports, CSV downloads, data visualization
- [ ] **Scheduled Exams**: Calendar-based exam scheduling with notifications
- [ ] **Question Bank Management**: Reusable question pools with tagging system
- [ ] **Peer Review System**: Collaborative grading and review workflows
- [ ] **Mobile Application**: Native iOS/Android apps for exam taking
- [ ] **LMS Integration**: Moodle, Canvas, Blackboard API integrations
- [ ] **Advanced Proctoring**: Screen sharing detection, multiple camera support
- [ ] **Biometric Authentication**: Fingerprint/face recognition for login
- [ ] **Real-time Collaboration**: Live faculty monitoring and intervention
- [ ] **Advanced AI Features**: Question difficulty prediction, adaptive testing
- [ ] **Multi-language Support**: Internationalization and localization
- [ ] **Offline Mode**: Limited functionality without internet connection

## 🤝 Contributing

This is a starter project. Feel free to:

- Add new features
- Improve security measures
- Enhance UI/UX
- Optimize performance
- Add tests
- Improve documentation

## License

This project is provided as-is for educational purposes.

## 🙏 Acknowledgments

- Built with Flask web framework
- AI enhancement powered by Anthropic Claude
- UI inspired by Google Forms
- Icons from emoji set

## 📧 Support

For issues or questions:

1. Check the troubleshooting section
2. Review error logs in the console
3. Verify your environment configuration

---

**Happy Examining! 🎉**
