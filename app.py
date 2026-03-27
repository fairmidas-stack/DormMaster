import streamlit as st
import pandas as pd
from datetime import date
import uuid
from PIL import Image, ImageDraw, ImageFont
from streamlit_image_coordinates import streamlit_image_coordinates
from streamlit_option_menu import option_menu
from streamlit_gsheets import GSheetsConnection
import streamlit as st
import pandas as pd
import gspread # 새로 고용한 구글 공식 심부름꾼

# -----------------------------------------------------
# 1. VIP 전용 구글 시트 직접 연결 함수
# -----------------------------------------------------
def get_gspread_client():
    # Secrets 보관함에 있는 모든 열쇠 정보를 통째로 꺼내서 딕셔너리로 만듭니다.
    creds_dict = dict(st.secrets["connections"]["gsheets"])
    
    # 구글 공식 라이브러리에게 이 열쇠를 주고 "로그인해!" 라고 명령합니다.
    gc = gspread.service_account_from_dict(creds_dict)
    return gc

# -----------------------------------------------------
# 2. 데이터 불러오기
# -----------------------------------------------------
def load_data():
    gc = get_gspread_client() # 로그인된 상태 가져오기
    
    # Secrets에 있는 시트 ID로 문서 열기
    doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
    worksheet = doc.worksheet("room_users") # 탭 이름
    
    # 데이터를 싹 다 긁어와서 표(DataFrame)로 변환
    data = worksheet.get_all_records()
    return pd.DataFrame(data)

# -----------------------------------------------------
# 3. 데이터 저장하기 (CRUD 중 쓰기 권한)
# -----------------------------------------------------
def update_gsheet(df):
    try:
        gc = get_gspread_client() # 로그인된 상태 가져오기
        doc = gc.open_by_key(st.secrets["connections"]["gsheets"]["spreadsheet"])
        worksheet = doc.worksheet("room_users")
        
        # 기존 시트의 내용을 깨끗하게 지웁니다.
        worksheet.clear()
        
        # 새로운 표(df)의 제목줄과 데이터를 구글 시트에 한 번에 덮어씁니다.
        worksheet.update([df.columns.values.tolist()] + df.values.tolist())
        
        st.cache_data.clear() # 스트림릿 캐시 새로고침
        return True
    except Exception as e:
        # 만약 여기서도 에러가 나면, 진짜 구체적인 이유를 화면에 띄워줍니다.
        st.error(f"⚠️ 저장 실패 상세 원인: {e}")
        return False
        
# 3. 데이터 로드 및 전처리
try:
    df_all = load_data()
    # 데이터가 아예 없을 경우 대비
    if df_all is None or df_all.empty:
        df_all = pd.DataFrame(columns=["user_id", "room_number", "name", "gender", "phone", "car_number", "check_in", "check_out", "status", "is_active"])
except:
    df_all = pd.DataFrame(columns=["user_id", "room_number", "name", "gender", "phone", "car_number", "check_in", "check_out", "status", "is_active"])

# 데이터 타입 보정 (문자열로 들어온 숫자를 처리)
df_all['is_active'] = pd.to_numeric(df_all['is_active'], errors='coerce').fillna(1)
df_active = df_all[df_all["is_active"] == 1]

