import os
import sys
import subprocess

# 📦 필수 도구 자동 설치 (requests, 구글 API, 제미나이 SDK)
try:
    import requests
    from google import genai
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build
except ModuleNotFoundError:
    print("📦 필수 라이브러리가 누락되어 자동 설치를 시작합니다...")
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
from urllib.parse import urlencode

# =====================================================================
# ⚙️ [고유 설정 정보] 형의 진짜 정보들로 꼭 채워 넣어주세요!
# =====================================================================
BLOG_ID = "형의_진짜_블로그_ID_입력"  
GOOGLE_ADSENSE_CLIENT = "형의_애드센스_pub_코드_입력"
GOOGLE_ADSENSE_SLOT = "형의_애드센스_slot_코드_입력"

# 🎯 자동 순환 키워드 풀 (2040 취향 저격 대형 그물망)
SUGGESTED_KEYWORDS = [
    "접이식 대용량 빨래바구니", "틈새 수납 슬라이딩 카트", "무선 버티컬 마우스", 
    "데스크테리어 모니터 받침대", "차량용 미니 무선 청소기", "트렁크 깔끔 정리함",
    "휴대용 미니 마사지건", "가성비 인바디 체중계", "무소음 스태퍼 홈트"
]

def generate_coupang_headers(method, path, query_string, access_key, secret_key):
    # ⚠️ [오타 패치] %y(소문자)를 %Y(대문자)로 수정하여 404 에러 원천 차단!
    datetime_gmt = time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())
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

