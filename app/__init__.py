from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
import os
import dotenv

dotenv.load_dotenv()

db = SQLAlchemy()


def create_app():

    app = Flask(
        __name__,
        template_folder="../templates",
        static_folder="../static"
    )

    app.secret_key = os.environ.get(
        "SECRET_KEY",
        "AI_BILLING_SECRET_2026"
    )

    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URI",
        "sqlite:///billing.db"
    )

    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False

    db.init_app(app)

    with app.app_context():

        from app import models

        db.create_all()

        from app.routes.auth import auth_bp
        from app.routes.products import products_bp
        from app.routes.billing import billing_bp
        from app.routes.customers import customers_bp
        from app.routes.history import history_bp
        from app.routes.subscription import subscription_bp
        from app.routes.shop_settings import shop_settings_bp
        from app.routes.suppliers import suppliers_bp
        from app.routes.purchases import purchases_bp
        from app.routes.stock import stock_bp
        from app.routes.reports import reports_bp

        app.register_blueprint(auth_bp)
        app.register_blueprint(products_bp)
        app.register_blueprint(billing_bp)
        app.register_blueprint(customers_bp)
        app.register_blueprint(history_bp)
        app.register_blueprint(subscription_bp)
        app.register_blueprint(shop_settings_bp)
        app.register_blueprint(suppliers_bp)
        app.register_blueprint(purchases_bp)
        app.register_blueprint(stock_bp)
        app.register_blueprint(reports_bp)

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template("errors/404.html"), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template("errors/500.html"), 500

    @app.errorhandler(403)
    def forbidden_error(error):
        return render_template("errors/403.html"), 403

    return app