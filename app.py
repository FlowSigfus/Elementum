from flask import Flask, request
import secrets
import database as db
import os
from extensions import mail
from blueprints.auth import auth_bp
from blueprints.main import main_bp
from blueprints.story import story_bp
from blueprints.pvp import pvp_bp
from blueprints.daily import daily_bp
from blueprints.inventory import inventory_bp
from blueprints.profile import profile_bp
from blueprints.nfc import nfc_bp
from blueprints.friends import friends_bp
from blueprints.shop import shop_bp
from blueprints.trade import trade_bp
from datetime import timedelta
from flask_compress import Compress
from dotenv import load_dotenv

load_dotenv()  # загружаем переменные из .env

def create_app():
    app = Flask(__name__)
    app.secret_key = os.environ.get('SECRET_KEY', secrets.token_hex(16))
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)

    # Конфигурация почты из переменных окружения
    app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.yandex.ru')
    app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 465))
    app.config['MAIL_USE_SSL'] = os.environ.get('MAIL_USE_SSL', 'True').lower() == 'true'
    app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
    app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
    app.config['MAIL_DEFAULT_SENDER'] = os.environ.get('MAIL_DEFAULT_SENDER')

    mail.init_app(app)
    Compress(app)

    # Настройка загрузки аватаров
    UPLOAD_FOLDER = 'static/avatars'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}
    app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)

    # Регистрация blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(main_bp)
    app.register_blueprint(story_bp)
    app.register_blueprint(pvp_bp)
    app.register_blueprint(daily_bp)
    app.register_blueprint(inventory_bp)
    app.register_blueprint(profile_bp)
    app.register_blueprint(nfc_bp)
    app.register_blueprint(friends_bp)
    app.register_blueprint(shop_bp, url_prefix='/shop')
    app.register_blueprint(trade_bp)

    @app.after_request
    def add_header(response):
        if request.path.startswith('/static/'):
            response.cache_control.max_age = 86400
        return response

    db.init_db()
    return app

if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000,
            ssl_context=('192.168.1.123+1.pem', '192.168.1.123+1-key.pem'))