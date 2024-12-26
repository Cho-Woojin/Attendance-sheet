import os
import csv
import json
from datetime import datetime, timedelta
from flask import render_template, request
from models import (
    write_to_csv,
    reset_logs_with_timestamp,
    load_holidays,
    save_holidays,
    is_valid_day_and_time,
    has_record,
    calculate_weekly_data,
)


# CSV 파일 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = "attendance.csv"
BACKUP_DIR = "backups"
STUDENT_FILE = "students.json"


# 백업 생성 함수
def backup_csv():
    """
    매일 백업 디렉토리에 현재 CSV 파일을 백업합니다.
    """
    if not os.path.exists(BACKUP_DIR):
        os.makedirs(BACKUP_DIR)
    today = datetime.now().strftime("%Y-%m-%d")
    backup_file = os.path.join(BACKUP_DIR, f"attendance_backup_{today}.csv")
    if not os.path.exists(backup_file):  # 이미 백업된 경우 건너뜀
        if os.path.exists(LOG_FILE):
            with open(LOG_FILE, "r", encoding="utf-8") as file:
                with open(backup_file, "w", encoding="utf-8") as backup:
                    backup.write(file.read())


# 시간 반올림 함수
def round_time_to_decimal(time_obj):
    """
    시간(datetime 객체)을 소수점 형식으로 반올림하여 반환.
    """
    hour = time_obj.hour
    minute = time_obj.minute
    if minute < 15:
        minute_decimal = 0.0
    elif minute < 45:
        minute_decimal = 0.5
    else:
        minute_decimal = 1.0
    return f"{hour + minute_decimal:.1f}"


def load_student_data():
    """
    학생 정보(학번-이름)를 JSON 파일에서 불러옴.
    """
    with open("students.json", "r", encoding="utf-8") as file:
        return json.load(file)


