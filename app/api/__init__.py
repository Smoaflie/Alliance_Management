from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

def init_api():
    from .items import items_bp
    api_bp.register_blueprint(items_bp)