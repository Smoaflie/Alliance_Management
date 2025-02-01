from app.ext.database import Database
from app.ext.redis import redis
from scripts.api.feishu import APIContainer

database : Database 
redis_client : redis 

# 由于FEISHU_CONFIG是由setting.json内容生成的
# 参数不固定，因此该存根文件仅用于让ide正确识别api类型
class _FeishuConfig:
    api: APIContainer

FEISHU_CONFIG: _FeishuConfig