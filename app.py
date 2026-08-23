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
    
    margin_x = int(img.width * 0.1)
    max_text_width = img.width - (margin_x * 2)
    
    def wrap_text(text, font, max_width):
        lines = []
        current_line = ""
        for char in text:
            test_line = current_line + char
            length = draw.textlength(test_line, font=font)
            
            if length <= max_width:
                current_line = test_line
            else:
                lines.append(current_line)
                current_line = char
        if current_line:
            lines.append(current_line)
        return lines

    wrapped_lines = wrap_text(text1, font, max_text_width) + wrap_text(text2, font, max_text_width)
    
    start_y = int(img.height * 0.70)
    line_spacing = font_size + int(font_size * 0.2) 
    
    def draw_text_with_outline(text, pos_x, pos_y):
        for adj_x in range(-3, 4):
            for adj_y in range(-3, 4):
                draw.text((pos_x + adj_x, pos_y + adj_y), text, font=font, fill="black")
        draw.text((pos_x, pos_y), text, font=font, fill="white")
        
    current_y = start_y
    for line in wrapped_lines:
        draw_text_with_outline(line, margin_x, current_y)
        current_y += line_spacing
        
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
if 'preview_image_data' not in st.session_state:
    st.session_state.preview_image_data = None

# ==========================================
# 3. 網頁前端介面與流程控制
# ==========================================
st.set_page_config(page_title="智慧衣物排程標記系統", layout="centered")
st.title("👕 智慧衣物排程標記系統")

# --- 步驟 1：拍攝主照片 ---
if st.session_state.step == 1:
    st.info("步驟 1/4：請拍攝衣服全貌照片")
    photo = st.camera_input("拍攝衣服全貌")
    st.caption("💡 提示：如需使用手機後鏡頭，請點擊相機畫面角落的切換圖示。")
    
    if photo is not None:
        st.session_state.image_data = photo.getvalue()
        st.session_state.step = 2
        st.rerun()

# --- 步驟 2：補拍標籤與 AI 分析 ---
elif st.session_state.step == 2:
    st.info("步驟 2/4：確認主照片，並可選填補拍衣標")
    
    main_image = Image.open(io.BytesIO(st.session_state.image_data))
    st.image(main_image, caption="已拍攝的主照片", use_container_width=True)
    
    label_photo = st.camera_input("📸 補拍衣服內標 (選填)")
    if label_photo is not None:
        st.session_state.label_image_data = label_photo.getvalue()
        st.success("✅ 已記錄標籤照片！")
    
    st.divider()
    
    if st.button("✨ 開始 AI 自動分析", type="primary", use_container_width=True):
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
                
    st.write("") 
    
    if st.button("🔄 不滿意，重新拍攝主照片", use_container_width=True):
        st.session_state.step = 1
        st.session_state.label_image_data = None
        st.rerun()

# --- 步驟 3：微調標籤並產生預覽 ---
elif st.session_state.step == 3:
    st.info("步驟 3/4：微調標籤")
    tags = st.session_state.tags
    main_image = Image.open(io.BytesIO(st.session_state.image_data))
    
    with st.form("schedule_form"):
        st.subheader("請確認或修改標籤內容")
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
            
        preview_button = st.form_submit_button("👀 預覽合成結果", type="primary", use_container_width=True)
        
        if preview_button:
            st.session_state.tags.update({
                "brand": brand, "color": color, "gender": gender, 
                "style": style, "size": size
            })
            
            processed_image = add_text_to_image(main_image, brand, style, color, gender, size)
            img_byte_arr = io.BytesIO()
            processed_image.save(img_byte_arr, format='JPEG')
            st.session_state.preview_image_data = img_byte_arr.getvalue()
            
            st.session_state.step = 4
            st.rerun()

# --- 步驟 4：預覽與確認存檔 ---
elif st.session_state.step == 4:
    st.info("步驟 4/4：預覽確認")
    
    preview_img = Image.open(io.BytesIO(st.session_state.preview_image_data))
    st.image(preview_img, caption="照片預覽 (若確認無誤請點擊下方儲存)", use_container_width=True)
    
    st.divider()
    
    if st.button("🚀 確認無誤，儲存並上傳", type="primary", use_container_width=True):
        with st.spinner("正在上傳至雲端與本地備份..."):
            filename = f"clothing_tagged_{int(time.time())}.jpg"
            
            local_dir = "local_saves"
            os.makedirs(local_dir, exist_ok=True)
            local_path = os.path.join(local_dir, filename)
            with open(local_path, "wb") as f:
                f.write(st.session_state.preview_image_data)
            st.session_state.local_path = local_path
            st.session_state.filename = filename
            
            img_byte_arr = io.BytesIO(st.session_state.preview_image_data)
            file_id, web_link = upload_to_drive(img_byte_arr, filename)
            
            st.session_state.web_link = web_link
            st.session_state.step = 5
            st.rerun()
            
    st.write("") 
            
    if st.button("✏️ 返回修改文字", use_container_width=True):
        st.session_state.step = 3
        st.rerun()

# --- 步驟 5：完成與下載畫面 ---
elif st.session_state.step == 5:
    if st.session_state.web_link:
        st.success("🎉 照片已成功存入 Google 硬碟與本地端！")
        st.write(f"[🔗 點此檢視 Google 硬碟中的照片]({st.session_state.web_link})")
    else:
        st.warning(f"⚠️ Google 硬碟上傳失敗，但照片已安全備份至本地端資料夾：`{st.session_state.local_path}`")
    
    final_image = Image.open(io.BytesIO(st.session_state.preview_image_data))
    st.image(final_image, caption="最終完成照片", use_container_width=True)
    
    st.divider()
    
    st.download_button(
        label="💾 下載這張照片到手機相簿",
        data=st.session_state.preview_image_data,
        file_name=st.session_state.filename,
        mime="image/jpeg",
        use_container_width=True
    )
    
    if st.button("📸 拍下一件衣服", type="primary", use_container_width=True):
        st.session_state.step = 1
        st.session_state.image_data = None
        st.session_state.label_image_data = None
        st.session_state.tags = {}
        st.session_state.preview_image_data = None
        st.rerun()