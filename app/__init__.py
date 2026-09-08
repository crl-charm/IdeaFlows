from flask import Flask, request, g, render_template, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from app.utils.auth import register_admin_blueprint, enforce_admin_access, is_admin_path
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_cors import CORS
import logging
import os

# Create database object
db = SQLAlchemy()
_sqlalchemy_db = db
socketio = SocketIO(cors_allowed_origins="*")  # Will be overridden by CORS
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address)


def create_app():

    import sys
    import os

    # Set up static folder - Flask should serve from root-level static directory
    static_folder = os.path.join(os.path.dirname(__file__), '..', 'static')
    app = Flask(__name__, static_folder=static_folder, static_url_path='/static')

    # Import config from organized config module
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from config import Config
    app.config.from_object(Config)

    # Initialize extensions
    db.init_app(app)
    socketio.init_app(app)

    # Trust single-hop Nginx reverse proxy for accurate client IP & scheme (outermost WSGI wrapper)
    from werkzeug.middleware.proxy_fix import ProxyFix
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    
    # CSRF exemptions (documented):
    # - POST /api/login (auth_routes @csrf.exempt)
    # - /admin/menu/api/* (multipart menu uploads; see custom_protect below)
    original_protect = csrf.protect

    def custom_protect(*args, **kwargs):
        if request.path.startswith("/admin/menu/api/"):
            return None
        return original_protect(*args, **kwargs)

    csrf.protect = custom_protect
    csrf.init_app(app)
    limiter.init_app(app)

    # Configure CORS restrictively
    CORS(app, origins=app.config['CORS_ORIGINS'], supports_credentials=True)

    # Enable response compression (Gzip) for faster HTML, JS, CSS, and API responses
    try:
        from flask_compress import Compress
        Compress(app)
    except ImportError:
        pass

    # Configure logging
    configure_logging(app)

    # Register security middleware
    register_security_middleware(app)

    # Register bot defense, honeypot traps, and scraper countermeasures
    from app.core.bot_defense import register_bot_defense
    register_bot_defense(app)

    # -------------------------------------------------------------------------
    # ROUTE & CONTROLLER BLUEPRINT REGISTRATIONS (Modularized by Domain)
    # -------------------------------------------------------------------------
    
    # 1. Authentication & User Management Module
    from app.routes.auth_routes import bp as auth_bp
    from app.routes.user_routes import user_bp
    from app.routes.admin_routes import admin_bp
    from app.controllers.management_controller import ManagementController

    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp)
    register_admin_blueprint(app, admin_bp)

    # 2. POS Operations & Space Management Module
    from app.routes.dashboard_routes import bp as dashboard_bp
    from app.routes.session_routes import session_bp
    from app.routes.order_routes import order_bp
    from app.routes.lounge_routes import lounge_bp
    from app.routes.boardroom_routes import boardroom_bp
    from app.routes.receipts import receipts_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(session_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(lounge_bp)
    app.register_blueprint(boardroom_bp)
    app.register_blueprint(receipts_bp)

    # 3. Catalog & Inventory Module (Admin & Staff)
    from app.routes.menu import menu_bp
    from app.routes.inventory import inventory_bp
    from app.routes.staff_menu import staff_menu_bp
    from app.routes.staff_inventory import staff_inventory_bp

    register_admin_blueprint(app, menu_bp)
    register_admin_blueprint(app, inventory_bp)
    app.register_blueprint(staff_menu_bp)
    app.register_blueprint(staff_inventory_bp)

    # 4. Financial, Accounting & Analytics Module
    from app.routes.sales_routes import sales_bp
    from app.routes.sales_balance import sales_bp as sales_balance_bp
    from app.routes.expenses import expenses_bp
    from app.routes.staff_expenses import staff_expenses_bp
    from app.routes.receivables import receivables_bp
    from app.routes.payables import payables_bp
    from app.routes.staff_receivables import staff_receivables_bp
    from app.routes.staff_performance import staff_performance_bp
    from app.routes.analytics import analytics_bp
    from app.controllers.analytics_controller import AnalyticsController
    from app.controllers.finance_controller import FinanceController

    register_admin_blueprint(app, sales_bp)
    register_admin_blueprint(app, sales_balance_bp)
    register_admin_blueprint(app, expenses_bp)
    app.register_blueprint(staff_expenses_bp)
    register_admin_blueprint(app, receivables_bp)
    app.register_blueprint(staff_receivables_bp)
    register_admin_blueprint(app, payables_bp)
    register_admin_blueprint(app, staff_performance_bp)
    register_admin_blueprint(app, analytics_bp)

    # Register OOP Controllers
    controllers = [
        AnalyticsController(db),
        FinanceController(db),
        ManagementController(db),
    ]
    for controller in controllers:
        controller.register(app)

    # Import Socket.IO handlers to register event handlers
    from app.core import socketio_handlers

    @app.route("/robots.txt")
    def robots_txt():
        return send_from_directory(static_folder, "robots.txt", mimetype="text/plain")

    @app.route("/")
    def home():
        return render_template("landing.html")

    return app


def configure_logging(app):
    """Configure comprehensive logging for security and debugging"""
    handlers = [logging.StreamHandler()]
    try:
        log_dir = os.environ.get('UPLOAD_FOLDER', os.path.dirname(__file__))
        handlers.append(logging.FileHandler(os.path.join(log_dir, 'app.log')))
    except Exception:
        pass

    if not app.debug:
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            handlers=handlers
        )

        security_logger = logging.getLogger('security')
        security_logger.setLevel(logging.INFO)
        try:
            log_dir = os.environ.get('UPLOAD_FOLDER', os.path.dirname(__file__))
            security_handler = logging.FileHandler(os.path.join(log_dir, 'security.log'))
            security_handler.setFormatter(logging.Formatter(
                '%(asctime)s - SECURITY - %(levelname)s - %(message)s'
            ))
            security_logger.addHandler(security_handler)
        except Exception:
            security_logger.addHandler(logging.StreamHandler())
    else:
        logging.basicConfig(
            level=logging.DEBUG,
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )


