import csv
import os
import json
from datetime import datetime, timedelta

# 파일 경로와 작업 시간 정의
LOG_FILE = "attendance.csv"
LAST_RESET_FILE = "last_reset.txt"
HOLIDAYS_FILE = "holidays.json"
WORK_HOURS = (8, 22)

from datetime import datetime

def format_date_and_time():
    days_in_korean = ["일요일", "월요일", "화요일", "수요일", "목요일", "금요일", "토요일"]
    now = datetime.now()
    korean_day = days_in_korean[now.weekday()]
    formatted_date = now.strftime(f"%Y년 %m월 %d일 {korean_day}")
    formatted_time = now.strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")
    return formatted_date, formatted_time

def reset_logs_with_timestamp():
    """
    오늘 날짜 기준으로 로그 초기화. 이미 초기화된 경우 무시.
    """
    today_date = datetime.now().strftime("%Y-%m-%d")
    if os.path.exists(LAST_RESET_FILE):
        with open(LAST_RESET_FILE, "r") as file:
            last_reset_date = file.read().strip()
        if last_reset_date == today_date:
            return  # 이미 초기화됨

    # 로그 파일 초기화
    with open(LOG_FILE, mode="w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["학번", "날짜", "시간", "기록"])  # 헤더 추가

    # 마지막 초기화 날짜 갱신
    with open(LAST_RESET_FILE, "w") as file:
        file.write(today_date)

def load_holidays():
    """
    공휴일 데이터를 JSON 파일에서 로드.
    """
    if not os.path.exists(HOLIDAYS_FILE):
        with open(HOLIDAYS_FILE, "w") as file:
            json.dump([], file)
    with open(HOLIDAYS_FILE, "r") as file:
        return json.load(file)

def save_holidays(holidays):
    """
    공휴일 데이터를 JSON 파일에 저장.
    """
    with open(HOLIDAYS_FILE, "w") as file:
        json.dump(holidays, file, indent=4)


def is_valid_day_and_time():
    """
    현재 시간이 출근 가능한 요일 및 시간인지 확인.
    """
    now = datetime.now()
    weekday = now.weekday()
    hour = now.hour
    today_date = now.strftime("%Y-%m-%d")
    holidays = load_holidays()
    return (0 <= weekday < 5) and (today_date not in holidays) and (WORK_HOURS[0] <= hour < WORK_HOURS[1])


def has_record(student_id, record_type):
    """
    특정 학번과 기록 유형의 기록 여부 확인 및 시간 반환.
    """
    try:
        with open(LOG_FILE, mode="r", encoding="utf-8") as file:
            reader = csv.reader(file)
            next(reader)  # 헤더 건너뜀
            today_date = datetime.now().strftime("%Y-%m-%d")
            for row in reader:
                if row[0] == student_id and row[1] == today_date and row[3] == record_type:
                    return datetime.strptime(row[2], "%H:%M:%S").strftime("%p %I:%M").replace("AM", "오전").replace("PM", "오후")
    except FileNotFoundError:
        pass
    return None  # 기록 없음

def write_to_csv(student_id, action_type):
    """
    학번과 동작 유형을 CSV 파일에 기록.
    """
    with open(LOG_FILE, mode="a", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow([student_id, datetime.now().strftime("%Y-%m-%d"), datetime.now().strftime("%H:%M:%S"), action_type])

def calculate_weekly_data(week_start, week_end):
    """
    주간 데이터를 계산하여 각 학번의 근무 시간과 출퇴근 기록 반환.
    """
    if not os.path.exists(LOG_FILE):
        return {}

    week_data = {}
    with open(LOG_FILE, mode="r", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader)  # 헤더 건너뜀
        for row in reader:
            student_id, date, time, record_type = row
            record_date = datetime.strptime(date, "%Y-%m-%d")

            if week_start <= record_date <= week_end:
                if student_id not in week_data:
                    week_data[student_id] = {day: {"출근": None, "퇴근": None, "근무시간": "0시간"} for day in range(5)}
                day_of_week = record_date.weekday()
                if day_of_week < 5:  # 월~금만 기록
                    if record_type == "출근":
                        week_data[student_id][day_of_week]["출근"] = time
                    elif record_type == "퇴근":
                        week_data[student_id][day_of_week]["퇴근"] = time

    # 근무 시간 계산
    for student_id, days in week_data.items():
        for day, records in days.items():
            if records["출근"] and records["퇴근"]:
                start_time = datetime.strptime(records["출근"], "%H:%M:%S")
                end_time = datetime.strptime(records["퇴근"], "%H:%M:%S")
                total_minutes = (end_time - start_time).seconds // 60
                hours = total_minutes // 60
                minutes = total_minutes % 60
                if minutes >= 15:
                    minutes = 30 if minutes < 45 else 0
                    if minutes == 0:
                        hours += 1
                records["근무시간"] = f"{hours + (minutes / 60):.1f}".rstrip('0').rstrip('.')

    return week_data
