import os
import sys
import subprocess

try:
    import requests
    from google import genai
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ModuleNotFoundError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "google-auth-oauthlib", "google-auth-httplib2", "google-api-python-client", "google-genai"])
    import requests
    from google import genai
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

import random
import hmac
import hashlib
import time
import json
import base64
import datetime
import pickle
import re

# =====================================================================
# ⚙️ [고유 설정 정보] (유저님 세팅 무결성 100% 보존)
# =====================================================================
BLOG_ID = "8715372631292128719"  
GOOGLE_ADSENSE_CLIENT = "ca-pub-4292478378917157"
GOOGLE_ADSENSE_SLOT = "7988651325"

# 블로그스팟 실 도메인
BLOG_DOMAIN = "blogspot.com"

def get_coupang_v2_products(access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    path = "/v2/providers/affiliate_open_api/apis/openapi/v2/products/reco"
    
    req_data = {
        "site": {
            "domain": BLOG_DOMAIN,
            "id": BLOG_ID
        },
        "device": {
            "id": "DESKTOP_ID",
            "ip": "127.0.0.1",
            "lmt": 0,
            "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        },
        "imp": {
            "ad_type": 2,          
            "imageSize": "180x180", 
            "placementid": "blog_main",
            "pos": 1                
        },
        "user": {
            "puid": "blogger_user"
        }
    }
    
    gmt_now = datetime.datetime.now(datetime.timezone.utc)
    datetime_gmt = gmt_now.strftime('%y%m%dT%H%M%SZ')
    
    message = datetime_gmt + "POST" + path

    # 🛡️ [클린 교정 완료] 인자 개수를 3개로 정확하게 맞추어 TypeError 원천 차단
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).hexdigest()

    authorization_header = (
        f"CEA algorithm=HmacSHA256, "
        f"access-key={access_key}, "
        f"signed-date={datetime_gmt}, "
        f"signature={signature}"
    )

    headers = {
        "Content-Type": "application/json",
        "Authorization": authorization_header
    }

    url = f"{domain}{path}"

    try:
        res = requests.post(url, headers=headers, json=req_data, timeout=10)
        print(f"📡 쿠팡 V2 서버 응답 상태코드: {res.status_code}")
        
        if res.status_code != 200:
            print(f"❌ 호출 실패 (코드: {res.status_code}), 메시지: {res.text}")
            return []
            
        res_json = res.json()
        
        data_node = res_json.get("data")
        products_list = []
        
        if isinstance(data_node, list):
            products_list = data_node
        elif isinstance(data_node, dict):
            products_list = data_node.get("result", []) or data_node.get("recoProducts", []) or data_node.get("products", [])
            
        return products_list[:4] 
        
    except Exception as e:
        print(f"💥 쿠팡 V2 통신 중 예외 발생: {str(e)}")
        return []

# 가비지 태그 및 불필요 마크다운 완전 정화 장치
def clean_html_garbage(text):
    text = text.replace('`', '').replace('**', '').replace('__', '')
    text = text.replace('<span>', '').replace('</span>', '')
    text = re.sub(r'<\s*span[^>]*>', '', text) 
    text = re.sub(r'\[.*?\]\s*:\s*', '', text)
    return text.strip()

def main():
    print("🔄 [쿠팡 파트너스 API V2 x 블로그스팟] 자동화 공장을 가동합니다.")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ [중단] 깃허브 시크릿 금고 열쇠 확인 필요")
        return

    print("🎯 [1단계: 소싱] 최신 V2 맞춤 추천 상품 호출 중...")
    products = get_coupang_v2_products(coupang_access, coupang_secret)
    if not products:
        print("🚨 소싱된 쿠팡 추천 상품이 없어 프로세스를 홀딩합니다.")
        return
    
    print(f"✅ 쿠팡 추천 상품 {len(products)}개 소싱 성공!")

    product_info_text = ""
    html_assets = {} 
    
    for idx, p in enumerate(products, 1):
        img_url = p.get('productImage', '').strip()
        if img_url.startswith('//'):
            img_url = 'https:' + img_url
        elif img_url and not img_url.startswith('http'):
            img_url = 'https://' + img_url

        link_url = p.get('productUrl', p.get('landingUrl', ''))
        p_name = p.get('productName', '상품명 없음').replace('"', "'")
        p_price = p.get('productPrice', 0)

        img_html = f'<div style="text-align: center; margin-bottom: 20px;"><img src="{img_url}" alt="{p_name}" style="width: 100%; max-width: 400px; height: auto; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1);" referrerpolicy="no-referrer"></div>'
        btn_html = f'<div style="text-align: center; margin-top: 15px; margin-bottom: 50px;"><a href="{link_url}" target="_blank" style="text-decoration:none; color:white; background-color:#007B
