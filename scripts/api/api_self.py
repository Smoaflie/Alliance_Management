import ujson

def DEBUG_OUT(data=None, json=None, file='request.json'):
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
    voidc = ["'", '"', '\\', '<', '>', '(', ')', '.', '=']
    for ccc in voidc:
        if ccc in str(sstr):
            errors.append(f'parameters error:\n"{sstr}" is not valid')

def can_convert_to_int(a):
    try:
        int(a)
        return True
    except (ValueError, TypeError):
        return False

def replace_placeholders(data, values):
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