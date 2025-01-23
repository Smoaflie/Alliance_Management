def register_blueprints(app):
    from app.feishu import feishu_bp
    from app.feishu.events import events_bp
    from app.feishu.mini_program import mini_program_bp
    feishu_bp.register_blueprint(events_bp)
    feishu_bp.register_blueprint(mini_program_bp)

    app.register_blueprint(feishu_bp)