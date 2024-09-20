import ujson

def debug(data=None, json=None, file='request.json'):
    with open(file, 'w') as f:
        json_str = ujson.dumps(data, indent=4) if data else json # 格式化写入 JSON 文件
        f.write(json_str)

