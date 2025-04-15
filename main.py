import logging
import os
import colorlog
from logging.handlers import TimedRotatingFileHandler

from app import app, init_app
from scripts.utils import get_project_root

# 配置日志目录
logs_dir = os.path.join(get_project_root(), ".logs")
os.makedirs(logs_dir, exist_ok=True)

# 文件日志处理器：按日期切分日志文件
file_handler = TimedRotatingFileHandler(
    os.path.join(logs_dir, "app.log"),  # 日志文件路径
    when="midnight",                    # 切分周期设置为午夜（每天00:00）
    interval=1,                         # 每1天切分一次（即每天0点切分）
    backupCount=7,                      # 保留最近7天的日志文件
    encoding="utf-8"                    # 文件编码格式为 utf-8
)

# 格式化日期后缀为 "YYYY-MM-DD.log"
file_handler.suffix = "%Y-%m-%d.log"  # 日志文件名的日期部分，例如：app-2025-02-27.log

# 控制台日志处理器：使用 colorlog 为不同级别添加颜色
console_handler = colorlog.StreamHandler()
console_handler.setFormatter(colorlog.ColoredFormatter(
    "%(log_color)s%(asctime)s %(name)s [%(levelname)s] %(message)s",
    log_colors={
        "DEBUG": "blue",
        "INFO": "green",
        "WARNING": "yellow",
        "ERROR": "red",
        "CRITICAL": "magenta",
    }
))

logging.basicConfig(
    level=logging.INFO,  # 设置最低日志级别
    format="%(asctime)s %(name)s [%(levelname)s] %(message)s",  # 日志格式
    handlers=[
        file_handler,  # 文件输出
        console_handler,  # 控制台输出
    ],
)

if __name__ == "__main__":
    logger = logging.getLogger(__name__)
    logger.info("正在启动服务端...")

    init_app(app)
    from flask import url_for
    with app.app_context():
        logging.info("服务端启动成功 - url_map:\n" + str(app.url_map))
    app.run(debug=True, port=3000)
