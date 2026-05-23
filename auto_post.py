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
from urllib.parse import quote  # ⚠️ 한글 깨짐 방지용 정석 도구 도입

BLOG_ID = "형의_진짜_블로그_ID_입력"  
GOOGLE_ADSENSE_CLIENT = "형의_애드센스_pub_코드_입력"
GOOGLE_ADSENSE_SLOT = "형의_애드센스_slot_코드_입력"

SUGGESTED_KEYWORDS = ["생수", "노트북", "골프채", "비타민", "마사지기", "청소기"]

def get_coupang_products(keyword, access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    path = "/v1/partners/products/search"
    
    # ⚠️ [한글 404 차단 패치] 한글 키워드를 쿠팡 규격에 맞게 미리 URL 인코딩 처리
    encoded_keyword = quote(keyword)
    query_string = f"keyword={encoded_keyword}&limit=4"

    datetime_gmt = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
    message = datetime_gmt + "GET" + path + query_string

    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).hexdigest()

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"
    }

    url = f"{domain}{path}?{query_string}"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        print(f"📡 쿠팡 서버 응답 상태코드: {res.status_code}")
        if res.status_code != 200:
            print(f"❌ 호출 실패 (코드: {res.status_code}), 메시지: {res.text}")
            return []
        return res.json().get("data", {}).get("productData", [])
    except Exception as e:
        print(f"💥 쿠팡 통신 중 예외 발생: {str(e)}")
        return []

def main():
    print("🔄 [쿠팡 파트너스 x 블로그스팟] 무결성 자동화 공장을 가동합니다.")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ [중단] 깃허브 시크릿 금고 열쇠 확인 필요")
        return

    keyword = random.choice(SUGGESTED_KEYWORDS)
    print(f"🎯 [1단계: 소싱] 오늘의 타겟 키워드: {keyword}")
    
    products = get_coupang_products(keyword, coupang_access, coupang_secret)
    if not products:
        print("🚨 소싱된 쿠팡 상품이 없어 프로세스를 홀딩합니다.")
        return
    
    print(f"✅ 쿠팡 상품 {len(products)}개 소싱 완료!")

    product_info_text = ""
    for p in products:
        product_info_text += f"- 상품명: {p['productName']}\n  가격: {p['productPrice']}원\n  구매링크: {p['productUrl']}\n  이미지: {p['productImage']}\n\n"

    ai_client = genai.Client(api_key=gemini_key)
    prompt = f"당신은 최고의 마케터입니다. 다음 상품 리스트를 보고 블로그 원고를 작성해 주세요:\n{product_info_text}"
    
    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    ai_content = response.text
    print("✅ 제미나이 원고 생성 성공!")

    post_body = "💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로 수수료를 제공받습니다.<br><br>"
    paragraphs = ai_content.split('\n\n')
    title = paragraphs[0].replace("제목:", "").replace("#", "").strip() if paragraphs else f"추천: {keyword}"
    
    for para in paragraphs:
        post_body += f"<p>{para.replace('\n', '<br>')}</p>"

    adsense_code = f"<br><ins class='adsbygoogle' data-ad-client='{GOOGLE_ADSENSE_CLIENT}' data-ad-slot='{GOOGLE_ADSENSE_SLOT}'></ins>"
    post_body += adsense_code

    try:
        creds_json = base64.b64decode(token_base64).decode('utf-8')
        credentials = Credentials.from_authorized_user_info(json.loads(creds_json))
        blogger_service = build('blogger', 'v3', credentials=credentials)
        
        tomorrow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=23, minute=0, second=0, microsecond=0).isoformat()

        new_post = {"kind": "blogger#post", "blog": {"id": BLOG_ID}, "title": title, "content": post_body, "published": scheduled_time}
        blogger_service.posts().insert(blogId=BLOG_ID, body=new_post, isDraft=False).execute()
        print(f"🎯 [성공] '{title}' 예약글 발행 완료!")
    except Exception as e:
        print(f"❌ 구글 블로그 업로드 에러: {str(e)}")

if __name__ == "__main__":
    main()
