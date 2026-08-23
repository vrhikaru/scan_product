import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import json
import time
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 0. 圖片壓字處理功能
# ==========================================
def add_text_to_image(base_img, brand, style, gender, size):
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    font_size = int(img.width * 0.08) 
    
    try:
        font = ImageFont.truetype("font.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        
    text1 = f"{brand}"
    text2 = f"{style} {gender} {size}"
    
    x = int(img.width * 0.1)
    y = int(img.height * 0.75)
    line_spacing = font_size + 15
    
    def draw_text_with_outline(text, pos_x, pos_y):
        outline_color = "black"
        thickness = 3
        for adj_x in range(-thickness, thickness+1):
            for adj_y in range(-thickness, thickness+1):
                draw.text((pos_x + adj_x, pos_y + adj_y), text, font=font, fill=outline_color)
        draw.text((pos_x, pos_y), text, font=font, fill="white")
        
    draw_text_with_outline(text1, x, y)
    draw_text_with_outline(text2, x, y + line_spacing)
    return img

# ==========================================
# 1. API 服務初始化與功能函式
# ==========================================
def get_drive_service():
    key_dict = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        key_dict, scopes=['https://www.googleapis.com/auth/drive.file']
    )
    return build('drive', 'v3', credentials=credentials)

def upload_to_drive(image_bytes, filename):
    try:
        service = get_drive_service()
        folder_id = st.secrets["drive_folder_id"]
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_bytes, mimetype='image/jpeg', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        st.error(f"上傳硬碟失敗: {e}")
        return None, None

def analyze_clothing_with_gemini(image):
    client = genai.Client(api_key=st.secrets["gemini_api_key"])
    prompt = """
    請分析這張衣服照片，並以繁體中文 JSON 格式回傳以下欄位：
    - brand: 品牌名稱 (若看不出來則填 "未知")
    - style: 服飾樣式 (如：風衣、短袖T恤等)
    - color: 主要顏色
    - gender: 適合性別 (男、女、或 中性)
    - size: 尺寸標籤 (若有拍到標籤請填寫如 S/M/L/XL，若無請填 "未標示")

    請僅回傳純 JSON 格式。
    """
    
    # 👇 將模型名稱更新為最新的 Gemini 3.7 Flash
    response = client.models.generate_content(
        model='gemini-3.7-flash', 
        contents=[image, prompt]
    )
    
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)

# ==========================================
# 2. 狀態管理初始化 (核心邏輯)
# ==========================================
if 'step' not in st.session_state:
    st.session_state.step = 1 # 預設從步驟 1 開始
if 'image_data' not in st.session_state:
    st.session_state.image_data = None
if 'tags' not in st.session_state:
    st.session_state.tags = {}

# ==========================================
# 3. 網頁前端介面與流程控制
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")

# --- 步驟 1：拍照 ---
if st.session_state.step == 1:
    st.info("步驟 1/3：請拍攝衣物照片")
    photo = st.camera_input("拍照辨識衣服")
    
    if photo is not None:
        # 將照片存入暫存，並前往步驟 2
        st.session_state.image_data = photo.getvalue()
        st.session_state.step = 2
        st.rerun() # 強制刷新畫面，隱藏相機

# --- 步驟 2：AI 分析 ---
elif st.session_state.step == 2:
    st.info("步驟 2/3：確認照片並進行分析")
    
    # 從暫存讀取照片並顯示
    image = Image.open(io.BytesIO(st.session_state.image_data))
    st.image(image, caption="已拍攝的照片", use_container_width=True)
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📸 重新拍照", use_container_width=True):
            st.session_state.step = 1
            st.rerun()
            
    with col2:
        if st.button("✨ 開始 AI 自動分析", use_container_width=True):
            with st.status("🤖 正在處理照片中...", expanded=True) as status:
                st.write("1. 正在傳送至 Gemini AI...")
                try:
                    st.session_state.tags = analyze_clothing_with_gemini(image)
                    status.update(label="✅ AI 分析成功！", state="complete", expanded=False)
                    time.sleep(1) # 短暫暫停讓使用者看到成功訊息
                    st.session_state.step = 3
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ AI 分析失敗", state="error", expanded=True)
                    st.error("分析發生錯誤：")
                    st.code(str(e))

# --- 步驟 3：微調與上傳 ---
elif st.session_state.step == 3:
    st.info("步驟 3/3：微調標籤並儲存")
    tags = st.session_state.tags
    image = Image.open(io.BytesIO(st.session_state.image_data))
    
    with st.form("schedule_form"):
        st.subheader("確認或微調標籤")
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("品牌", value=tags.get("brand", "未知"))
            gender_options = ["男", "女", "中性"]
            gender_idx = gender_options.index(tags.get("gender")) if tags.get("gender") in gender_options else 2
            gender = st.selectbox("性別", gender_options, index=gender_idx)
        with col2:
            style = st.text_input("樣式", value=tags.get("style", ""))
            size = st.text_input("尺寸", value=tags.get("size", "未標示"))
            
        submit_button = st.form_submit_button("🚀 壓印圖片並存入硬碟", use_container_width=True)
        
        if submit_button:
            with st.spinner("正在合成照片並上傳至雲端..."):
                processed_image = add_text_to_image(image, brand, style, gender, size)
                
                img_byte_arr = io.BytesIO()
                processed_image.save(img_byte_arr, format='JPEG')
                img_byte_arr.seek(0)
                
                filename = f"clothing_tagged_{int(time.time())}.jpg"
                file_id, web_link = upload_to_drive(img_byte_arr, filename)
                
                if file_id:
                    st.session_state.web_link = web_link
                    # 存入另外的變數方便步驟 4 顯示圖片
                    st.session_state.final_image_data = img_byte_arr.getvalue()
                    st.session_state.step = 4
                    st.rerun()

# --- 步驟 4：完成畫面 ---
elif st.session_state.step == 4:
    st.success("🎉 照片已成功壓字並存入 Google 硬碟！")
    
    final_image = Image.open(io.BytesIO(st.session_state.final_image_data))
    st.image(final_image, caption="最終合成照片", use_container_width=True)
    st.write(f"[🔗 點此檢視 Google 硬碟中的照片]({st.session_state.web_link})")
    
    st.divider()
    if st.button("📸 拍下一件衣服", type="primary", use_container_width=True):
        # 清空所有暫存狀態，回到步驟 1
        st.session_state.step = 1
        st.session_state.image_data = None
        st.session_state.tags = {}
        st.rerun()