def init_routes(app):
    # 홈페이지
    @app.route("/")
    def home():
        backup_csv()  # 매일 백업 실행
        formatted_date = get_current_date()
        current_time = get_current_time()
        return render_template(
            "home.html", date=formatted_date, time=current_time, message=None
        )

    # 출근/퇴근 기록
    @app.route("/record", methods=["POST"])
    def record():
        student_data = load_student_data()  # 학생 정보 로드
        student_id = request.form.get(
            "student_id", ""
        ).strip()  # 학번 입력, 누락 시 기본값 ""
        action = request.form.get(
            "action", ""
        ).strip()  # 출근 또는 퇴근 액션 값, 누락 시 기본값 ""

        # 학번 또는 액션 값 누락 시
        if not student_id or not action:
            return render_home(
                "학번과 액션 값이 필요합니다. 입력 후 다시 시도해주세요."
            )

        current_time = (
            datetime.now()
            .strftime("%p %I:%M")
            .replace("AM", "오전")
            .replace("PM", "오후")
        )

        # 학생 이름 매핑
        student_name = student_data.get(student_id, None)
        if not student_name:
            return render_home("학번이 등록되지 않았습니다. 다시 확인해주세요.")

        # 출퇴근 가능 시간 확인
        if not is_valid_day_and_time():
            return render_home(
                f"{student_name}님, 출퇴근 가능 시간이 아닙니다. (평일 08:00 ~ 22:00)"
            )

        # 출근 처리
        if action == "check_in":
            if has_record(student_id, "출근"):
                return render_home(f"{student_name}님, 이미 출근 기록이 존재합니다.")
            write_to_csv(student_id, "출근")
            return render_home(
                f"{student_name}님, {current_time} 출근 기록이 추가되었습니다."
            )

        # 퇴근 처리
        elif action == "check_out":
            if not has_record(student_id, "출근"):
                return render_home(
                    f"{student_name}님, 출근 기록이 없습니다. 먼저 출근을 기록해주세요."
                )
            if has_record(student_id, "퇴근"):
                return render_home(f"{student_name}님, 이미 퇴근 기록이 존재합니다.")
            write_to_csv(student_id, "퇴근")
            return render_home(
                f"{student_name}님, {current_time} 퇴근 기록이 추가되었습니다."
            )

    # 주간 출석부
    @app.route("/weekly", methods=["GET", "POST"])
    def weekly():
        student_data = load_student_data()  # 학생 정보 로드
        current_year = datetime.now().year
        today = datetime.now().date()

        # 주차와 월 선택
        if request.method == "POST":
            selected_month = int(request.form.get("month"))
            selected_week = int(request.form.get("week"))

            # 선택한 월과 주차의 첫 번째 날 계산
            month_start = datetime(current_year, selected_month, 1)
            week_start = month_start + timedelta(weeks=selected_week - 1)
            week_start = week_start - timedelta(
                days=week_start.weekday()
            )  # 해당 주의 월요일로 설정
        else:
            # 기본적으로 현재 주차로 설정
            week_start = datetime.now() - timedelta(days=datetime.now().weekday())
            selected_month = week_start.month
            selected_week = (week_start.day - 1) // 7 + 1

        week_end = week_start + timedelta(days=4)  # 해당 주의 금요일

        # 미래 주차 조회 시 빈 데이터 반환
        if week_start.date() > today:
            week_data = {
                student_data[student_id]: {} for student_id in student_data.keys()
            }
            title = f"{selected_month}월({selected_week}주차): 미래 주차"
            ranked_hours = []
        else:
            # 주간 데이터 계산
            week_data = calculate_weekly_data(week_start, week_end)

            # 학생 목록을 기준으로 주차 데이터 구성
            complete_week_data = {}
            for student_id, student_name in student_data.items():
                student_days = week_data.get(
                    student_id,
                    {
                        day: {"출근": None, "퇴근": None, "근무시간": "0.0"}
                        for day in ["월요일", "화요일", "수요일", "목요일", "금요일"]
                    },
                )
                complete_week_data[student_name] = student_days

            # 정렬된 데이터
            week_data = dict(sorted(complete_week_data.items()))

            # 근무 시간 계산 및 정렬
            total_hours = []
            for student_name, days in week_data.items():
                total_time = sum(
                    float(day["근무시간"])
                    for day in days.values()
                    if day["근무시간"] != "0.0"
                )
                total_hours.append((student_name, total_time))
            ranked_hours = sorted(total_hours, key=lambda x: (-x[1], x[0]))

            title = f"{selected_month}월({selected_week}주차, {week_start.strftime('%m/%d')}~{week_end.strftime('%m/%d')}) 출석부"

        # 템플릿으로 데이터 전달
        return render_template(
            "weekly.html",
            title=title,
            week_data=week_data,
            ranked_hours=ranked_hours,
            selected_month=selected_month,
            selected_week=selected_week,
            enumerate=enumerate,
        )

    # 공휴일 관리
    @app.route("/manage_holidays", methods=["GET", "POST"])
    def manage_holidays():
        holidays = load_holidays()
        if request.method == "POST":
            action = request.form["action"]
            if action == "add":
                new_date = request.form["date"]
                if new_date not in holidays:
                    holidays.append(new_date)
            elif action == "delete_selected":
                selected_dates = request.form.getlist(
                    "selected_dates"
                )  # 다중 선택된 날짜
                holidays = [h for h in holidays if h not in selected_dates]
            save_holidays(holidays)
        return render_template("manage_holidays.html", holidays=holidays)

    # 헬퍼 함수
    def render_home(message):
        """
        헬퍼 함수: 홈 페이지로 메시지와 함께 리디렉션합니다.
        """
        # 메시지에 줄 바꿈 추가 (HTML 태그 사용)
        if "출퇴근 가능 시간이 아닙니다" in message:
            message = message.replace("(", "<br>(")  # 줄 바꿈을 추가

        return render_template(
            "home.html",
            date=get_current_date(),
            time=get_current_time(),
            message=message,
        )

    def get_current_date():
        days_in_korean = [
            "월요일",
            "화요일",
            "수요일",
            "목요일",
            "금요일",
            "토요일",
            "일요일",
        ]
        now = datetime.now()
        korean_day = days_in_korean[now.weekday()]
        return now.strftime(f"%Y년 %m월 %d일 {korean_day}")

    def get_current_time():
        return (
            datetime.now()
            .strftime("%p %I:%M")
            .replace("AM", "오전")
            .replace("PM", "오후")
        )
