import ujson

def DEBUG_OUT(data=None, json=None, file='request.json'):
    with open(file, 'w') as f:
        json_str = ujson.dumps(data, indent=4, ensure_ascii=False) if data else json # 格式化写入 JSON 文件
        f.write(json_str)

