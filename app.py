import streamlit as st
from PIL import Image, ImageDraw, ImageFont
import io
import json
import time
import base64
from google import genai
import streamlit.components.v1 as components

# ==========================================
# 0. 圖片壓字（壓成機器好讀的三行：名稱 / 性別尺寸 / 庫存N）
# ==========================================
def add_text_to_image(base_img, brand, style, color, gender, size, qty):
    img = base_img.copy().convert("RGB")
    draw = ImageDraw.Draw(img)
    font_size = int(img.width * 0.075)
    try:
        font = ImageFont.truetype("font.ttf", font_size)
    except IOError:
        font = ImageFont.load_default()

    def clean(v, skip):
        v = (v or "").strip()
        return "" if v in skip else v

    line1 = " ".join(x for x in [clean(brand, ["未知"]), clean(style, []), clean(color, [])] if x)
    line2 = " ".join(x for x in [clean(gender, []), clean(size, ["未標示"])] if x)
    line3 = f"庫存 {qty}"                      # 🔑 這行是給 LINE 機器人解析庫存用的固定 token
    raw_lines = [line1, line2, line3]

    margin_x = int(img.width * 0.06)
    max_text_width = img.width - margin_x * 2

    def wrap_text(text):
        if not text:
            return []
        lines, cur = [], ""
        for ch in text:
            if draw.textlength(cur + ch, font=font) <= max_text_width:
                cur += ch
            else:
                lines.append(cur)
                cur = ch
        if cur:
            lines.append(cur)
        return lines

    wrapped = []
    for t in raw_lines:
        wrapped += wrap_text(t)

    line_spacing = font_size + int(font_size * 0.25)
    total_h = line_spacing * len(wrapped)
    start_y = img.height - total_h - int(img.height * 0.04)  # 貼齊底部往上排

    def draw_outline(text, x, y):
        for ax in range(-3, 4):
            for ay in range(-3, 4):
                draw.text((x + ax, y + ay), text, font=font, fill="black")
        draw.text((x, y), text, font=font, fill="white")

    y = start_y
    for line in wrapped:
        draw_outline(line, margin_x, y)
        y += line_spacing
    return img


# ==========================================
# 1. Gemini 分析
# ==========================================
def analyze_clothing(main_image, label_image=None):
    client = genai.Client(api_key=st.secrets["gemini_api_key"])
    prompt = """
請分析提供的衣服照片（可能包含主照片與標籤特寫），並以繁體中文 JSON 格式回傳以下欄位：
- brand: 品牌名稱 (若有標籤照片請優先參考，若無則填 "未知")
- style: 服飾樣式 (如：風衣、短袖T恤等)
- color: 主要顏色
- gender: 適合性別 (男、女、或 中性)
- size: 尺寸標籤 (若有標籤照片請優先參考如 S/M/L/XL，若無請填 "未標示")
請僅回傳純 JSON 格式，不要任何額外文字或 Markdown。
"""
    contents = [main_image]
    if label_image:
        contents.append(label_image)
    contents.append(prompt)

    response = client.models.generate_content(
        model='gemini-3.7-flash',
        contents=contents
    )
    clean_text = response.text.strip().replace('```json', '').replace('```', '')
    return json.loads(clean_text)


# ==========================================
# 2. 分享到 LINE（呼叫手機原生分享選單；不支援時退回下載）
# ==========================================
def line_share_button(image_bytes, filename):
    b64 = base64.b64encode(image_bytes).decode()
    html = f"""
    <div style="text-align:center;font-family:sans-serif;">
      <button id="shareBtn"
        style="width:100%;padding:14px;font-size:17px;border:0;border-radius:10px;
               background:#06C755;color:#fff;font-weight:bold;">
        📲 分享到 LINE 群
      </button>
      <p id="msg" style="color:#888;font-size:13px;margin-top:10px;line-height:1.5;"></p>
    </div>
    <script>
      const b64 = "{b64}";
      function b64ToFile(b64, name) {{
        const bin = atob(b64);
        const arr = new Uint8Array(bin.length);
        for (let i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
        return new File([arr], name, {{ type: 'image/jpeg' }});
      }}
      const btn = document.getElementById('shareBtn');
      const msg = document.getElementById('msg');
      btn.addEventListener('click', async () => {{
        try {{
          const file = b64ToFile(b64, "{filename}");
          if (navigator.canShare && navigator.canShare({{ files: [file] }})) {{
            await navigator.share({{ files: [file], title: '商品上架' }});
            msg.textContent = '已開啟分享選單，請選你的 LINE 群組送出。';
          }} else {{
            msg.textContent = '此瀏覽器不支援直接分享，請改用上方「下載」後，在 LINE 手動附加這張圖。';
          }}
        }} catch (e) {{
          msg.textContent = '已取消或無法分享（可改用下載後手動貼到 LINE）。';
        }}
      }});
    </script>
    """
    components.html(html, height=130)


