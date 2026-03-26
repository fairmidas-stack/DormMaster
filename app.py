import streamlit as st
import sqlite3
import pandas as pd
from datetime import date, datetime
import json, os, uuid
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates
from streamlit_option_menu import option_menu

# 1. 디자인 및 세션 설정
st.set_page_config(layout="wide", page_title="인력개발원 숙소동 v1.2")

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
    .status-badge {
        padding: 4px 12px; border-radius: 20px; font-size: 0.85em; font-weight: bold; color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# 2. DB 연결
conn = sqlite3.connect("dormitory.db", check_same_thread=False)
cursor = conn.cursor()

def init_and_migrate_db():
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS room_users (
        user_id TEXT PRIMARY KEY, room_number TEXT, name TEXT, gender TEXT, 
        phone TEXT, car_number TEXT, check_in TEXT, check_out TEXT, 
        re_entry INTEGER, status TEXT, is_active INTEGER DEFAULT 1
    )
    """)
    cursor.execute("PRAGMA table_info(room_users)")
    cols = [c[1] for c in cursor.fetchall()]
    needed = {"gender": "TEXT", "car_number": "TEXT", "status": "TEXT", "is_active": "INTEGER DEFAULT 1"}
    for col, dtype in needed.items():
        if col not in cols:
            cursor.execute(f"ALTER TABLE room_users ADD COLUMN {col} {dtype}")
    conn.commit()

init_and_migrate_db()

# 3. 사이드바 및 관리자 인증
with st.sidebar:
    st.title("🏢 인력개발원 숙소동")
    selected = option_menu(None, ["실시간 도면", "전체 명단", "퇴실 히스토리"], 
                          icons=["map", "list-task", "archive"], default_index=0)
    search_q = st.text_input("🔍 통합 검색", placeholder="이름/방/번호")
    st.divider()
    password = st.text_input("관리자 비밀번호", type="password")
    is_admin = (password == "0416")

# 4. 데이터 로드
df_all = pd.read_sql("SELECT * FROM room_users", conn)
df_active = df_all[df_all["is_active"] == 1]

if is_admin:
    st.sidebar.subheader("📂 엑셀 일괄 업로드")
    uploaded_file = st.sidebar.file_uploader("xlsx 파일 선택", type=["xlsx"])
    if uploaded_file:
        try:
            df_excel = pd.read_excel(uploaded_file)
            for _, row in df_excel.iterrows():
                r_num, p_num = str(row.get("room_number", "")), str(row.get("phone", ""))
                if df_active[(df_active["room_number"]==r_num) & (df_active["phone"]==p_num)].empty:
                    cursor.execute("""
                        INSERT INTO room_users (user_id, room_number, name, gender, phone, car_number, check_in, status, is_active) 
                        VALUES (?,?,?,?,?,?,?,?,1)
                    """, (str(uuid.uuid4()), r_num, str(row.get("name", "")), str(row.get("gender", "남")), 
                          p_num, str(row.get("car_number", "-")), str(row.get("check_in", date.today())), "occupied"))
            conn.commit(); st.rerun()
        except: st.sidebar.error("엑셀 형식을 확인해주세요.")

if search_q:
    df_active = df_active[df_active["name"].str.contains(search_q, na=False) | 
                          df_active["room_number"].str.contains(search_q, na=False) |
                          df_active["phone"].str.contains(search_q, na=False)]

# --- [메뉴 1: 실시간 도면] ---
if selected == "실시간 도면":
    st.write("### 📊 운영 현황 요약")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("현재 거주자", f"{len(df_active)}명")
    m2.metric("점유 중인 방", f"{df_active['room_number'].nunique()}실")
    m3.metric("청소 필요", f"{len(df_active[df_active['status']=='cleaning'])}건")
    m4.metric("오늘 입실", f"{len(df_active[df_active['check_in'].astype(str).str.contains(date.today().strftime('%Y-%m-%d'))])}명")
    
    st.divider()
    room_map = {}
    for r in df_active.to_dict('records'):
        room_map.setdefault(str(r["room_number"]), []).append(r)

    left, right = st.columns([2, 1]) 

    with left:
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
                statuses = [u.get("status") for u in users]
                color = "#40c057" # empty
                if "maintenance" in statuses: color = "#fd7e14"
                elif "cleaning" in statuses: color = "#fab005"
                elif users: color = "#fa5252"
                
                r_size = 13 * ratio
                draw.ellipse((x-r_size, y-r_size, x+r_size, y+r_size), fill=color, outline="white", width=2)
                
                room_int = int(room) if room.isdigit() else 0
                if 511 <= room_int <= 520:
                    draw.text((x - (15 * ratio), y - (32 * ratio)), str(room), fill="#333333", font=font)
                elif (501 <= room_int <= 510) or (1 <= (room_int % 100) <= 10):
                    draw.text((x + r_size + (5 * ratio), y - (8 * ratio)), str(room), fill="#333333", font=font)
                else:
                    draw.text((x - (10 * ratio), y - (28 * ratio)), str(room), fill="#333333", font=font) 
                
                if users:
                    draw.text((x-(4*ratio), y-(8*ratio)), str(len(users)), fill="white", font=font)

            coords = streamlit_image_coordinates(img, key="dorm_map_final")
            if coords:
                new_room = None
                for r, (ox, oy) in ROOM_COORDS.items():
                    rx, ry = ox * ratio, oy * ratio
                    if abs(coords["x"]-rx) < (15 * ratio) and abs(coords["y"]-ry) < (15 * ratio):
                        new_room = r
                        break
                if new_room and new_room != st.session_state["room"]:
                    st.session_state["room"] = new_room
                    st.rerun()
        else:
            st.info("도면 파일이 필요합니다.")

    with right:
        sel_room = st.session_state.get("room")
        if sel_room:
            st.subheader(f"🏠 {sel_room}호")
            users = room_map.get(sel_room, [])
            for u in users:
                badge_color = "#fa5252" if u['status'] == 'occupied' else "#fab005"
                st.markdown(f"""
                <div class="user-card" style="border-left-color: {badge_color}">
                    <span class="status-badge" style="background-color: {badge_color}">{u['status']}</span>
                    <h4 style="margin: 10px 0 5px 0;">{u['name']} ({u['gender'] or '남'})</h4>
                    <p style="margin:0;">📞 {u['phone']} | 🚗 {u['car_number'] or '-'}</p>
                    <p style="margin:0; font-size:0.9em; color:#888;">📅 입실일: {u['check_in']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_admin:
                    c1, c2 = st.columns(2)
                    with c1:
                        with st.expander("📝 수정 (방 이동 포함)"):
                            en = st.text_input("이름", value=u['name'], key=f"en_{u['user_id']}")
                            eg = st.selectbox("성별", ["남", "여"], index=0 if u['gender'] == "남" else 1, key=f"eg_{u['user_id']}")
                            ep = st.text_input("연락처", value=u['phone'], key=f"ep_{u['user_id']}")
                            ec = st.text_input("차량", value=u['car_number'], key=f"ec_{u['user_id']}")
                            try: curr_in = datetime.strptime(str(u['check_in']), '%Y-%m-%d').date()
                            except: curr_in = date.today()
                            ei = st.date_input("입실일 수정", value=curr_in, key=f"ei_{u['user_id']}")
                            st.divider()
                            er = st.text_input("🏠 이동할 방 번호", value=u['room_number'], key=f"er_{u['user_id']}")
                            if st.button("변경사항 저장", key=f"sv_{u['user_id']}", use_container_width=True):
                                cursor.execute("UPDATE room_users SET name=?, gender=?, phone=?, car_number=?, check_in=?, room_number=? WHERE user_id=?", 
                                             (en, eg, ep, ec, str(ei), er, u['user_id']))
                                conn.commit(); st.session_state["room"] = er; st.rerun()
                    with c2:
                        with st.expander("🚪 퇴실"):
                            eo = st.date_input("퇴실 날짜 선택", value=date.today(), key=f"eo_{u['user_id']}")
                            if st.button("퇴실 확정", key=f"out_{u['user_id']}", use_container_width=True, type="primary"):
                                cursor.execute("UPDATE room_users SET is_active=0, check_out=? WHERE user_id=?", 
                                             (str(eo), u['user_id']))
                                conn.commit(); st.rerun()
            
            if is_admin and len(users) < 4:
                st.divider()
                with st.expander("➕ 새 입실자 등록"):
                    with st.form(f"add_form_{sel_room}"):
                        nn, ng = st.text_input("성함*"), st.selectbox("성별", ["남", "여"])
                        np, nc = st.text_input("연락처*"), st.text_input("차량번호")
                        # 🔥 [변경 포인트] 신규 입실 등록 시 입실일 선택 기능 추가
                        ni = st.date_input("입실일 선택", value=date.today())
                        
                        if st.form_submit_button("등록 완료", use_container_width=True):
                            if nn and np:
                                cursor.execute("INSERT INTO room_users (user_id, room_number, name, gender, phone, car_number, check_in, status, is_active) VALUES (?,?,?,?,?,?,?,?,1)",
                                             (str(uuid.uuid4()), sel_room, nn, ng, np, nc, str(ni), "occupied"))
                                conn.commit(); st.rerun()
        else:
            st.info("👈 도면에서 방을 클릭하세요.")

elif selected == "전체 명단":
    st.subheader("📋 현재 거주자 명단")
    st.dataframe(df_active[["room_number", "name", "gender", "phone", "car_number", "check_in", "status"]], use_container_width=True)
elif selected == "퇴실 히스토리":
    st.subheader("📂 퇴실 기록")
    df_h = pd.read_sql("SELECT * FROM room_users WHERE is_active=0", conn)
    st.dataframe(df_h[["room_number", "name", "phone", "check_in", "check_out"]], use_container_width=True)

conn.close()