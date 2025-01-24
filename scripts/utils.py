import ujson
import sys
import os
"""
该文件存储了一些工具类函数
"""

class Obj(dict):
    """自定义对象类,用于将字典转换成对象"""
    def __init__(self, d):
        for a, b in d.items():
            if isinstance(b, (list, tuple)):
                setattr(self, a, [Obj(x) if isinstance(x, dict) else x for x in b])
            else:
                setattr(self, a, Obj(b) if isinstance(b, dict) else b)

def dict_2_obj(d: dict):
    return Obj(d)

def obj_2_dict(o: Obj) -> dict:
    r = {}
    for a, b in o.__dict__.items():
        if isinstance(b, str):
            r[a] = b
        elif isinstance(b, (list, tuple)):
            r[a] = [obj_2_dict(x) if isinstance(x, Obj) else x for x in b]
        elif isinstance(b, Obj):
            r[a] = obj_2_dict(b)
    return r

def DEBUG_OUT(data=None, json=None, file='request.json'):
    """调试时输出数据到文件中."""
    with open(file, 'w') as f:
        json_str = ujson.dumps(data, indent=4, ensure_ascii=False) if data else json # 格式化写入 JSON 文件
        f.write(json_str)


def get_display_width(s):
    """计算字符串的显示宽度，中文字符占2个单位，英文字符、数字和全角空格占1个单位"""
    full_width = 0
    half_width = 0
    for char in s:
        if ord(char) > 255 or char == '\u3000':  # 中文字符and全角空格
            full_width += 1
        else:  # 英文字符和数字
            half_width += 1
    return full_width, half_width

def format_with_margin(s, margin, assign_full_width_num=None):
    """根据给定的宽度格式化字符串"""
    s = str(s)
    full_width, half_width = get_display_width(s)
    if full_width*2+half_width >= margin:
        return s  # 如果字符串已经超过了margin，返回原字符串
    
    if not assign_full_width_num:
        full_width_num = 0
        half_width_num = margin - (full_width*2+half_width)
    else:
        full_width_num = assign_full_width_num - full_width if assign_full_width_num>full_width else 0
        half_width_num = margin-((full_width_num+full_width)*2+half_width) if margin>(full_width_num+full_width)*2+half_width else 0
    # 使用全角空格+数样间距 (figure space)填充
    return s + '\u3000' * full_width_num + "\u2007" * half_width_num

def is_valid(sstr, errors):
    """判断字符串是否合法"""
    voidc = ["'", '"', '\\', '<', '>', '(', ')', '.', '=']
    for ccc in voidc:
        if ccc in str(sstr):
            errors.append(f'parameters error:\n"{sstr}" is not valid')

def can_convert_to_int(a):
    """判断变量能否转变成int类型"""
    try:
        int(a)
        return True
    except (ValueError, TypeError):
        return False

def replace_placeholders(data, values):
    """
    格式化字典中 ${name} 格式的字符串
    """
    if isinstance(data, dict):
        for key, value in data.items():
            data[key] = replace_placeholders(value, values)
    elif isinstance(data, list):
        for index in range(len(data)):
            data[index] = replace_placeholders(data[index], values)
    elif isinstance(data, str):
        for key, value in values.items():
            data = data.replace(f"${{{key}}}", str(value))
    return data

def load_file(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return ujson.load(f)
    except FileNotFoundError:
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    except ujson.JSONDecodeError as e:
        raise ValueError(f"Error decoding JSON in {file_path}: {e}")
    except Exception as e:
        raise RuntimeError(f"Unexpected error occurred while reading {file_path}: {e}")

def get_project_root():
    """
    获取当前工程目录的根路径，通过递归查找特定标志文件或文件夹。
    """
    current_path = os.path.abspath(os.path.dirname(__file__))
    while current_path:
        if any(os.path.exists(os.path.join(current_path, marker)) for marker in ['main.py']):
            return current_path
        parent_path = os.path.dirname(current_path)
        if parent_path == current_path:  # 已经到根目录
            break
        current_path = parent_path
    raise RuntimeError("无法找到工程根目录，请确保有标志文件（如 requirements.txt 或 .git）")

def safe_get(data, *keys, default=None):
    """安全地从嵌套字典中获取值"""
    for key in keys:
        if isinstance(data, dict):
            data = data.get(key)
        else:
            return default
    return data