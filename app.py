import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import json
import time
import os
from google import genai
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload

# ==========================================
# 0. 圖片壓字處理功能
# ==========================================
def add_text_to_image(base_img, brand, style, color, gender, size):
    img = base_img.copy()
    draw = ImageDraw.Draw(img)
    font_size = int(img.width * 0.08) 
    try:
        font = ImageFont.truetype("font.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()
        
    text1 = f"{brand}"
    text2 = f"{style} {color} {gender} {size}"
    
    x = int(img.width * 0.1)
    y = int(img.height * 0.75)
    line_spacing = font_size + 15
    
    def draw_text_with_outline(text, pos_x, pos_y):
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((pos_x + adj_x, pos_y + adj_y), text, font=font, fill="black")
        draw.text((pos_x, pos_y), text, font=font, fill="white")
        
    draw_text_with_outline(text1, x, y)
    draw_text_with_outline(text2, x, y + line_spacing)
    return img

# ==========================================
# 1. API 服務初始化與功能函式
# ==========================================
def get_drive_service():
    gcp_secret = st.secrets["gcp_service_account"]
    if isinstance(gcp_secret, str):
        key_dict = json.loads(gcp_secret)
    else:
        key_dict = dict(gcp_secret)
        
    if "private_key" in key_dict:
        key_dict["private_key"] = key_dict["private_key"].replace("\\n", "\n")
        
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
        file = service.files().create(
            body=file_metadata, 
            media_body=media, 
            fields='id, webViewLink',
            supportsAllDrives=True
        ).execute()
        return file.get('id'), file.get('webViewLink')
    except Exception as e:
        # 這裡把原本的 st.error 改成回傳錯誤訊息，讓流程繼續往下走
        print(f"上傳硬碟失敗: {e}")
        return None, None

def analyze_clothing_with_gemini(main_image, label_image=None):
    client = genai.Client(api_key=st.secrets["gemini_api_key"])
    prompt = """
    請分析提供的衣服照片（可能包含主照片與標籤特寫），並以繁體中文 JSON 格式回傳以下欄位：
    - brand: 品牌名稱 (若有標籤照片請優先參考，若無則填 "未知")
    - style: 服飾樣式 (如：風衣、短袖T恤等)
    - color: 主要顏色
    - gender: 適合性別 (男、女、或 中性)
    - size: 尺寸標籤 (若有標籤照片請優先參考如 S/M/L/XL，若無請填 "未標示")

    請僅回傳純 JSON 格式。
    """
    
    contents_list = [main_image]
    if label_image:
        contents_list.append(label_image)
    contents_list.append(prompt)

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=contents_list
    )
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)

# ==========================================
# 2. 狀態管理初始化
# ==========================================
if 'step' not in st.session_state:
    st.session_state.step = 1
if 'image_data' not in st.session_state:
    st.session_state.image_data = None
if 'label_image_data' not in st.session_state:
    st.session_state.label_image_data = None
if 'tags' not in st.session_state:
    st.session_state.tags = {}

# ==========================================
# 3. 網頁前端介面與流程控制
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")

# --- 步驟 1：拍攝主照片 ---
if st.session_state.step == 1:
    st.info("步驟 1/3：請拍攝衣服全貌照片")
    photo = st.camera_input("拍攝衣服全貌")
    
    if photo is not None:
        st.session_state.image_data = photo.getvalue()
        st.session_state.step = 2
        st.rerun()

