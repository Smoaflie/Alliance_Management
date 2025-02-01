import logging
import os

from app import app, init_app
from scripts.utils import get_project_root
# 获取项目的根目录
project_root = get_project_root()

# 创建日志文件夹
logs_dir = os.path.join(project_root, '.logs')
os.makedirs(logs_dir, exist_ok=True)

# 配置日志文件路径
log_file_path = os.path.join(logs_dir, 'app.log')

# 配置日志记录器
logging.basicConfig(
    level=logging.INFO,  # 设置最低日志级别
    format='%(asctime)s [%(levelname)s] %(message)s',  # 日志格式
    handlers=[
        logging.FileHandler(log_file_path, encoding='utf-8'),  # 文件输出（保存到 .logs 文件中）
        logging.StreamHandler()  # 控制台输出
    ]
)



if __name__ == "__main__":
    init_app(app)
    from flask import url_for
    with app.app_context():
        print(app.url_map)
        # print(url_for('feishu.feishu_web.get_home'))
    app.run(debug=True)
    