def get_coupang_products(keyword, access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    path = "/v1/partners/products/search"
    
    params = {"keyword": keyword, "limit": 4} # 상위 4개 알짜 상품 소싱
    query_string = urlencode(params)
    url = f"{domain}{path}?{query_string}"

    headers = generate_coupang_headers("GET", path, query_string, access_key, secret_key)
    res = requests.get(url, headers=headers, timeout=10)
    
    if res.status_code != 200:
        print(f"❌ 쿠팡 API 호출 실패 (코드: {res.status_code}), 메시지: {res.text}")
        return []
        
    return res.json().get("data", {}).get("productData", [])

def main():
    print("🔄 [쿠팡 파트너스 x 블로그스팟] 무결성 자동화 공장을 가동합니다.")
    
    # 환경 변수 및 금고 열쇠 확인
    gemini_key = os.environ.get("API_KEY", "").strip()
    token_base64 = os.environ.get("TOKEN_PICKLE_BASE64", "").strip()
    coupang_access = os.environ.get("COUPANG_ACCESS_KEY", "").strip()
    coupang_secret = os.environ.get("COUPANG_SECRET_KEY", "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ [중단] 깃허브 시크릿 금고에 등록되지 않은 키가 있습니다. 확인해 주세요.")
        return

    # 1. 아이템 키워드 랜덤 소싱
    keyword = random.choice(SUGGESTED_KEYWORDS)
    print(f"🎯 [1단계: 소싱] 오늘의 타겟 키워드: {keyword}")
    
    products = get_coupang_products(keyword, coupang_access, coupang_secret)
    if not products:
        print("🚨 소싱된 쿠팡 상품이 없어 프로세스를 홀딩합니다.")
        return
    
    print(f"✅ 쿠팡 상품 {len(products)}개 소싱 완료!")

    # 2. 제미나이 AI 원고 작성 데이터 조립
    product_info_text = ""
    for p in products:
        product_info_text += f"- 상품명: {p['productName']}\n  가격: {p['productPrice']}원\n  구매링크: {p['productUrl']}\n  이미지: {p['productImage']}\n\n"

    print("🤖 [2단계: AI 원고 생성] 제미나이에게 마케팅 원고 요청 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
    당신은 최고의 e-commerce 마케터이자 블로그 에디터입니다.
    소비자가 아래 제공된 상품 리스트를 보고 강력한 구매 욕구를 느끼도록 설득력 있고 유용한 정보를 제공하는 블로그 포스팅 원고를 작성해 주세요.

    [소싱된 상품 리스트]
    {product_info_text}

    [작성 규칙]
    1. 제목은 타겟 키워드인 '{keyword}'가 포함되도록 직관적이고 매력적으로 뽑아주세요.
    2. 본문은 친근한 말투(~해보세요, ~입니다)로 작성하고, 각 상품별 특장점을 명확히 짚어주세요.
    3. 각 상품 설명이 끝나는 지점에 [LINK_HERE_0], [LINK_HERE_1] 형태로 구매 링크가 들어갈 자리를 정확히 표시해 주세요.
    4. 포스팅의 맨 앞과 맨 뒤에는 제품 추천 배경과 유의사항 등을 자연스럽게 배치해 주세요.
    5. 대답은 오직 블로그 포스팅 본문 내용(HTML 형식 아님, 순수 텍스트)만 출력하세요.
    """
    
    response = ai_client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
    )
    ai_content = response.text
    print("✅ 제미나이 원고 생성 성공!")

    # 3. HTML 변환 및 광고/링크 배너 매칭
    post_body = "💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.<br><br>"
    paragraphs = ai_content.split('\n\n')
    
    # 타이틀 추출 (첫 줄)
    title = paragraphs[0].replace("제목:", "").replace("#", "").strip() if paragraphs else f"가성비 대박 추천: {keyword}"
    
    product_idx = 0
    for idx, para in enumerate(paragraphs):
        if idx == 0 and ("제목" in para or "#" in para):
            continue # 제목 줄은 본문에서 제외
            
        cleaned_para = para.replace("\n", "<br>")
        post_body += f"<p>{cleaned_para}</p>"
        
        # 제미나이가 지정한 자리에 쿠팡 이미지 및 링크 배너 심기
        link_tag = f"[LINK_HERE_{product_idx}]"
        if link_tag in post_body and product_idx < len(products):
            p = products[product_idx]
            ad_banner = f"""
            <div style="text-align: center; margin: 20px 0; padding: 15px; border: 1px solid #ddd; border-radius: 8px;">
                <img src="{p['productImage']}" alt="{p['productName']}" style="max-width:250px; border-radius:5px;"><br>
                <strong style="font-size:16px; color:#333;">{p['productName']}</strong><br>
                <span style="color:#e4393c; font-size:18px; font-weight:bold;">{p['productPrice']}원</span><br><br>
                <a href="{p['productUrl']}" target="_blank" style="background-color:#007bf5; color:white; padding:10px 20px; text-decoration:none; border-radius:5px; font-weight:bold; display:inline-block;">👉 최저가 확인 및 구매하기</a>
            </div>
            """
            post_body = post_body.replace(link_tag, ad_banner)
            product_idx += 1

    # 애드센스 광고 코드 하단 삽입
    adsense_code = f"""
    <br><br>
    <div style="text-align: center; margin-top: 30px;">
        <script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={GOOGLE_ADSENSE_CLIENT}" crossorigin="anonymous"></script>
        <ins class="adsbygoogle" style="display:block" data-ad-client="{GOOGLE_ADSENSE_CLIENT}" data-ad-slot="{GOOGLE_ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins>
        <script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script>
    </div>
    """
    post_body += adsense_code

    # 4. 구글 블로그스팟에 내일 오전 8시 예약 발행 처리
    print("🚀 [3단계: 블로그 업로드] 구글 블로그스팟 예약 발행 처리 시작...")
    try:
        creds_json = base64.b64decode(token_base64).decode('utf-8')
        creds_data = json.loads(creds_json)
        credentials = Credentials.from_authorized_user_info(creds_data)
        blogger_service = build('blogger', 'v3', credentials=credentials)
        
        # 내일 오전 8시 타임스탬프 계산
        tomorrow = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        scheduled_time = tomorrow.replace(hour=23, minute=0, second=0, microsecond=0).isoformat() # UTC 23시 = 한국 오전 8시

        new_post = {
            "kind": "blogger#post",
            "blog": {"id": BLOG_ID},
            "title": title,
            "content": post_body,
            "published": scheduled_time
        }

        blogger_service.posts().insert(blogId=BLOG_ID, body=new_post, isDraft=False).execute()
        print(f"🎯 [성공] '{title}' 예약글 발행 완료! 내일 오전 8시에 정상 오픈됩니다.")
        
    except Exception as e:
        print(f"❌ 구글 블로그스팟 예약 업로드 중 에러 발생: {str(e)}")

if __name__ == "__main__":
    main()