# --- 步驟 2：補拍標籤與 AI 分析 ---
elif st.session_state.step == 2:
    st.info("步驟 2/3：確認主照片，並可選填補拍衣標")
    
    main_image = Image.open(io.BytesIO(st.session_state.image_data))
    st.image(main_image, caption="已拍攝的主照片", use_container_width=True)
    
    label_photo = st.camera_input("📸 補拍衣服內標 (選填)")
    if label_photo is not None:
        st.session_state.label_image_data = label_photo.getvalue()
        st.success("✅ 已記錄標籤照片！")
    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔄 重新拍攝主照片", use_container_width=True):
            st.session_state.step = 1
            st.session_state.label_image_data = None
            st.rerun()
            
    with col2:
        if st.button("✨ 開始 AI 自動分析", use_container_width=True):
            with st.status("🤖 正在綜合分析照片中...", expanded=True) as status:
                st.write("1. 正在傳送影像資料至 Gemini AI...")
                try:
                    label_image = None
                    if st.session_state.label_image_data:
                        label_image = Image.open(io.BytesIO(st.session_state.label_image_data))
                    
                    st.session_state.tags = analyze_clothing_with_gemini(main_image, label_image)
                    status.update(label="✅ AI 分析成功！", state="complete", expanded=False)
                    time.sleep(1)
                    st.session_state.step = 3
                    st.rerun()
                except Exception as e:
                    status.update(label="❌ AI 分析失敗", state="error", expanded=True)
                    st.error("分析發生錯誤：")
                    st.code(str(e))

# --- 步驟 3：微調與存檔 ---
elif st.session_state.step == 3:
    st.info("步驟 3/3：微調標籤並儲存")
    tags = st.session_state.tags
    main_image = Image.open(io.BytesIO(st.session_state.image_data))
    
    with st.form("schedule_form"):
        st.subheader("確認或微調標籤")
        col1, col2 = st.columns(2)
        with col1:
            brand = st.text_input("品牌", value=tags.get("brand", "未知"))
            color = st.text_input("顏色", value=tags.get("color", "")) 
            gender_options = ["男", "女", "中性"]
            gender_idx = gender_options.index(tags.get("gender")) if tags.get("gender") in gender_options else 2
            gender = st.selectbox("性別", gender_options, index=gender_idx)
        with col2:
            style = st.text_input("樣式", value=tags.get("style", ""))
            size = st.text_input("尺寸", value=tags.get("size", "未標示"))
            
        submit_button = st.form_submit_button("🚀 處理照片並存檔", use_container_width=True)
        
        if submit_button:
            with st.spinner("正在合成照片並嘗試上傳..."):
                processed_image = add_text_to_image(main_image, brand, style, color, gender, size)
                
                # 轉為 bytes 供上傳與下載使用
                img_byte_arr = io.BytesIO()
                processed_image.save(img_byte_arr, format='JPEG')
                img_data = img_byte_arr.getvalue()
                
                filename = f"clothing_tagged_{int(time.time())}.jpg"
                
                # --- 新增：強制存入本地端資料夾 ---
                local_dir = "local_saves"
                os.makedirs(local_dir, exist_ok=True) # 如果資料夾不存在則自動建立
                local_path = os.path.join(local_dir, filename)
                processed_image.save(local_path, format='JPEG')
                st.session_state.local_path = local_path
                
                # --- 嘗試上傳雲端 ---
                img_byte_arr.seek(0)
                file_id, web_link = upload_to_drive(img_byte_arr, filename)
                
                # 將結果存入狀態管理
                st.session_state.web_link = web_link
                st.session_state.final_image_data = img_data
                st.session_state.filename = filename
                st.session_state.step = 4
                st.rerun()

# --- 步驟 4：完成與下載畫面 ---
elif st.session_state.step == 4:
    
    # 判斷雲端是否有成功
    if st.session_state.web_link:
        st.success("🎉 照片已成功壓字並存入 Google 硬碟與本地端！")
        st.write(f"[🔗 點此檢視 Google 硬碟中的照片]({st.session_state.web_link})")
    else:
        st.warning(f"⚠️ Google 硬碟上傳失敗，但照片已安全備份至伺服器本地端資料夾：`{st.session_state.local_path}`")
    
    # 顯示最終結果
    final_image = Image.open(io.BytesIO(st.session_state.final_image_data))
    st.image(final_image, caption="最終合成照片", use_container_width=True)
    
    st.divider()
    
    # 新增：直接下載照片的按鈕
    st.download_button(
        label="💾 下載這張照片到手機相簿",
        data=st.session_state.final_image_data,
        file_name=st.session_state.filename,
        mime="image/jpeg",
        use_container_width=True
    )
    
    if st.button("📸 拍下一件衣服", type="primary", use_container_width=True):
        st.session_state.step = 1
        st.session_state.image_data = None
        st.session_state.label_image_data = None
        st.session_state.tags = {}
        st.rerun()