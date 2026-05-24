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

# =====================================================================
# ⚙️ [고유 설정 정보]
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
    for idx, p in enumerate(products, 1):
        product_info_text += f"[상품 {idx}]\n"
        product_info_text += f"- 상품명: {p.get('productName', '상품명 없음')}\n"
        product_info_text += f"- 가격: {p.get('productPrice', 0)}원\n"
        product_info_text += f"- 구매링크: {p.get('productUrl', p.get('landingUrl', ''))}\n"
        product_info_text += f"- 이미지주소: {p.get('productImage', '')}\n\n"

    print("🤖 [2단계: AI 원고 생성] 제미나이에게 HTML 마케팅 원고 요청 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    # 💡 [핵심 변경] PASONA 법칙, 소제목, CTA를 강제하는 고도화된 프롬프트
    prompt = f"""
당신은 10년 차 수석 카피라이터이자 구매 전환율 1위의 블로그 에디터입니다. 
제공된 쿠팡 상품 리스트를 활용하여 독자가 당장 구매하고 싶게 만드는 매력적인 블로그 포스팅을 작성해 주세요.

[작성 핵심 전략: 자연스러운 PASONA 법칙 적용]
반드시 'PASONA 법칙(Problem - Affinity - Solution - Offer - Narrowing down - Action)'의 흐름에 따라 글을 전개하세요. 
단, 주의할 점은 **절대로 본문에 'Problem', 'Solution', 'PASONA' 같은 이론적 단어나 기호를 직접 노출해서는 안 됩니다.** 물 흐르듯 자연스러운 에세이나 리뷰처럼 스토리텔링 하세요.

1. (문제 제기 & 공감): 독자가 일상에서 겪을 법한 고민이나 불편함을 짚어주고, "맞아요, 저도 요즘 그게 참 고민이더라고요"라며 깊이 공감하는 도입부로 시작하세요.
2. (해결책 제시): 그 고민을 완벽하게 해결해 줄 '치트키'이자 '구원템'으로 아래의 상품들을 자연스럽게 소개하세요.
3. (제안 & 한정 혜택): 각 상품의 핵심 소구점(가성비, 압도적 편의성 등)을 매력적으로 어필하고, "왜 지금 당장 알아봐야 하는지(품절 임박, 요즘 제일 잘나가는 베스트셀러 등)"를 언급하여 조급함을 살짝 자극하세요.
4. (행동 촉구 - 강력한 CTA): 각 상품 소개 끝에는 반드시 독자의 클릭을 유도하는 강력하고 직관적인 CTA 문구와 함께 구매 링크를 배치하세요. (예: "👉 품절되기 전에 최저가로 담아두기", "🔥 오늘 시세 확인하러 가기" 등)

[HTML 및 포맷 요구사항]
1. 첫 줄은 무조건 '제목: [소비자를 이끄는 호기심 유발 제목]' 형식으로 작성하세요.
2. 글의 흐름이 잘 읽히고 지루하지 않도록 **반드시 시선을 끄는 <h2> 또는 <h3> 태그의 매력적인 소제목**을 본문 곳곳에 적극적으로 활용하세요.
3. 각 상품 소개 시 제공된 '이미지주소'를 <img> 태그로 넣고, '구매링크'는 CTA 문구가 적용된 <a> 태그(target="_blank" style="...버튼처럼 보이게 혹은 굵은 글씨체로...")로 작성하세요.
4. 쿠팡 파트너스 안내 문구는 제가 따로 넣을 테니 본문 내용에만 집중하세요.

[상품 리스트]
{product_info_text}
"""
    
    response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
    ai_content = response.text
    print("✅ 제미나이 원고 생성 성공!")

    post_body = "<p style='color: gray; font-size: 0.9em; text-align: center;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p><br>"
    
    lines = ai_content.strip().split('\n')
    title = f"오늘의 추천 베스트 상품 시리즈"
    content_start_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith("제목:"):
            title = line.replace("제목:", "").replace("#", "").strip()
            content_start_idx = i + 1
            break
            
    post_body += "\n".join(lines[content_start_idx:])

    adsense_code = f"<br><br><ins class='adsbygoogle' style='display:block' data-ad-client='{GOOGLE_ADSENSE_CLIENT}' data-ad-slot='{GOOGLE_ADSENSE_SLOT}' data-ad-format='auto' data-full-width-responsive='true'></ins>"
    post_body += adsense_code

    try:
        creds_bytes = base64.b64decode(token_base64)
        credentials = pickle.loads(creds_bytes)
        
        blogger_service = build('blogger', 'v3', credentials=credentials)
        
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
