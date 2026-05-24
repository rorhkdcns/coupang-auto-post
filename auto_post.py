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
        btn_html = f'<div style="text-align: center; margin-top: 15px; margin-bottom: 50px;"><a href="{link_url}" target="_blank" style="text-decoration:none; color:white; background-color:#007BFF; padding:12px 25px; border-radius:8px; font-weight:bold; display:inline-block; font-size:16px;">👉 상품 자세히 보기</a></div>'

        html_assets[f"[[IMAGE_{idx}]]"] = img_html
        html_assets[f"[[BUTTON_{idx}]]"] = btn_html

        product_info_text += f"[상품 {idx}]\n"
        product_info_text += f"- 상품명: {p_name}\n"
        product_info_text += f"- 가격: {p_price}원\n"
        product_info_text += f"- 이미지 삽입 기호: [[IMAGE_{idx}]]\n"
        product_info_text += f"- 버튼 삽입 기호: [[BUTTON_{idx}]]\n\n"

    print("🤖 [2단계: AI 원고 생성] 제미나이에게 HTML 마케팅 원고 요청 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = f"""
당신은 쿠팡 파트너스 전문 에디터입니다.
제공된 상품 리스트를 활용하여 독자의 호기심을 자극하고 유용한 정보를 제공하는 세련된 블로그 포스팅을 작성해 주세요.

[작성 핵심 전략: 담백한 PASONA 법칙 적용]
'고민 - 공감 - 해결책 - 혜택 제안 - 한정/긴급성 - 행동 유도'의 흐름에 따라 글을 전개하세요.
단, 이론적 단어를 직접 노출하지 말고, 독자가 "내 고민을 알아주는 에세이"를 읽는 것처럼 자연스럽게 스토리텔링 하세요.

[HTML 및 포맷 디자인 요구사항 (디테일 100% 준수 필수)]
1. 💡 [핵심: 미친 후킹 제목] 첫 줄은 무조건 '제목: 호기심 유발 제목' 형식으로 작성하세요. 뻔한 '추천템 4가지' 같은 제목은 절대 금지합니다! 타겟의 고민을 날카롭게 찌르거나, 손실 회피 심리를 강하게 자극하는 클릭 유도형 카피라이팅을 적용하세요.
   - 좋은 예시: "더 이상 돈 낭비 마세요! 본전 뽑고도 남는 갓성비템 리스트", "나만 모르면 손해, 삶의 질이 수직 상승하는 숨겨진 꿀템"
   - (🚨주의: 제목에 대괄호 [ ] 기호는 절대 쓰지 마세요!)
2. 🚨 마크다운(Markdown) 기호(예: **글씨**, # 제목)는 절대 사용하지 마세요! 오직 순수 HTML 태그만 사용해야 합니다.
3. 글이 빽빽해 보이지 않도록 문장 1~2개 단위로 과감하게 문단을 나누세요. `<p style="line-height: 1.8; margin-bottom: 25px;">`를 사용하여 단락 사이 여백을 시원하게 확보하세요.
4. 컬러 규칙 (반드시 지킬 것):
   - 가격: 반드시 빨간색으로 작성 `<strong style="color:#E52528;">00,000원</strong>`
   - 핵심 키워드/강조: 반드시 핑크색으로 작성 `<strong style="color:#FF1493;">가장 중요한 혜택이나 포인트</strong>`
5. 글의 흐름을 안내하는 소제목은 본문보다 확실히 크게 보이도록 아래 태그를 그대로 사용하세요.
   <h3 style="font-size: 22px; font-weight: bold; color: #333; border-bottom: 2px solid #FF1493; padding-bottom: 8px; margin-top: 40px; margin-bottom: 20px;">소제목 텍스트</h3>
6. 🚨 [절대 규칙: 이미지와 버튼은 무조건 제공된 '기호'만 쓸 것] 
   각 상품을 소개할 때, 제공된 `[[IMAGE_1]]` 이나 `[[BUTTON_1]]` 같은 기호를 텍스트 그대로 본문에 입력하세요. 절대로 당신이 임의로 <img ...> 나 <a ...> 태그를 만들어내면 안 됩니다! 오직 기호만 적어두면 됩니다.
7. 쿠팡 파트너스 안내 문구는 제가 따로 넣을 테니 본문 내용에만 집중하세요.

[상품 리스트]
{product_info_text}
"""
    
    max_retries = 5
    ai_content = ""
    for attempt in range(max_retries):
        try:
            response = ai_client.models.generate_content(model='gemini-2.5-flash', contents=prompt)
            ai_content = response.text
            print("✅ 제미나이 원고 생성 성공!")
            break
        except Exception as e:
            print(f"⚠️ 제미나이 API 호출 실패 (시도 {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                print("⏳ 구글 서버 트래픽 혼잡... 20초 후 다시 시도합니다.")
                time.sleep(20)
            else:
                print("❌ 제미나이 API 최종 실패.")
                sys.exit(1)

    for key, actual_html in html_assets.items():
        ai_content = ai_content.replace(key, actual_html)

    post_body = "<p style='color: gray; font-size: 0.9em; text-align: center; margin-bottom: 30px;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>"
    
    lines = ai_content.strip().split('\n')
    title = f"오늘의 추천 베스트 상품 시리즈"
    content_start_idx = 0
    
    for i, line in enumerate(lines):
        if line.startswith("제목:"):
            title = line.replace("제목:", "").replace("[", "").replace("]", "").replace("#", "").strip()
            content_start_idx = i + 1
            break
            
    post_body += "\n".join(lines[content_start_idx:])

    adsense_code = f"<div style='margin-top: 50px;'><ins class='adsbygoogle' style='display:block' data-ad-client='{GOOGLE_ADSENSE_CLIENT}' data-ad-slot='{GOOGLE_ADSENSE_SLOT}' data-ad-format='auto' data-full-width-responsive='true'></ins></div>"
    post_body += adsense_code

    try:
        creds_bytes = base64.b64decode(token_base64)
        credentials = pickle.loads(creds_bytes)
        
        blogger_service = build('blogger', 'v3', credentials=credentials)
        
        publish_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
        scheduled_time = publish_time.strftime('%Y-%m-%dT%H:%M:%SZ')

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
