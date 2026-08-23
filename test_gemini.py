import os
import streamlit as st
from PIL import Image
from google import genai

def test_gemini_vision(image_path):
    """
    測試 Gemini 2.5 Flash 是否能正常接收圖片並進行服飾標籤分析
    """
    try:
        # 正確做法：從 .streamlit/secrets.toml 讀取金鑰，避免明碼外流
        api_key = st.secrets["gemini_api_key"]
        
        # 初始化 Gemini 客戶端
        client = genai.Client(api_key=api_key)
        
        # 載入測試圖片
        image = Image.open(image_path)
        
        prompt = """
        請分析這張衣服照片，並以 JSON 格式回傳：
        - brand: 品牌名稱
        - style: 服飾樣式
        - color: 主要顏色
        - gender: 男裝/女裝/中性
        - size: 尺寸標籤
        """
        
        print("正在安全讀取金鑰，並傳送圖片至 Gemini API...")
        response = client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[image, prompt]
        )
        
        print("\n--- AI 辨識結果 ---")
        print(response.text)
        
    except FileNotFoundError:
        print("錯誤：找不到圖片檔案。請確認檔名與路徑是否正確。")
    except KeyError:
        print("錯誤：在 secrets.toml 中找不到 'gemini_api_key'，請檢查設定檔。")
    except Exception as e:
        print(f"呼叫 API 發生未知錯誤: {e}")

if __name__ == "__main__":
    # 準備用來測試的圖片檔名
    test_image = "test.jpg" 
    
    if os.path.exists(test_image):
        test_gemini_vision(test_image)
    else:
        print(f"請在專案資料夾中放一張名為 {test_image} 的照片以進行測試。")