# 4. 사이드바 구성
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
            target_width = 1200  
            ratio = target_width / 800     
            img = img.resize((target_width, int(img.size[1]*target_width/img.size[0])))
            draw = ImageDraw.Draw(img)
            try: font = ImageFont.truetype("malgun.ttf", int(14 * ratio))
            except: font = ImageFont.load_default()

            ROOM_COORDS = json.load(open("room_coords.json")) if os.path.exists("room_coords.json") else {}

            for room, (orig_x, orig_y) in ROOM_COORDS.items():
                x, y = orig_x * ratio, orig_y * ratio
                users = room_map.get(str(room), [])
                color = "#fa5252" if users else "#40c057" # 사람이 있으면 빨간색, 없으면 초록색
                
                r_size = 13 * ratio
                draw.ellipse((x-r_size, y-r_size, x+r_size, y+r_size), fill=color, outline="white", width=2)
                
                # 방 번호 텍스트 배치
                room_int = int(room) if str(room).isdigit() else 0
                if 511 <= room_int <= 520:
                    draw.text((x - (15 * ratio), y - (32 * ratio)), str(room), fill="#333333", font=font)
                elif (501 <= room_int <= 510) or (1 <= (room_int % 100) <= 10):
                    draw.text((x + r_size + (5 * ratio), y - (8 * ratio)), str(room), fill="#333333", font=font)
                else:
                    draw.text((x - (10 * ratio), y - (28 * ratio)), str(room), fill="#333333", font=font) 

            coords = streamlit_image_coordinates(img, key="dorm_map_final")
            if coords:
                new_room = None
                for r, (ox, oy) in ROOM_COORDS.items():
                    if abs(coords["x"]-(ox*ratio)) < (20*ratio) and abs(coords["y"]-(oy*ratio)) < (20*ratio):
                        new_room = r; break
                if new_room and new_room != st.session_state["room"]:
                    st.session_state["room"] = new_room; st.rerun()

    with right:
        sel_room = st.session_state.get("room")
        if sel_room:
            st.subheader(f"🏠 {sel_room}호 정보")
            users = room_map.get(str(sel_room), [])
            
            if not users:
                st.write("현재 빈 방입니다.")
            
            for u in users:
                st.markdown(f"""
                <div class="user-card">
                    <h4 style="margin: 0;">{u['name']} ({u['gender']})</h4>
                    <p style="margin:5px 0;">📞 {u['phone']} | 🚗 {u['car_number']}</p>
                    <p style="margin:0; font-size:0.85em; color:gray;">📅 입실: {u['check_in']}</p>
                </div>
                """, unsafe_allow_html=True)
                
                if is_admin:
                    with st.expander(f"🚪 {u['name']}님 퇴실 처리"):
                        if st.button("퇴실 확정", key=f"btn_out_{u['user_id']}", type="primary"):
                            df_all.loc[df_all['user_id'] == u['user_id'], ['is_active', 'check_out']] = [0, date.today().strftime('%Y-%m-%d')]
                            if update_gsheet(df_all):
                                st.rerun()
            
            if is_admin and len(users) < 4:
                st.divider()
                with st.expander("➕ 신규 입실 등록"):
                    with st.form("add_user_gs"):
                        nn = st.text_input("성함*")
                        ng = st.selectbox("성별", ["남", "여"])
                        np = st.text_input("연락처*")
                        nc = st.text_input("차량번호")
                        ni = st.date_input("입실일", value=date.today())
                        
                        if st.form_submit_button("입실 저장"):
                            if nn and np:
                                new_row = {
                                    "user_id": str(uuid.uuid4()), "room_number": str(sel_room), "name": nn,
                                    "gender": ng, "phone": np, "car_number": nc, "check_in": ni.strftime('%Y-%m-%d'),
                                    "check_out": "", "status": "occupied", "is_active": 1
                                }
                                # 기존 데이터와 합쳐서 시트에 업데이트
                                df_new = pd.concat([df_all, pd.DataFrame([new_row])], ignore_index=True)
                                if update_gsheet(df_new):
                                    st.success("데이터가 안전하게 저장되었습니다.")
                                    st.rerun()
                            else:
                                st.warning("성함과 연락처는 필수입니다.")
        else:
            st.info("👈 왼쪽 도면에서 방 번호를 클릭하세요.")

elif selected == "전체 명단":
    st.subheader("📋 현재 거주자 명단")
    st.dataframe(df_active, use_container_width=True)

elif selected == "퇴실 히스토리":
    st.subheader("📚 과거 퇴실자 기록")
    st.dataframe(df_all[df_all["is_active"] == 0], use_container_width=True)
