import streamlit as st
import pandas as pd
from datetime import date, datetime
import uuid
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates
from streamlit_option_menu import option_menu
from streamlit_gsheets import GSheetsConnection

# 1. 디자인 및 세션 설정
st.set_page_config(layout="wide", page_title="인력개발원 숙소동 v2.0 (GS)")

if "room" not in st.session_state:
    st.session_state["room"] = None

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stMetric { background-color: #ffffff; padding: 15px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); border: 1px solid #eee; }
    .user-card { 
        background-color: white; padding: 20px; border-radius: 12px; 
        box-shadow: 0 4px 6px rgba(0,0,0,0.07); margin-bottom: 15px;
        border-left: 6px solid #228be6;
    }
    .status-badge { padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; color: white; }
    </style>
    """, unsafe_allow_html=True)

# 2. 구글 시트 연결 설정
conn = st.connection("gsheets", type=GSheetsConnection)

def load_data():
    return conn.read(
        spreadsheet="https://docs.google.com/spreadsheets/d/1C3-W6MIZMptgND9e8Zms2orhEYfFPCls3vC3FuxfC30/edit#gid=0",
        worksheet="room_users",
        ttl="0s"
def update_gsheet(df):
    conn.update(worksheet="room_users", data=df)
    st.cache_data.clear()

# 3. 데이터 로드
try:
    df_all = load_data()
except:
    # 시트가 비어있을 경우를 대비한 기본 틀
    df_all = pd.DataFrame(columns=["user_id", "room_number", "name", "gender", "phone", "car_number", "check_in", "check_out", "status", "is_active"])

# 데이터 타입 보정
df_all['is_active'] = pd.to_numeric(df_all['is_active'], errors='coerce').fillna(1)
df_active = df_all[df_all["is_active"] == 1]

# 4. 사이드바 및 관리자 인증
with st.sidebar:
    st.title("🏢 숙소동 관리 (영구저장)")
    selected = option_menu(None, ["실시간 도면", "전체 명단", "퇴실 히스토리"], 
                          icons=["map", "list-task", "archive"], default_index=0)
    search_q = st.text_input("🔍 통합 검색", placeholder="이름/방/번호")
    st.divider()
    password = st.text_input("관리자 비밀번호", type="password")
    is_admin = (password == "1234")

if search_q:
    df_active = df_active[df_active["name"].astype(str).str.contains(search_q, na=False) | 
                          df_active["room_number"].astype(str).str.contains(search_q, na=False) |
                          df_active["phone"].astype(str).str.contains(search_q, na=False)]

# --- [메뉴 1: 실시간 도면] ---
if selected == "실시간 도면":
    # 요약 메트릭
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
        import os, json
        if os.path.exists("dorm_map.png"):
            img = Image.open("dorm_map.png")
            target_width = 1200  
            ratio = target_width / 800     
            img = img.resize((target_width, int(img.size[1]*target_width/img.size[0])))
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype("malgun.ttf", int(14 * ratio))
            except: font = ImageFont.load_default()

            ROOM_COORDS = json.load(open("room_coords.json")) if os.path.exists("room_coords.json") else {}

            for room, (orig_x, orig_y) in ROOM_COORDS.items():
                x, y = orig_x * ratio, orig_y * ratio
                users = room_map.get(room, [])
                color = "#fa5252" if users else "#40c057"
                
                r_size = 13 * ratio
                draw.ellipse((x-r_size, y-r_size, x+r_size, y+r_size), fill=color, outline="white", width=2)
                
                # 방 번호 위치 로직 유지
                room_int = int(room) if str(room).isdigit() else 0
                if 511 <= room_int <= 520:
                    draw.text((x - (15 * ratio), y - (32 * ratio)), str(room), fill="#333333", font=font)
                elif (501 <= room_int <= 510) or (1 <= (room_int % 100) <= 10):
                    draw.text((x + r_size + (5 * ratio), y - (8 * ratio)), str(room), fill="#333333", font=font)
                else:
                    draw.text((x - (10 * ratio), y - (28 * ratio)), str(room), fill="#333333", font=font) 

            coords = streamlit_image_coordinates(img, key="dorm_map_gs")
            if coords:
                new_room = None
                for r, (ox, oy) in ROOM_COORDS.items():
                    if abs(coords["x"]-(ox*ratio)) < (15*ratio) and abs(coords["y"]-(oy*ratio)) < (15*ratio):
                        new_room = r; break
                if new_room and new_room != st.session_state["room"]:
                    st.session_state["room"] = new_room; st.rerun()

    with right:
        sel_room = st.session_state.get("room")
        if sel_room:
            st.subheader(f"🏠 {sel_room}호")
            users = room_map.get(sel_room, [])
            for u in users:
                st.markdown(f"""
                <div class="user-card">
                    <h4 style="margin: 0;">{u['name']} ({u['gender']})</h4>
                    <p style="margin:5px 0;">📞 {u['phone']} | 🚗 {u['car_number']}</p>
                    <p style="margin:0; font-size:0.85em; color:gray;">📅 입실: {u['check_in']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_admin:
                    with st.expander("🚪 퇴실 처리"):
                        out_date = st.date_input("퇴실 날짜", value=date.today(), key=f"out_d_{u['user_id']}")
                        if st.button("퇴실 확정", key=f"btn_out_{u['user_id']}", type="primary"):
                            df_all.loc[df_all['user_id'] == u['user_id'], ['is_active', 'check_out']] = [0, str(out_date)]
                            update_gsheet(df_all); st.rerun()
            
            if is_admin and len(users) < 4:
                with st.expander("➕ 신규 입실 등록"):
                    with st.form("add_user_gs"):
                        nn, ng = st.text_input("성함*"), st.selectbox("성별", ["남", "여"])
                        np, nc = st.text_input("연락처*"), st.text_input("차량번호")
                        ni = st.date_input("입실일", value=date.today())
                        if st.form_submit_button("등록"):
                            new_data = pd.DataFrame([{
                                "user_id": str(uuid.uuid4()), "room_number": sel_room, "name": nn,
                                "gender": ng, "phone": np, "car_number": nc, "check_in": str(ni),
                                "check_out": "", "status": "occupied", "is_active": 1
                            }])
                            update_gsheet(pd.concat([df_all, new_data], ignore_index=True))
                            st.rerun()
        else:
            st.info("👈 도면에서 방을 클릭하세요.")

elif selected == "전체 명단":
    st.dataframe(df_active, use_container_width=True)

elif selected == "퇴실 히스토리":
    st.dataframe(df_all[df_all["is_active"] == 0], use_container_width=True)
