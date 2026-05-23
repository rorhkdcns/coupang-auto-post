import os
import sys
import subprocess

# 📦 필수 도구 자동 설치
try:
    import requests
except ModuleNotFoundError:
    print("📦 requests 라이브러리가 없어 자동 설치를 시작합니다...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

import random
import hmac
import hashlib
import time
import json
from urllib.parse import urlencode

# ⚙️ 고유 설정 정보 (형의 정보로 채워 넣으세요!)
BLOG_ID = "형의_쿠팡_블로그_ID"  
GOOGLE_ADSENSE_CLIENT = "형의_애드센스_pub_코드"
GOOGLE_ADSENSE_SLOT = "형의_애드센스_slot_코드"

# 🎯 자동 순환 키워드 풀
SUGGESTED_KEYWORDS = ["생수", "노트북", "골프채", "비타민", "마사지기"]

def generate_coupang_headers(method, path, query_string, access_key, secret_key):
    if not access_key or not secret_key:
        raise ValueError("❌ 깃허브 시크릿에 쿠팡 키가 누락되었거나 비어있습니다!")
        
    datetime_gmt = time.strftime('%y%m%dT%H%M%SZ', time.gmtime())
    message = datetime_gmt + method + path + query_string

    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).hexdigest()

    return {
        "Content-Type": "application/json",
        "Authorization": f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"
    }

def main():
    print("🔄 쿠팡 전용 자동화 에러 추적 모드를 가동합니다.")
    
    access_key = os.environ.get("COUPANG_ACCESS_KEY", "").strip()
    secret_key = os.environ.get("COUPANG_SECRET_KEY", "").strip()
    
    keyword = random.choice(SUGGESTED_KEYWORDS)
    print(f"🎯 [아이템 소싱] 이번 타겟 키워드: {keyword}")

    # ⚠️ [핵심 패치] 파트너스 전용 최신 정식 도메인으로 교체!
    domain = "https://partners.api.coupang.com"
    path = "/v1/partners/products/search"
    
    params = {
        "keyword": keyword,
        "limit": 10
    }
    query_string = urlencode(params)
    url = f"{domain}{path}?{query_string}"

    try:
        headers = generate_coupang_headers("GET", path, query_string, access_key, secret_key)
        res = requests.get(url, headers=headers, timeout=10)
        
        print(f"📡 쿠팡 서버 응답 코드: {res.status_code}")
        
        if res.status_code != 200:
            print("❌ [경고] 쿠팡 API 호출 실패!")
            print(f"ℹ️ 쿠팡이 보낸 에러 메시지: {res.text}")
            raise Exception(f"쿠팡 인증 실패 상태코드: {res.status_code}")
            
        data = res.json()
        products = data.get("data", {}).get("productData", [])
        
        if not products:
            print("🚨 키는 정상인데, 검색된 상품 결과 자체가 진짜 0개입니다.")
            return

        print(f"✅ 대성공!!! 쿠팡에서 상품 {len(products)}개를 정상적으로 긁어왔습니다!")
        print(f"📦 첫 번째 상품 샘플: {products[0].get('productName')} - {products[0].get('productPrice')}원")
        
    except Exception as e:
        print(f"💥 치명적 오류 발생: {str(e)}")
        raise e

if __name__ == "__main__":
    main()
