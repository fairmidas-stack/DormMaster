import streamlit.elements.image as st_image
if not hasattr(st_image, "UseColumnWith"):
    st_image.UseColumnWith = bool

import os
import json
import uuid
from datetime import date

import streamlit as st
import pandas as pd
import gspread
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates
from streamlit_option_menu import option_menu

# --- 설정 ---
st.set_page_config(
    page_title="숙소동 관리 시스템",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ============================================================
# [보안] 비밀번호는 st.secrets에서 불러옵니다.
# secrets.toml 예시:
# [passwords]
# guest = "1234"
# admin = "0416"
# ============================================================
GUEST_PASSWORD = st.secrets.get("passwords", {}).get("guest", "1234")
ADMIN_PASSWORD = st.secrets.get("passwords", {}).get("admin", "0416")

# 로그인 시도 최대 횟수
MAX_LOGIN_ATTEMPTS = 5


# ============================================================
# 마스킹 함수 모음 (전화번호 함수화 포함)
# ============================================================

def mask_name(name):
    """이름 마스킹: 2글자 → 첫 글자 + *, 3글자 이상 → 첫 글자 + ** + 끝 글자"""
    if not name or len(str(name)) == 0:
        return name
    n = str(name)
    if len(n) == 1:
        return n
    elif len(n) == 2:
        # 두 글자 이름: 두 번째 글자 마스킹 (예: 김* )
        return n[0] + "*"
    else:
        # 세 글자 이상: 첫 글자 + 중간 전부 * + 끝 글자
        return n[0] + "*" * (len(n) - 2) + n[-1]


def mask_phone(phone):
    """전화번호 마스킹: 앞 3자리-****-뒤 4자리"""
    p = str(phone).strip()
    # 숫자만 추출
    digits = "".join(filter(str.isdigit, p))
    if len(digits) >= 10:
        return f"{digits[:3]}-****-{digits[-4:]}"
    elif len(digits) >= 4:
        return f"****-{digits[-4:]}"
    else:
        return "****"


def mask_car(car):
    """차량번호 마스킹: 끝 2자리 **"""
    if not car or len(str(car)) < 2:
        return car
    return str(car)[:-2] + "**"


def mask_date(dt_str):
    """날짜 마스킹: YYYY-MM-** 형태"""
    if not dt_str or len(str(dt_str)) < 10:
        return dt_str
    return str(dt_str)[:8] + "**"


# ============================================================
# 구글 시트 연동 함수
# ============================================================

def get_gspread_client():
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    gc = gspread.service_account_from_dict(creds_dict)
    return gc


def load_data():
    try:
        gc = get_gspread_client()
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = doc.worksheet("room_users")
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except Exception:
        return pd.DataFrame(columns=[
            "user_id", "room_number", "name", "gender",
            "phone", "car_number", "check_in", "check_out",
            "status", "is_active"
        ])


def auto_backup(df):
    try:
        gc = get_gspread_client()
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        try:
            backup_ws = doc.worksheet("backup_log")
        except gspread.exceptions.WorksheetNotFound:
            backup_ws = doc.add_worksheet(title="backup_log", rows="1000", cols="20")
        backup_data = [df.columns.values.tolist()] + df.values.tolist()
        backup_ws.update(values=backup_data, range_name='A1')
        return True
    except Exception:
        return False


def update_gsheet(df):
    try:
        gc = get_gspread_client()
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = doc.worksheet("room_users")
        auto_backup(df)
        data_to_write = [df.columns.values.tolist()] + df.values.tolist()
        worksheet.update(values=data_to_write, range_name='A1')
        current_rows = len(worksheet.get_all_values())
        new_rows = len(data_to_write)
        if current_rows > new_rows:
            worksheet.delete_rows(new_rows + 1, current_rows)
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ 저장 오류: {e}")
        return False


# ============================================================
# 1단계: 로그인 (입구 컷) — 시도 횟수 제한 포함
# ============================================================

if "authenticated" not in st.session_state:
    st.session_state["authenticated"] = False

if "login_attempts" not in st.session_state:
    st.session_state["login_attempts"] = 0

if not st.session_state["authenticated"]:
    st.title("🔒 숙소동 관리 시스템")

    # 시도 횟수 초과 시 잠금
    if st.session_state["login_attempts"] >= MAX_LOGIN_ATTEMPTS:
        st.error(f"❌ 비밀번호 오류가 {MAX_LOGIN_ATTEMPTS}회를 초과하였습니다. 관리자에게 문의하세요.")
        st.stop()

    remaining = MAX_LOGIN_ATTEMPTS - st.session_state["login_attempts"]
    st.caption(f"🔑 남은 시도 횟수: {remaining}회")

    input_pw = st.text_input("접속 비밀번호를 입력하세요", type="password")

    if st.button("입장하기"):
        if input_pw == GUEST_PASSWORD or input_pw == ADMIN_PASSWORD:
            st.session_state["authenticated"] = True
            st.session_state["login_attempts"] = 0  # 성공 시 초기화
            st.rerun()
        else:
            st.session_state["login_attempts"] += 1
            failed = st.session_state["login_attempts"]
            left = MAX_LOGIN_ATTEMPTS - failed
            if left > 0:
                st.error(f"비밀번호가 틀렸습니다. (남은 시도: {left}회)")
            else:
                st.error(f"❌ 비밀번호 오류가 {MAX_LOGIN_ATTEMPTS}회를 초과하였습니다. 관리자에게 문의하세요.")

    st.stop()


# ============================================================
# 이하: 로그인 통과 후 실행
# ============================================================

df_all = load_data()
df_all['is_active'] = pd.to_numeric(df_all['is_active'], errors='coerce').fillna(1)
df_active = df_all[df_all["is_active"] == 1]

if "room" not in st.session_state:
    st.session_state["room"] = None

# 사이드바
with st.sidebar:
    st.title("🏢 숙소동 관리")
    selected = option_menu(
        None,
        ["실시간 도면", "전체 명단", "퇴실 히스토리"],
        icons=["map", "list-task", "archive"],
        default_index=0
    )
    search_q = st.text_input("🔍 통합 검색", placeholder="이름/방/번호")
    st.divider()
    admin_input = st.text_input("관리자 비밀번호", type="password")
    is_admin = (admin_input == ADMIN_PASSWORD)

    if st.button("로그아웃 (화면잠금)"):
        st.session_state["authenticated"] = False
        st.session_state["login_attempts"] = 0
        st.rerun()

if search_q:
    df_active = df_active[
        df_active["name"].astype(str).str.contains(search_q, na=False) |
        df_active["room_number"].astype(str).str.contains(search_q, na=False) |
        df_active["phone"].astype(str).str.contains(search_q, na=False)
    ]


# ============================================================
# 메뉴 1: 실시간 도면
# ============================================================

if selected == "실시간 도면":
    m1, m2, m3 = st.columns(3)
    m1.metric("현재 거주자", f"{len(df_active)}명")
    m2.metric("점유 중인 방", f"{df_active['room_number'].nunique()}실")
    m3.metric(
        "오늘 입실",
        f"{len(df_active[df_active['check_in'].astype(str).str.contains(date.today().strftime('%Y-%m-%d'))])}명"
    )

    st.divider()

    room_map = {}
    for r in df_active.to_dict('records'):
        room_map.setdefault(str(r["room_number"]), []).append(r)

    left, right = st.columns([2, 1])

    with left:
        if os.path.exists("dorm_map.png"):
            img = Image.open("dorm_map.png")
            target_width = 800
            ratio = target_width / 800
            img = img.resize((target_width, int(img.size[1] * target_width / img.size[0])))
            draw = ImageDraw.Draw(img)
            try:
                font = ImageFont.truetype("malgun.ttf", int(14 * ratio))
            except Exception:
                font = ImageFont.load_default()

            ROOM_COORDS = json.load(open("room_coords.json")) if os.path.exists("room_coords.json") else {}

            for room, (orig_x, orig_y) in ROOM_COORDS.items():
                x, y = orig_x * ratio, orig_y * ratio
                users = room_map.get(str(room), [])
                color = "#fa5252" if users else "#40c057"
                r_size = 13 * ratio
                draw.ellipse(
                    (x - r_size, y - r_size, x + r_size, y + r_size),
                    fill=color, outline="white", width=2
                )
                room_str = str(room)
                room_int = int(room_str) if room_str.isdigit() else 0
                last_two = room_int % 100
                if 1 <= last_two <= 9:
                    text_x, text_y = x - (35 * ratio), y - (8 * ratio)
                elif 501 <= room_int <= 504:
                    text_x, text_y = x - (10 * ratio), y - (32 * ratio)
                else:
                    text_x, text_y = x - (10 * ratio), y - (28 * ratio)
                draw.text((text_x, text_y), room_str, fill="#333333", font=font)

            coords = streamlit_image_coordinates(img, key="dorm_map_final")
            if coords:
                min_dist = 999999
                new_room = None
                for r, (ox, oy) in ROOM_COORDS.items():
                    dist = ((coords["x"] - (ox * ratio)) ** 2 + (coords["y"] - (oy * ratio)) ** 2) ** 0.5
                    if dist < (25 * ratio) and dist < min_dist:
                        min_dist = dist
                        new_room = r
                if new_room and new_room != st.session_state.get("room"):
                    st.session_state["room"] = new_room
                    st.rerun()

    with right:
        sel_room = st.session_state.get("room")
        if sel_room:
            st.subheader(f"🏠 {sel_room}호 정보")
            users = room_map.get(str(sel_room), [])
            if not users:
                st.write("현재 빈 방입니다.")
            for u in users:
                if is_admin:
                    name_display = u['name']
                    phone_display = u['phone']
                    car_display = u['car_number']
                    check_in_display = u['check_in']
                else:
                    name_display = mask_name(u['name'])
                    phone_display = mask_phone(u['phone'])
                    car_display = mask_car(u['car_number'])
                    check_in_display = mask_date(u['check_in'])

                st.markdown(f"""
                <div style="border:1px solid #ddd; padding:10px; border-radius:10px;
                            margin-bottom:10px; background-color:#f9f9f9;">
                    <h4 style="margin: 0;">{name_display} ({u['gender']})</h4>
                    <p style="margin:5px 0;">📞 {phone_display} | 🚗 {car_display}</p>
                    <p style="margin:0; font-size:0.85em; color:gray;">📅 입실: {check_in_display}</p>
                </div>
                """, unsafe_allow_html=True)

                if is_admin:
                    with st.expander("🚪 퇴실 처리"):
                        out_date = st.date_input("퇴실일", value=date.today(), key=f"dout_{u['user_id']}")
                        if st.button("퇴실 확정", key=f"bout_{u['user_id']}", type="primary"):
                            df_all.loc[df_all['user_id'] == u['user_id'], ['is_active', 'check_out']] = \
                                [0, out_date.strftime('%Y-%m-%d')]
                            if update_gsheet(df_all):
                                st.rerun()

                    with st.expander("📝 정보 수정"):
                        with st.form(key=f"edit_{u['user_id']}"):
                            en = st.text_input("이름", value=u['name'])
                            ep = st.text_input("연락처", value=u['phone'])
                            ec = st.text_input("차량번호", value=u['car_number'])
                            er = st.text_input("방 번호", value=u['room_number'])
                            if st.form_submit_button("수정 저장"):
                                idx = df_all[df_all['user_id'] == u['user_id']].index
                                df_all.loc[idx, ['name', 'phone', 'car_number', 'room_number']] = [en, ep, ec, er]
                                if update_gsheet(df_all):
                                    st.rerun()

            if is_admin and len(users) < 4:
                st.divider()
                with st.expander("➕ 신규 입실 등록"):
                    with st.form("add_user_form"):
                        nn = st.text_input("성함*")
                        ng = st.selectbox("성별", ["남", "여"])
                        np_ = st.text_input("연락처*")
                        nc = st.text_input("차량번호")
                        ni = st.date_input("입실일", value=date.today())
                        if st.form_submit_button("입실 저장"):
                            if nn and np_:
                                last_id = pd.to_numeric(df_all["user_id"], errors='coerce').max()
                                new_id = int(last_id + 1) if not pd.isna(last_id) else 1
                                new_row = {
                                    "user_id": new_id,
                                    "room_number": str(sel_room),
                                    "name": nn,
                                    "gender": ng,
                                    "phone": np_,
                                    "car_number": nc,
                                    "check_in": ni.strftime('%Y-%m-%d'),
                                    "check_out": "",
                                    "status": "occupied",
                                    "is_active": 1
                                }
                                df_new = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
                                if update_gsheet(df_new):
                                    st.rerun()
        else:
            st.info("👈 왼쪽 도면에서 방 번호를 클릭하세요.")


# ============================================================
# 메뉴 2: 전체 명단
# ============================================================

elif selected == "전체 명단":
    st.subheader("📋 현재 거주자 명단")
    display_df = df_active.copy()
    if not is_admin:
        display_df['name'] = display_df['name'].apply(mask_name)
        display_df['phone'] = display_df['phone'].apply(mask_phone)
        display_df['car_number'] = display_df['car_number'].apply(mask_car)
        display_df['check_in'] = display_df['check_in'].apply(mask_date)
    st.dataframe(display_df, use_container_width=True)


# ============================================================
# 메뉴 3: 퇴실 히스토리
# ============================================================

elif selected == "퇴실 히스토리":
    st.subheader("📚 과거 퇴실자 기록")
    display_df = df_all[df_all["is_active"] == 0].copy()
    if not is_admin:
        display_df['name'] = display_df['name'].apply(mask_name)
        display_df['phone'] = display_df['phone'].apply(mask_phone)
        display_df['car_number'] = display_df['car_number'].apply(mask_car)
        display_df['check_in'] = display_df['check_in'].apply(mask_date)
    st.dataframe(display_df, use_container_width=True)
