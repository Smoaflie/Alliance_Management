from app import app

from scripts.api.feishu import APIContainer
from scripts.utils import dict_2_obj

database = app.config.get("database")
redis_client = app.config.get('redis_client')
feishu_config = app.config.get("feishu")
# 飞书参数及api
FEISHU_CONFIG = dict_2_obj(feishu_config)
FEISHU_CONFIG.api = APIContainer(
    FEISHU_CONFIG.APP_ID,
    FEISHU_CONFIG.APP_SECRET,
    FEISHU_CONFIG.LARK_HOST,
)