def register_security_middleware(app):
    """Register security middleware and error handlers"""

    @app.before_request
    def enforce_admin_path_access():
        """Defense-in-depth RBAC for admin URLs."""
        path = request.path or ""
        if path in ("/", "/login", "/logout", "/register"):
            return None
        if path.startswith("/static/"):
            return None
        if not is_admin_path(path):
            return None
        denied = enforce_admin_access()
        if denied is not None:
            return denied

    @app.before_request
    def security_headers():
        """Add security headers to all responses"""
        for header, value in app.config.get('SECURITY_HEADERS', {}).items():
            g.security_headers = getattr(g, 'security_headers', {})
            g.security_headers[header] = value

    @app.after_request
    def apply_security_headers(response):
        """Apply security headers and static asset cache controls to response"""
        security_headers = getattr(g, 'security_headers', {})
        for header, value in security_headers.items():
            response.headers[header] = value

        # Aggressive browser caching for static files and uploaded images
        if request.path.startswith('/static/'):
            response.headers['Cache-Control'] = 'public, max-age=31536000, immutable'

        return response

    @app.errorhandler(404)
    def not_found_error(error):
        """Handle 404 errors securely"""
        if request.path.startswith('/api/'):
            return {'error': 'Resource not found'}, 404
        return render_template('404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        """Handle 500 errors without leaking information"""
        db.session.rollback()
        if request.path.startswith('/api/'):
            return {'error': 'Internal server error'}, 500
        return render_template('500.html'), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        """Handle 403 errors"""
        if request.path.startswith('/api/'):
            return {'error': 'Forbidden'}, 403
        return render_template('403.html'), 403

        