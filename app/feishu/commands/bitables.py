import os
import subprocess
import ujson
from flask import jsonify
from app.feishu.config import FEISHU_CONFIG as _fs
from scripts.utils import get_project_root

def gcode_optimize_event_handler(logger, event):
    try:
        original_file_field_id = _fs.bitables.gcode_optimize.original_file_field_id
        file_origin = next(i.field_value for i in event.action_list[0].after_value if i.field_id == original_file_field_id)

        if not file_origin:
            logger.error('Unexpect record was added in "gcode_optimize" table.(empty file_original)')
            return 'Error: Unexpect record was added in "gcode_optimize" table.(empty file_original)'
        file = ujson.loads(file_origin)

        file_name = file[0].get('name')
        os.path.splitext(file_name)
        file_name_without_extfile_token = os.path.splitext(file_name)[0]   
        file_ext = os.path.splitext(file_name)[1]
        if not file_ext == '.gcode':
            logger.error('Unexpect record was added in "gcode_optimize" table.(file_ext is not .gcode)')
            return 'Error: Unexpect record was added in "gcode_optimize" table.(file_ext is not .gcode)'
        
        file_token = file[0].get('id')
        record_id = event.action_list[0].record_id
        resp = _fs.api.cloud.download_medias(file_token)
        if resp.status_code == 200:
            cache_dir = os.path.join(get_project_root(), 'cache')
            file_path = os.path.join(cache_dir, file_name)
            script_path = os.path.join(get_project_root(), 'third_party', 'BrickLayers', "bricklayers.py")
            output_path = os.path.join(cache_dir, f"{file_name_without_extfile_token}_output.gcode")
            if not os.path.exists(cache_dir):
                os.makedirs(cache_dir)
            with open(file_path, 'wb') as f:
                f.write(resp.content)
            logger.info('Download file %s successfully, try to handle.' % file_name)
            
            command = [
                "python",
                script_path,       # 被调用脚本路径
                file_path,         # 输入文件路径
                "-outputFile",
                output_path,       # 输出文件路径
                "-extrusionMultiplier",
                "1.05",
                "-verbosity",
                "1"
            ]
            try:
                # 执行命令并等待完成
                result = subprocess.run(
                    command,
                    check=True,            # 若子进程返回非零状态码则抛出异常
                    stdout=subprocess.PIPE, # 捕获标准输出
                    stderr=subprocess.PIPE, # 捕获错误输出
                    text=True,              # 以文本形式返回结果
                    timeout=10             # 设置超时时间
                )
                
            except subprocess.CalledProcessError as e:
                logger.error(f"脚本执行失败！返回码：{e.returncode}")
                logger.error("错误信息:\n", e.stderr)
            except FileNotFoundError:
                logger.error("错误：python 或脚本文件不存在！")

            if os.path.exists(output_path):
                logger.info('Handle file %s successfully, try upload file.' % file_name)
                with open(output_path, 'rb') as f:
                    resp = _fs.api.cloud.upload_all(
                        file_name=f"{file_name_without_extfile_token}_output.gcode",
                        parent_type="bitable_file",
                        parent_node=event.file_token,
                        size= str(os.path.getsize(output_path)),
                        file= (f)  
                    )
                
                upload_file_token = resp['data']['file_token']
                if not upload_file_token:
                    logger.error('Upload file %s failed.' % file_name)
                else:
                    _fs.api.bitable.batch_update_records(
                        app_token=_fs.bitables.gcode_optimize.file_token,
                        table_id=_fs.bitables.gcode_optimize.table_id,
                        records=[{
                            "record_id": record_id,
                            "fields": {
                                "处理结果":[
                                    {
                                        "file_token": upload_file_token
                                    }
                                ]
                            }
                        }]
                    )
                    logger.info('Upload file %s successfully.' % file_name)
                os.remove(output_path)
            os.remove(file_path)
            logger.info("Clear cache file %s successfully." % file_name)
        bitable_url = f"https://feishu.cn/base/{event.file_token}?table={event.table_id}"
        return f'Success: gcode_optimize_event_handler over,plz see bitable "gcode_optimize": {bitable_url}'
    except Exception as e:
        logger.error("Error in gcode_optimize_event_handler: %s" % str(e))
        return 'Error: gcode_optimize_event_handler: %s' % str(e)