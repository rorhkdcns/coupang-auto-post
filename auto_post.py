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

# =====================================================================
# ⚙️ [고유 설정 정보]
# =====================================================================
BLOG_ID = "8715372631292128719"  
GOOGLE_ADSENSE_CLIENT = "ca-pub-4292478378917157"
GOOGLE_ADSENSE_SLOT = "7988651325"

# 🎯 추천 상품 API용 주요 카테고리 ID 리스트
# 1001: 여성패션, 1011: 식품, 1016: 가전디지털, 1019: 생활용품, 1021: 스포츠/레저
CATEGORY_IDS = ["1011", "1016", "1019", "1021"] 

def get_coupang_best_products(category_id, access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    
    # 💡 [교정] 카테고리 ID가 URL 경로(Path) 자체에 포함되는 정식 규격 적용
    path = f"/v1/partners/products/v1/categories/{category_id}"
    
    # 💡 [교정] 쿼리 스트링 조건 최소화 및 무결성 확보
    query_string = "limit=4"
    
    # 1. 서명(Signature) 생성 (Method + Path + QueryString)
    message = "GET" + path + query_string

    # GMT 기준 타임스탬프 생성
    gmt_now = datetime.datetime.now(datetime.timezone.utc)
    datetime_gmt = gmt_now.strftime('%Y%m%dT%H%M%SZ')
    
    # Hmac SHA256 서명 생성
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).hexdigest()

    # Authorization 헤더 조립
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"
    }

    # 최종 요청 URL
    url = f"{domain}{path}?{query_string}"

    try:
        res = requests.get(url, headers=headers, timeout=10)
        print(f"📡 쿠팡 서버 응답 상태코드: {res.status_code}")
        
        if res.status_code != 200:
            print(f"❌ 호출 실패 (코드: {res.status_code}), 메시지: {res.text}")
            return []
            
        res_json = res.json()
        
        # 💡 [영상 데이터 구조 반영 교정] 
        # 쿠팡 API는 'data' 딕셔너리 내부의 'productData' 키값에 실제 상품 배열을 반환합니다.
        data_content = res_json.get("data", {})
        if isinstance(data_content, dict):
            return data_content.get("productData", [])
        return []
        
    except Exception as e:
        print(f"💥 쿠팡 통신 중 예외 발생: {str(e)}")
        return []

def main():
    print("🔄 [쿠팡 파트너스 x 블로그스팟] 무결성 추천상품 자동화 공장을 가동합니다.")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ [중단] 깃허브 시크릿 금고 열쇠 확인 필요")
        return

    # 타겟 카테고리 랜덤 선정
    target_category = random.choice(CATEGORY_IDS)
    print(f"🎯 [1단계: 소싱] 오늘의 타겟 카테고리 ID: {target_category}")
    
    products = get_coupang_best_products(target_category, coupang_access, coupang_secret)
    if not products:
        print("🚨 소싱된 쿠팡 추천 상품이 없어 프로세스를 홀딩합니다.")
        return
    
    print(f"✅ 쿠팡 추천 상품 {len(products)}개 소싱 성공!")

    # 제미나이 전송용 데이터 정제
    product_info_text = ""
    for idx, p in enumerate(products, 1):
        product_info_text += f"[상품 {idx}]\n"
        product_info_text += f"- 상품명: {p.get('productName', '상품명 없음')}\n"
        product_info_text += f"- 가격: {p.get('productPrice', 0)}원\n"
        product_info_text += f"- 구매링크: {p.get('productUrl', '')}\n"
        product_info_text += f"- 이미지주소: {p.get('productImage', '')}\n\n"

    print("🤖 [2단계: AI 원고 생성] 제미나이에게 HTML 마케팅 원고 요청 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
당신은 최고의 디지털 마케터이자 블로그 에디터입니다. 
제공된 쿠팡 베스트 상품 리스트를 바탕으로 소비자들의 구매 욕구를 강력하게 자극하는 큐레이션 형태의 블로그 포스팅을 작성해 주세요.

[요구사항]
1. 출력 포맷은 반드시 HTML 태그(<p>, <h2>, <a>, <img> 등)를 편리하게 파싱할 수 있도록 완성형으로 작성해 주세요.
2. 각 상품을 소개할 때, 제공된 '이미지주소'를 <img> 태그로 넣고, '구매링크'를 버튼이나 텍스트 링크(<a href="..." target="_blank">) 형태로 자연스럽게 본문에 포함해 주세요.
3. 첫 줄에는 '제목: [소비자를 이끄는 매력적인 제목]' 형식으로 제목을 명시해 주세요.
4. 쿠팡 파트너스 안내 문구는 제가 따로 넣을 테니 오직 상품 큐레이션 본문 내용에만 집중해 주세요.

[상품 리스트]
{product_info_text}
"""
    
    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    ai_content = response.text
    print("✅ 제미나이 원고 생성 성공!")

    # 3. 본문 조립 (파트너스 필수 공정 배너 선삽입)
    post_body = "<p style='color: gray; font-size: 0.9em; text-align: center;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p><br>"
    
    # 제목 파싱 분리
    lines = ai_content.strip().split('\n')
    title = f"오늘의 추천 베스트 상품 시리즈"
    content_start_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith("제목:"):
            title = line.replace("제목:", "").replace("#", "").strip()
            content_start_idx = i + 1
            break
            
    # 본문 데이터 합체
    post_body += "\n".join(lines[content_start_idx:])

    # 하단 구글 애드센스 결합
    adsense_code = f"<br><br><ins class='adsbygoogle' style='display:block' data-ad-client='{GOOGLE_ADSENSE_CLIENT}' data-ad-slot='{GOOGLE_ADSENSE_SLOT}' data-ad-format='auto' data-full-width-responsive='true'></ins>"
    post_body += adsense_code

    try:
        creds_json = base64.b64decode(token_base64).decode('utf-8')
        credentials = Credentials.from_authorized_user_info(json.loads(creds_json))
        blogger_service = build('blogger', 'v3', credentials=credentials)
        
        # 구글 블로거 규격(RFC 3339) 예약 타임스탬프 (내일 밤 11시 발행)
        tomorrow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=23, minute=0, second=0, microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')

        new_post = {
            "kind": "blogger#post",
            "blog": {"id": BLOG_ID},
            "title": title,
            "content": post_body,
            "published": scheduled_time
        }
        
        blogger_service.posts().insert(blogId=BLOG_ID, body=new_post, isDraft=False).execute()
        print(f"🎯 [성공] '{title}' 예약글 발행 완료 (발행 예정 시각: {scheduled_time})")
    except Exception as e:
        print(f"❌ 구글 블로그 업로드 에러: {str(e)}")

if __name__ == "__main__":
    main()
