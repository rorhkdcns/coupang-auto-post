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
    
    # [V2 API 파라미터 규격]
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
    
    # 1. GMT 기준 타임스탬프 생성
    gmt_now = datetime.datetime.now(datetime.timezone.utc)
    datetime_gmt = gmt_now.strftime('%y%m%dT%H%M%SZ')
    
    # 2. 쿠팡 V2 서명 생성용 메시지 구조
    message = datetime_gmt + "POST" + path

    # 3. Hmac SHA256 서명 생성
    signature = hmac.new(
        bytes(secret_key, "utf-8"),
        bytes(message, "utf-8"),
        hashlib.sha256
    ).hexdigest()

    # 4. Authorization 헤더 규격 
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
            # 쿠팡 실 응답 데이터 키인 "result"를 최우선으로 탐색
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

    # 제미나이 전송용 데이터 정제
    product_info_text = ""
    for idx, p in enumerate(products, 1):
        product_info_text += f"[상품 {idx}]\n"
        product_info_text += f"- 상품명: {p.get('productName', '상품명 없음')}\n"
        product_info_text += f"- 가격: {p.get('productPrice', 0)}원\n"
        product_info_text += f"- 구매링크: {p.get('productUrl', p.get('landingUrl', ''))}\n"
        product_info_text += f"- 이미지주소: {p.get('productImage', '')}\n\n"

    print("🤖 [2단계: AI 원고 생성] 제미나이에게 HTML 마케팅 원고 요청 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    # 💡 [핵심 교정]
    # 1. '10년차 수석 카피라이터' 등 페르소나 제거 -> 담백한 에디터로 변경
    # 2. 이미지 엑박 방지(referrerpolicy) 및 가운데 정렬, 크기 키우기 강제
    # 3. 중요 키워드 빨간색 볼드체 처리
    prompt = f"""
당신은 쿠팡 파트너스 전문 에디터입니다.
제공된 상품 리스트를 활용하여 독자의 호기심을 자극하고 유용한 정보를 제공하는 세련된 블로그 포스팅을 작성해 주세요.

[작성 핵심 전략: 담백한 PASONA 법칙 적용]
반드시 'Problem(고민) - Affinity(공감) - Solution(해결책) - Offer(혜택 제안) - Narrowing down(한정/긴급성) - Action(행동 유도)'의 흐름에 따라 글을 전개하세요.
단, 주의할 점은 절대로 본문에 'Problem', 'Solution' 같은 이론적 단어를 직접 노출하지 말고, 독자가 "내 고민을 알아주는 에세이"를 읽는 것처럼 자연스럽게 스토리텔링 하세요. 거부감 드는 자화찬은 삼가세요.

[HTML 및 포맷 요구사항 (가독성과 정보 전달 극대화)]
1. 첫 줄은 무조건 '제목: [소비자를 이끄는 호기심 유발 제목]' 형식으로 작성하세요.
2. 🚨 마크다운(Markdown) 기호(예: **글씨**, # 제목)는 절대 사용하지 마세요! 오직 순수 HTML 태그만 사용해야 합니다.
3. 텍스트가 벽돌처럼 빽빽해 보이지 않도록 문단을 짧게 나누고(<p>, <br> 적극 활용), 각 상품의 가장 중요한 특징, 강력한 혜택, **핵심 키워드에는 반드시 `<strong style="color:#e52528;">중요 키워드</strong>` 형태의 태그를 씌워 빨간색 굵은 글씨로 시선이 꽂히게 만드세요.**
4. 글의 흐름이 잘 읽히도록 시선을 끄는 <h2> 또는 <h3> 태그의 매력적인 소제목을 본문 곳곳에 적극 활용하세요.
5. 💡 각 상품의 이미지를 넣을 때는 엑박(Broken Image) 현상을 막기 위해 반드시 아래 형태의 HTML 태그로 정확히 작성하세요. (referrerpolicy 속성 필수, 이미지 크기 증대 및 가운데 정렬 반영)
   <div style="text-align: center; margin-bottom: 20px;">
     <img src="[제공된 이미지주소]" alt="[상품명]" style="width: 100%; max-width: 500px; height: auto;" referrerpolicy="no-referrer">
   </div>
6. 구매링크는 CTA(행동 유도) 문구가 적용된 <a> 태그(target="_blank" style="text-decoration:none; color:white; background-color:#e52528; padding:10px 20px; border-radius:5px; font-weight:bold; display:inline-block; margin-top:10px;") 형태의 버튼으로 작성하세요.
7. 쿠팡 파트너스 안내 문구는 제가 따로 넣을 테니 본문 내용에만 집중하세요.

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
        creds_bytes = base64.b64decode(token_base64)
        credentials = pickle.loads(creds_bytes)
        
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
