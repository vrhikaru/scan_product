import streamlit as st
from PIL import Image
import io
import json
import time
from datetime import datetime
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 1. 初始化服務與 API 金鑰
# ==========================================

# 取得 Google Drive 服務物件 (使用你的 GCP Service Account)
def get_drive_service():
    key_dict = json.loads(st.secrets["gcp_service_account"])
    credentials = service_account.Credentials.from_service_account_info(
        key_dict,
        scopes=['https://www.googleapis.com/auth/drive.file']
    )
    return build('drive', 'v3', credentials=credentials)

# 圖片上傳至 Google Drive
def upload_to_drive(image_file, filename):
    try:
        service = get_drive_service()
        folder_id = st.secrets["drive_folder_id"]
        
        file_metadata = {
            'name': filename,
            'parents': [folder_id]
        }
        media = MediaIoBaseUpload(image_file, mimetype='image/jpeg', resumable=True)
        file = service.files().create(body=file_metadata, media_body=media, fields='id, webViewLink').execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        st.error(f"上傳 Google 硬碟失敗: {e}")
        return None, None

# ==========================================
# 2. 真實 AI 視覺辨識 (使用 Google Gemini)
# ==========================================
def analyze_clothing_with_gemini(image):
    """
    呼叫 Gemini 2.5 Flash 模型分析衣服照片，並強制回傳 JSON 格式
    """
    try:
        # 使用設定檔中的 GEMINI_API_KEY 初始化客戶端
        client = genai.Client(api_key=st.secrets["gemini_api_key"])
        
        prompt = """
        請分析這張衣服照片，並以繁體中文 JSON 格式回傳以下欄位：
        - brand: 品牌名稱 (若看不出來則填 "未知")
        - style: 服飾樣式 (如：短袖T恤、牛仔褲、帽T、襯衫等)
        - color: 主要顏色
        - gender: 適合性別 (必須為 "男裝", "女裝", 或 "中性/通用" 其中之一)
        - size: 尺寸標籤 (若有拍到標籤請填寫如 S/M/L/XL，若無請填 "未標示")

        請僅回傳純 JSON 格式，不要加入任何 Markdown 標點或引號以外的字。
        """
        
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )
        
        # 清理並解析回傳的 JSON 資料
        clean_text = response.text.strip().replace('```json', '').replace('```', '')
        result = json.loads(clean_text)
        return result
    except Exception as e:
        st.warning(f"AI 辨識過程發生預期外狀況，載入預設值：{e}")
        return {
            "brand": "未知",
            "style": "上衣/褲款",
            "color": "多色",
            "gender": "中性/通用",
            "size": "未標示"
        }

# ==========================================
# 3. 網頁前端介面
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")
st.write("拍下衣服照片，AI 將自動辨識屬性並建立排程上架資料庫。")

photo = st.camera_input("拍照辨識衣服")

if photo is not None:
    image = Image.open(photo)
    st.image(image, caption="已拍攝的照片", use_column_width=True)
    
    # 觸發 AI 分析與處理
    if st.button("✨ 開始 AI 自動分析"):
        with st.spinner("AI 正在分析衣服屬性..."):
            st.session_state['tags'] = analyze_clothing_with_gemini(image)
            st.session_state['analyzed'] = True

if st.session_state.get('analyzed', False):
    tags = st.session_state['tags']
    st.success("✅ AI 辨識完成！請確認或微調以下內容：")
    
    with st.form("schedule_form"):
        st.subheader("1. 服飾屬性標籤")
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("品牌", value=tags.get("brand", "未知"))
            color = st.text_input("顏色", value=tags.get("color", ""))
            gender_options = ["男裝", "女裝", "中性/通用"]
            gender_idx = gender_options.index(tags.get("gender")) if tags.get("gender") in gender_options else 2
            gender = st.selectbox("性別", gender_options, index=gender_idx)
        with col2:
            style = st.text_input("樣式", value=tags.get("style", ""))
            size = st.text_input("尺寸", value=tags.get("size", "M"))
        
        st.subheader("2. 排程發布設定")
        col_d, col_t = st.columns(2)
        with col_d:
            publish_date = st.date_input("預計上架日期", value=datetime.today())
        with col_t:
            publish_time = st.time_input("預計上架時間", value=datetime.now().time())
            
        submit_button = st.form_submit_button("🚀 確認並存入排程庫")
        
        if submit_button:
            with st.spinner("正在上傳照片並記錄排程..."):
                # 將圖片轉換為 Bytes 並上傳至 Drive
                img_byte_arr = io.BytesIO()
                image.save(img_byte_arr, format='JPEG')
                img_byte_arr.seek(0)
                
                timestamp = int(time.time())
                filename = f"clothing_{timestamp}.jpg"
                file_id, web_link = upload_to_drive(img_byte_arr, filename)
                
                if file_id:
                    scheduled_datetime = f"{publish_date} {publish_time}"
                    st.balloons()
                    st.success("🎉 已成功儲存！")
                    st.json({
                        "狀態": "待上架 (Pending)",
                        "預計發布時間": scheduled_datetime,
                        "品牌": brand,
                        "樣式": style,
                        "顏色": color,
                        "性別": gender,
                        "尺寸": size,
                        "硬碟照片連結": web_link
                    })