# ==========================================
# 3. 狀態初始化
# ==========================================
defaults = {
    "step": 1,
    "main_bytes": None,
    "label_bytes": None,
    "qty": 1,
    "tags": {},
    "preview_bytes": None,
    "filename": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ==========================================
# 4. 介面（3 步驟）
# ==========================================
st.set_page_config(page_title="智慧衣物上架", layout="centered")
st.title("👕 智慧衣物上架")

# ---------- 步驟 1：一次拍好（外觀＋衣標）＋數量 ----------
if st.session_state.step == 1:
    st.info("步驟 1／3：拍照（外觀必拍、衣標選拍）")
    st.caption("💡 點下方欄位會叫出手機相機，選「拍照」可用後鏡頭、對焦、放大拍衣標小字，比直接用網頁相機清楚很多。")

    main_file = st.file_uploader("① 衣服外觀（必拍）", type=["jpg", "jpeg", "png"], key="up_main")
    if main_file:
        st.session_state.main_bytes = main_file.getvalue()
        st.image(st.session_state.main_bytes, caption="外觀", use_container_width=True)

    label_file = st.file_uploader("② 衣服內標（選拍，有拍品牌／尺寸會更準）", type=["jpg", "jpeg", "png"], key="up_label")
    if label_file:
        st.session_state.label_bytes = label_file.getvalue()
        st.image(st.session_state.label_bytes, caption="衣標", use_container_width=True)

    st.session_state.qty = st.number_input("數量（庫存）", min_value=1, value=int(st.session_state.qty), step=1)

    disabled = st.session_state.main_bytes is None
    if st.button("✨ 開始 AI 分析", type="primary", use_container_width=True, disabled=disabled):
        with st.status("🤖 分析中…", expanded=True) as status:
            try:
                main_image = Image.open(io.BytesIO(st.session_state.main_bytes))
                label_image = Image.open(io.BytesIO(st.session_state.label_bytes)) if st.session_state.label_bytes else None
                st.session_state.tags = analyze_clothing(main_image, label_image)
                status.update(label="✅ 分析完成", state="complete", expanded=False)
                time.sleep(0.5)
                st.session_state.step = 2
                st.rerun()
            except Exception as e:
                status.update(label="❌ 分析失敗", state="error", expanded=True)
                st.code(str(e))

# ---------- 步驟 2：確認／微調 ----------
elif st.session_state.step == 2:
    st.info("步驟 2／3：確認標籤（尺寸可直接點按）")
    tags = st.session_state.tags

    col1, col2 = st.columns(2)
    with col1:
        brand = st.text_input("品牌", value=tags.get("brand", "未知"))
        color = st.text_input("顏色", value=tags.get("color", ""))
        gender_opts = ["男", "女", "中性"]
        g = tags.get("gender")
        gender = st.selectbox("性別", gender_opts, index=gender_opts.index(g) if g in gender_opts else 2)
    with col2:
        style = st.text_input("樣式", value=tags.get("style", ""))
        qty = st.number_input("數量（庫存）", min_value=1, value=int(st.session_state.qty), step=1)

    size_opts = ["XS", "S", "M", "L", "XL", "XXL", "F", "未標示"]
    ai_size = tags.get("size", "未標示")
    size_choice = st.radio(
        "尺寸（快速選）", size_opts,
        index=size_opts.index(ai_size) if ai_size in size_opts else size_opts.index("未標示"),
        horizontal=True,
    )
    size_other = st.text_input("尺寸（其他，選填；填了以此為準）", value="" if ai_size in size_opts else ai_size)
    size = size_other.strip() if size_other.strip() else size_choice

    c1, c2 = st.columns(2)
    with c1:
        if st.button("🔄 重拍", use_container_width=True):
            for k in ["main_bytes", "label_bytes", "tags", "preview_bytes"]:
                st.session_state[k] = defaults[k]
            st.session_state.step = 1
            st.rerun()
    with c2:
        if st.button("👀 產生預覽", type="primary", use_container_width=True):
            st.session_state.tags.update({"brand": brand, "color": color, "gender": gender, "style": style, "size": size})
            st.session_state.qty = qty
            main_image = Image.open(io.BytesIO(st.session_state.main_bytes))
            out = add_text_to_image(main_image, brand, style, color, gender, size, qty)
            buf = io.BytesIO()
            out.save(buf, format="JPEG", quality=90)
            st.session_state.preview_bytes = buf.getvalue()
            st.session_state.filename = f"item_{int(time.time())}.jpg"
            st.session_state.step = 3
            st.rerun()

# ---------- 步驟 3：完成（下載／分享到 LINE） ----------
elif st.session_state.step == 3:
    st.info("步驟 3／3：分享到 LINE 群即完成上架")
    st.image(st.session_state.preview_bytes, caption="成品（分享到群，機器人會自動上架）", use_container_width=True)

    st.download_button(
        "💾 下載到手機相簿", data=st.session_state.preview_bytes,
        file_name=st.session_state.filename, mime="image/jpeg", use_container_width=True,
    )
    line_share_button(st.session_state.preview_bytes, st.session_state.filename)

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        if st.button("✏️ 返回修改", use_container_width=True):
            st.session_state.step = 2
            st.rerun()
    with c2:
        if st.button("📸 拍下一件", type="primary", use_container_width=True):
            for k, v in defaults.items():
                st.session_state[k] = v
            st.rerun()