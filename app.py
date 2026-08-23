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
    """
    將文字資訊壓印到圖片的左下角，並加上黑色描邊確保文字清晰
    """
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    
    # 動態計算字體大小 (依圖片寬度的 8%)
    font_size = int(img.width * 0.08) 
    
    # 載入中文字體 (需確認專案資料夾內有 font.ttf)
    try:
        font = ImageFont.truetype("font.ttf", font_size)
    except IOError:
        st.warning("⚠️ 找不到字體檔 (font.ttf)！將使用預設字體，中文可能會顯示為方塊。請記得放入字體檔。")
        font = ImageFont.load_default()
        
    text1 = f"{brand}"
    text2 = f"{style} {gender} {size}"
    
    # 設定文字起始位置 (左下角)
    x = int(img.width * 0.1)
    y = int(img.height * 0.75)
    line_spacing = font_size + 15
    
    # 建立描邊文字的副程式
    def draw_text_with_outline(text, pos_x, pos_y):
        outline_color = "black"
        thickness = 3
        # 畫周圍的黑色描邊
        for adj_x in range(-thickness, thickness+1):
            for adj_y in range(-thickness, thickness+1):
                draw.text((pos_x + adj_x, pos_y + adj_y), text, font=font, fill=outline_color)
        # 畫中間的白色主文字
        draw.text((pos_x, pos_y), text, font=font, fill="white")
        
    # 將兩行文字畫上圖片
    draw_text_with_outline(text1, x, y)
    draw_text_with_outline(text2, x, y + line_spacing)
    
    return img

# ==========================================
# 1. Google Drive 與 Gemini API 初始化
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

def analyze_clothing_with_gemini(image):
    try:
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
    except Exception as e:
        st.warning(f"AI 辨識異常：{e}")
        return {"brand": "未知", "style": "服飾", "color": "", "gender": "中性", "size": "未標示"}

# ==========================================
# 2. 網頁前端介面
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")

photo = st.camera_input("拍照辨識衣服")

if photo is not None:
    image = Image.open(photo)
    st.image(image, caption="原始照片", use_container_width=True)
    
    if st.button("✨ 開始 AI 自動分析"):
        with st.spinner("AI 正在分析衣服屬性..."):
            st.session_state['tags'] = analyze_clothing_with_gemini(image)
            st.session_state['analyzed'] = True

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
                # 1. 呼叫我們寫好的壓字功能
                processed_image = add_text_to_image(image, brand, style, gender, size)
                
                # 2. 顯示處理好的合成圖片給你看
                st.image(processed_image, caption="最終合成照片", use_container_width=True)
                
                # 3. 將合成好的圖片上傳 Google Drive
                img_byte_arr = io.BytesIO()
                processed_image.save(img_byte_arr, format='JPEG')
                img_byte_arr.seek(0)
                
                filename = f"clothing_tagged_{int(time.time())}.jpg"
                file_id, web_link = upload_to_drive(img_byte_arr, filename)
                
                if file_id:
                    st.success("🎉 合成照片已成功存入 Google 硬碟！")
                    st.write(f"[點此檢視上傳的照片]({web_link})")