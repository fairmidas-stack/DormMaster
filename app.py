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

# --- 설정: 화면을 넓게 쓰고 제목 설정 ---
st.set_page_config(
    page_title="숙소동 관리 시스템",
    layout="wide",  
    initial_sidebar_state="expanded"
)

# 1. VIP 전용 구글 시트 직접 연결 함수
def get_gspread_client():
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    gc = gspread.service_account_from_dict(creds_dict)
    return gc

# 2. 데이터 불러오기
def load_data():
    try:
        gc = get_gspread_client()
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = doc.worksheet("room_users")
        data = worksheet.get_all_records()
        return pd.DataFrame(data)
    except:
        return pd.DataFrame(columns=["user_id", "room_number", "name", "gender", "phone", "car_number", "check_in", "check_out", "status", "is_active"])

# 3. 데이터 저장하기
def update_gsheet(df):
    try:
        gc = get_gspread_client()
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = doc.worksheet("room_users")
        worksheet.clear()
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.cache_data.clear()
        return True
    except Exception as e:
        st.error(f"⚠️ 저장 실패 상세 원인: {e}")
        return False

# 데이터 로드 및 전처리
df_all = load_data()
df_all['is_active'] = pd.to_numeric(df_all['is_active'], errors='coerce').fillna(1)
df_active = df_all[df_all["is_active"] == 1]

if "room" not in st.session_state:
    st.session_state["room"] = None

# 4. 사이드바 구성
with st.sidebar:
    st.title("🏢 숙소동 관리")
    selected = option_menu(None, ["실시간 도면", "전체 명단", "퇴실 히스토리"], 
                          icons=["map", "list-task", "archive"], default_index=0)
    search_q = st.text_input("🔍 통합 검색", placeholder="이름/방/번호")
    st.divider()
    password = st.text_input("관리자 비밀번호", type="password")
    is_admin = (password == "0416")

if search_q:
    df_active = df_active[df_active["name"].astype(str).str.contains(search_q, na=False) | 
                          df_active["room_number"].astype(str).str.contains(search_q, na=False) |
                          df_active["phone"].astype(str).str.contains(search_q, na=False)]

# --- [메뉴 1: 실시간 도면] ---
if selected == "실시간 도면":
    m1, m2, m3 = st.columns(3)
    m1.metric("현재 거주자", f"{len(df_active)}명")
    m2.metric("점유 중인 방", f"{df_active['room_number'].nunique()}실")
    m3.metric("오늘 입실", f"{len(df_active[df_active['check_in'].astype(str).str.contains(date.today().strftime('%Y-%m-%d'))])}명")
    
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
            img = img.resize((target_width, int(img.size[1]*target_width/img.size[0])))
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype("malgun.ttf", int(14 * ratio))
            except: font = ImageFont.load_default()

            ROOM_COORDS = json.load(open("room_coords.json")) if os.path.exists("room_coords.json") else {}

            for room, (orig_x, orig_y) in ROOM_COORDS.items():
                x, y = orig_x * ratio, orig_y * ratio
                users = room_map.get(str(room), [])
                color = "#fa5252" if users else "#40c057"
                
                r_size = 13 * ratio
                draw.ellipse((x-r_size, y-r_size, x+r_size, y+r_size), fill=color, outline="white", width=2)
                
                # --- [방 번호 텍스트 위치 가독성 최적화] ---
                room_str = str(room)
                room_int = int(room_str) if room_str.isdigit() else 0
                last_two = room_int % 100 

                # 1. 오른쪽 대각선 구역 (x01~x09호) : 원의 왼쪽으로 글자 배치
                if 1 <= last_two <= 9:
                    text_x, text_y = x - (35 * ratio), y - (8 * ratio)
                # 2. 501~504호 구역 : 위쪽 여백 더 확보
                elif 501 <= room_int <= 504:
                    text_x, text_y = x - (10 * ratio), y - (32 * ratio)
                # 3. 기타 구역 : 기본 위쪽 배치
                else:
                    text_x, text_y = x - (10 * ratio), y - (28 * ratio)

                draw.text((text_x, text_y), room_str, fill="#333333", font=font) 

            # 좌표 판정 핵심 로직
            coords = streamlit_image_coordinates(img, key="dorm_map_final")
            if coords:
                min_dist = 999999
                new_room = None
                for r, (ox, oy) in ROOM_COORDS.items():
                    dist = ((coords["x"] - (ox * ratio))**2 + (coords["y"] - (oy * ratio))**2)**0.5
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
                st.markdown(f"""
                <div style="border:1px solid #ddd; padding:10px; border-radius:10px; margin-bottom:10px; background-color:#f9f9f9;">
                    <h4 style="margin: 0;">{u['name']} ({u['gender']})</h4>
                    <p style="margin:5px 0;">📞 {u['phone']} | 🚗 {u['car_number']}</p>
                    <p style="margin:0; font-size:0.85em; color:gray;">📅 입실: {u['check_in']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_admin:
                    with st.expander(f"🚪 퇴실 처리"):
                        out_date = st.date_input("퇴실일 선택", value=date.today(), key=f"dout_{u['user_id']}")
                        if st.button("퇴실 확정", key=f"bout_{u['user_id']}", type="primary"):
                            df_all.loc[df_all['user_id'] == u['user_id'], ['is_active', 'check_out']] = [0, out_date.strftime('%Y-%m-%d')]
                            if update_gsheet(df_all): st.rerun()

                    with st.expander(f"📝 정보 수정 / 방 이동"):
                        with st.form(key=f"edit_{u['user_id']}"):
                            en = st.text_input("이름", value=u['name'])
                            ep = st.text_input("연락처", value=u['phone'])
                            ec = st.text_input("차량번호", value=u['car_number'])
                            er = st.text_input("방 번호 (변경 시 자동이동)", value=u['room_number'])
                            if st.form_submit_button("수정 저장"):
                                idx = df_all[df_all['user_id'] == u['user_id']].index
                                df_all.loc[idx, ['name', 'phone', 'car_number', 'room_number']] = [en, ep, ec, er]
                                if update_gsheet(df_all): st.rerun()
            
            if is_admin and len(users) < 4:
                st.divider()
                with st.expander("➕ 신규 입실 등록"):
                    with st.form("add_user_form"):
                        nn = st.text_input("성함*")
                        ng = st.selectbox("성별", ["남", "여"])
                        np = st.text_input("연락처*")
                        nc = st.text_input("차량번호")
                        ni = st.date_input("입실일", value=date.today())
                        if st.form_submit_button("입실 저장"):
                            if nn and np:
                                last_id = pd.to_numeric(df_all["user_id"], errors='coerce').max()
                                new_id = int(last_id + 1) if not pd.isna(last_id) else 1
                                new_row = {
                                    "user_id": new_id, "room_number": str(sel_room), "name": nn,
                                    "gender": ng, "phone": np, "car_number": nc, "check_in": ni.strftime('%Y-%m-%d'),
                                    "check_out": "", "status": "occupied", "is_active": 1
                                }
                                df_new = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
                                if update_gsheet(df_new): st.rerun()
                            else:
                                st.warning("필수 항목을 입력하세요.")
        else:
            st.info("👈 왼쪽 도면에서 방 번호를 클릭하세요.")

elif selected == "전체 명단":
    st.subheader("📋 현재 거주자 명단")
    st.dataframe(df_active, use_container_width=True)

elif selected == "퇴실 히스토리":
    st.subheader("📚 과거 퇴실자 기록")
    st.dataframe(df_all[df_all["is_active"] == 0], use_container_width=True)
