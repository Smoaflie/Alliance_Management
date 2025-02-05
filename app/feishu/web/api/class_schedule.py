from ...config import FEISHU_CONFIG as _fs
from ..main import web_bp
from flask import request, jsonify


@web_bp.route("/class_schedule", methods=["POST"])
def update_class_schedule():
    user_name = request.args.get("userName")
    cookie = request.args.get("cookie")
    courses_info = get_courses_info(cookie)
    SHEET_TOKEN = _fs.class_schedule.sheet_token
    SHEET_ID = _fs.class_schedule.sheet_id
    resp = _fs.api.spreadsheet.reading_a_single_range(SHEET_TOKEN, SHEET_ID, "B1:B")
    member_list = resp["data"]["valueRange"]["values"]
    index = (
        next(i for i, sublist in enumerate(member_list) if sublist[0] == user_name) + 1
    )
    course_time_list = []
    for day_schedule in courses_info.values():  # 遍历每天的课程表
        for period in day_schedule.values():
            course_time_list.append(period)
    if any(s != "" for s in course_time_list):
        _fs.api.spreadsheet.write_date_to_a_single_range(
            SHEET_TOKEN, SHEET_ID, f"C{index}:AK{index}", [course_time_list]
        )
        return jsonify(courses_info)
    else:
        return jsonify(), 400


def get_courses_info(cookie):
    """从教务处获取课表信息"""
    import requests
    import re
    from bs4 import BeautifulSoup

    # 目标 URL
    url = "http://bkjw.njust.edu.cn/njlgdx/xskb/xskb_list.do?Ves632DSdyV=NEW_XSD_PYGL"

    # 自定义请求头
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0",
    }

    # 设置 Cookie
    cookies = {
        "JSESSIONID": cookie,
    }

    # 发送 GET 请求
    response = requests.get(url, headers=headers, cookies=cookies)

    # 解析 HTML
    soup = BeautifulSoup(response.text, "html.parser")
    # 获取所有课程的上课周次
    # 选取所有 class="kbcontent1" 的 div
    courses = {}
    for divs in soup.find_all("div", class_=lambda x: x and "kbcontent1" in x):
        for font in divs.find_all("font", title="周次(节次)"):
            course_name = font.find_previous(
                string=True
            ).strip()  # 获取课程名称（<br>前面的文本）
            week_info = font.get_text().strip()  # 获取周次信息
            week_value = re.findall(r"[0-9,\-]+", week_info)[0]
            courses[course_name] = {}
            courses[course_name]["week"] = week_value
    # 获取所有课程的上课节次
    # 解析表格数据
    for row in soup.find_all("tr"):
        cols = row.find_all("td")
        if len(cols) >= 10:  # 确保列数足够
            course_name = cols[3].text.strip()
            class_time = cols[5].text.strip()  # 上课时间
            # 正则匹配 上课日 和 对应节次
            matches = re.findall(
                r"(星期[一二三四五六日])\((\d{2}-\d{2})小节\)", class_time
            )
            courses[course_name]["class"] = matches

    def process_course_data(data):
        # 定义大节时间段映射
        sections_order = {
            "第一大节": (1, 3),
            "第二大节": (4, 5),
            "第三大节": (6, 7),
            "第四大节": (8, 10),
            "第五大节": (11, 13),
        }

        # 初始化结果字典
        weekdays = [
            "星期一",
            "星期二",
            "星期三",
            "星期四",
            "星期五",
            "星期六",
            "星期日",
        ]
        result = {day: {section: [] for section in sections_order} for day in weekdays}

        # 处理每个课程
        for course_name, course_info in data.items():
            week_range = course_info["week"]

            # 处理每个上课时间段
            for class_time in course_info["class"]:
                day = class_time[0]
                time_slot = class_time[1]

                # 解析节次范围
                start_str, end_str = time_slot.split("-")
                start = int(start_str)
                end = int(end_str)

                # 忽略14-14
                if start == 14 and end == 14:
                    continue

                # 确定影响的大节
                affected_sections = []
                for section_name, (sec_start, sec_end) in sections_order.items():
                    if start <= sec_end and end >= sec_start:
                        affected_sections.append(section_name)

                # 添加到结果字典
                for section in affected_sections:
                    if week_range not in result[day][section]:
                        result[day][section].append(week_range)

        # 合并周次范围并格式化
        final_result = {}
        for day in weekdays:
            day_data = {}
            for section_name in sections_order:
                # 合并连续周次
                merged = merge_week_ranges(result[day][section_name])
                if merged:
                    day_data[section_name] = merged
                else:
                    day_data[section_name] = ""
            if day_data:
                final_result[day] = day_data

        return final_result

    def merge_week_ranges(week_list):
        """合并连续的周次范围"""
        if not week_list:
            return ""

        # 将字符串转换为数字区间
        intervals = []
        for week in week_list:
            for part in week.split(","):
                start, end = map(int, part.strip().split("-"))
                intervals.append((start, end))

        # 合并区间
        intervals.sort()
        merged = [intervals[0]]
        for current in intervals[1:]:
            last = merged[-1]
            if current[0] <= last[1] + 1:
                merged[-1] = (last[0], max(last[1], current[1]))
            else:
                merged.append(current)

        # 转换回字符串
        return ", ".join([f"{s}-{e}" for s, e in merged])

    return process_course_data(courses)
