import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import json
import time
import os
from datetime import datetime
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
        st.warning("⚠️ 找不到字體檔 (font.ttf)！將使用預設字體，中文可能會顯示為方塊。")
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
# 1. Google Drive 服務初始化
# ==========================================
def get_drive_service():
    key_dict = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        key_dict, scopes=['https://www.googleapis.com/auth/drive.file']
    )
    return build('drive', 'v3', credentials=credentials)

def upload_to_drive(image_file, filename):
    try:
        service = get_drive_service()
        folder_id = st.secrets["drive_folder_id"]
        file_metadata = {'name': filename, 'parents': [folder_id]}
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        st.error(f"上傳硬碟失敗: {e}")
        return None, None

# ==========================================
# 2. 真實 AI 視覺辨識 (移除隱藏錯誤的機制)
# ==========================================
def analyze_clothing_with_gemini(image):
    # 這裡不再使用 try-except 包覆，而是讓錯誤直接傳遞給前端顯示
    client = genai.Client(api_key=st.secrets["gemini_api_key"])
    prompt = """
    請分析這張衣服照片，並以繁體中文 JSON 格式回傳以下欄位：
    - brand: 品牌名稱 (若看不出來則填 "未知")
    - style: 服飾樣式 (如：風衣、短袖T恤等)
    - color: 主要顏色
    - gender: 適合性別 (男、女、或 中性)
    - size: 尺寸標籤 (若有拍到標籤請填寫如 S/M/L/XL，若無請填 "未標示")

    請僅回傳純 JSON 格式，不要加入任何 Markdown 標點或引號以外的字。
    """
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=[image, prompt]
    )
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)

# ==========================================
# 3. 網頁前端介面
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")

photo = st.camera_input("拍照辨識衣服")

if photo is not None:
    image = Image.open(photo)
    st.image(image, caption="原始照片", use_container_width=True)
    
    if st.button("✨ 開始 AI 自動分析"):
        # 使用 st.status 建立帶有詳細步驟的進度動畫
        with st.status("🤖 正在處理照片中...", expanded=True) as status:
            st.write("1. 正在將照片傳送至 Gemini AI...")
            
            try:
                # 嘗試執行分析
                st.session_state['tags'] = analyze_clothing_with_gemini(image)
                st.write("2. 分析完成，正在解析標籤資料...")
                st.session_state['analyzed'] = True
                
                # 成功時更新動畫狀態
                status.update(label="✅ AI 分析成功！", state="complete", expanded=False)
                
            except Exception as e:
                # 失敗時更新動畫狀態，並印出真實錯誤
                status.update(label="❌ AI 分析失敗", state="error", expanded=True)
                st.error("很抱歉，呼叫 AI 時發生了錯誤。請參考下方的系統訊息：")
                st.code(str(e), language="text")
                st.info("💡 提示：請檢查您的 `gemini_api_key` 是否正確填寫、免費額度是否用盡，或是終端機是否有安裝 `google-genai` 套件。")
                st.session_state['analyzed'] = False

# ==========================================
# 4. 顯示與編輯標籤
# ==========================================
if st.session_state.get('analyzed', False):
    tags = st.session_state['tags']
    
    with st.form("schedule_form"):
        st.subheader("確認或微調標籤")
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("品牌", value=tags.get("brand", "未知"))
            gender = st.selectbox("性別", ["男", "女", "中性"], index=0)
        with col2:
            style = st.text_input("樣式", value=tags.get("style", ""))
            size = st.text_input("尺寸", value=tags.get("size", "L"))
            
        submit_button = st.form_submit_button("🚀 壓印圖片並存入硬碟")
        
        if submit_button:
            with st.spinner("正在將資訊壓印到照片上並上傳..."):
                processed_image = add_text_to_image(image, brand, style, gender, size)
                st.image(processed_image, caption="最終合成照片", use_container_width=True)
                
                img_byte_arr = io.BytesIO()
                processed_image.save(img_byte_arr, format='JPEG')
                img_byte_arr.seek(0)
                
                filename = f"clothing_tagged_{int(time.time())}.jpg"
                file_id, web_link = upload_to_drive(img_byte_arr, filename)
                
                if file_id:
                    st.success("🎉 合成照片已成功存入 Google 硬碟！")
                    st.write(f"[點此檢視上傳的照片]({web_link})")