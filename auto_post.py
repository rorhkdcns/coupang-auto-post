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

[1. 페르소나 및 집필 원칙 (어뷰징 방지 핵심)]
- 인간적인 에세이 톤 유지: 기계적인 설명조(~했던 경험 다들 있으실 거예요 등)를 완전 배제하고, 실제 블로그 주인이 직접 일상에서 겪은 불편함을 독백하듯 친근한 구어체로 작성하세요.
- 패턴의 무작위화(Randomization): 매번 똑같은 서론/결론 구조가 나오지 않도록 문장의 시작점과 전개 방식을 유연하게 바꾸어야 합니다.
- 중복 금지 (🚨최우선 엄격 제한): 동일한 단어나 문장, 문단이 토씨 하나 틀리지 않고 본문 내에서 연속으로 절대 반복 출력되지 않도록 문장 생성을 엄격히 통제하세요.

[2. 담백한 PASONA 글 전개 프로세스]
이론적인 단어(고민, 해결 등)는 절대 노출하지 말고, 아래의 흐름이 자연스러운 하나의 스토리로 연결되게 하세요.
- 1단계 (Problem): 일상에서 누구나 겪지만 무심코 넘어갔던 '불편한 순간'이나 '손해 보는 상황'을 콕 짚어 대화를 건냅니다.
- 2단계 (Affinity): "저도 처음엔 그랬다"며 독자의 상황에 깊이 공감하고 위로합니다.
- 3단계 (Solution): 그 문제를 깔끔하게 해결해 준 현실적인 기준과 대안(제품)을 제시합니다.
- 4단계 (Benefit): 이 제품을 썼을 때 삶이 얼마나 쾌적해지는지, 혹은 비용/시간이 얼마나 아껴지는지 가장 핵심적인 혜택을 강조합니다.
- 5단계 (Action): 과장된 영업 멘트 없이, "더 이상 스트레스받지 마시고 확인해 보세요"라며 자연스럽게 정보를 공유하듯 행동을 유도합니다.

[3. HTML 및 포맷 디자인 요구사항 (디테일 100% 준수 필수)]
1. 💡 제목 작성 규칙: 첫 줄은 무조건 '제목: 호기심 유발 제목' 형식으로 작성하세요. 뻔한 추천/리스트형 제목은 절대 금지합니다. 타겟의 페인 포인트를 날카롭게 찌르거나 손실 회피 심리를 자극하세요. (🚨주의: 제목에 대괄호 [ ] 기호는 절대 사용 금지!)
2. 🚨 순수 HTML만 사용: 마크다운 기호(예: **글씨**, # 제목)는 절대 사용하지 마세요. 오직 순수 HTML 태그만 사용해야 합니다.
3. 시원한 여백 확보: 글이 빽빽해 보이지 않도록 문장 1~2개 단위로 과감하게 문단을 나누세요. 단락 사이 여백은 <p style="line-height: 1.8; margin-bottom: 25px;">를 사용하여 시원하게 확보합니다.
4. 소제목 스타일 고정: 본문보다 확실히 크게 보이도록 아래 태그를 토씨 하나 틀리지 말고 그대로 사용하세요.
   <h3 style="font-size: 22px; font-weight: bold; color: #333; border-bottom: 2px solid #FF1493; padding-bottom: 8px; margin-top: 40px; margin-bottom: 20px;">소제목 텍스트</h3>
5. 엄격한 컬러 규칙:
   - 가격: 반드시 빨간색 두꺼운 글씨로 딱 한 번만 표기하세요. <strong style="color:#E52528;">00,000원</strong>
   - 핵심 포인트: 반드시 핑크색 두꺼운 글씨로 표기하세요. <strong style="color:#FF1493;">가장 중요한 혜택이나 포인트</strong>

[4. 🚨 절대 규칙: 이미지와 버튼의 미니멀 배치 (도배 금지)]
- 각 상품을 소개할 때 제공된 [[IMAGE_번호]]와 [[BUTTON_번호]] 같은 기호를 텍스트 그대로 본문에 입력하세요. 임의로 <img ...> 나 <a ...> 태그를 만들어내면 안 됩니다.
- 과도한 링크 방지: 하나의 상품당 이미지 기호 1개, 버튼 기호 1개만 깔끔하게 배치해야 합니다. 
  - [[IMAGE_번호]]는 각 상품 설명이 시작되는 최상단에 딱 1번 위치합니다.
  - [[BUTTON_번호]]는 각 상품 설명 및 가격 표기가 모두 끝나는 최하단에 딱 1번 위치합니다.
  - 주변에 불필요한 배너나 링크 문구를 중복으로 채우지 말고 미니멀하게 정리하여 스팸 필터링을 회피하세요.
- 안내 문구 제외: 쿠팡 파트너스 안내 문구는 별도로 삽입되므로 본문 내용 작성에만 집중하세요.

[TAGS_EXTRACT]: 본문 내용과 밀접한 마케팅용 키워드 태그를 3개 추출하시오 (예시: 쇼핑추천, 살림템, 가성비제품)

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

    # 🔗 [추천글 상시 노출을 위한 라벨 누적 방어 시스템 가동]
    ai_tags = []
    tag_match = re.search(r'\[TAGS_EXTRACT\]\s*:\s*(.*)', ai_content, re.IGNORECASE)
    if tag_match:
        ai_tags = [t.strip() for t in tag_match.group(1).split(',') if t.strip()]
        
    fixed_shopping_tags = ['쇼핑추천', '리뷰', '추천템']
    final_labels = list(set(ai_tags + fixed_shopping_tags))

    # 본문 기호 치환
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
            
    # 원고 본문 빌드 및 지저분한 HTML 기호 클렌징 적용
    raw_body_text = "\n".join(lines[content_start_idx:])
    cleaned_body_text = clean_html_garbage(raw_body_text)
    
    # 🛡️ [HTML 무결성 3등분 자동 방어 장치] 쿠팡 글에도 적용하여 태그 깨짐 전면 차단
    paragraphs = [p.strip() for p in cleaned_body_text.split('\n') if p.strip()]
    total_p = len(paragraphs)
    
    if total_p >= 3:
        size = total_p // 3
        part1 = "\n\n".join(paragraphs[:size])
        part2 = "\n\n".join(paragraphs[size:size*2])
        part3 = "\n\n".join(paragraphs[size*2:])
    else:
        part1 = cleaned_body_text
        part2 = ""
        part3 = ""

    # 줄바꿈 변환 적용 후 바인딩
    b1_html = part1.replace('\n', '<br>')
    b2_html = f"<br><br>{part2.replace('\n', '<br>')}" if part2 else ""
    b3_html = f"<br><br>{part3.replace('\n', '<br>')}" if part3 else ""
    
    # 순수 본문 결합
    post_body += f'<div class="post-p1" style="font-size:16px; line-height:1.9; color:#334155; letter-spacing: -0.3px;">{b1_html}{b2_html}{b3_html}</div>'

    # 하단 애드센스 코드 배치
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
            "labels": final_labels,  
            "published": scheduled_time
        }
        
        blogger_service.posts().insert(blogId=BLOG_ID, body=new_post, isDraft=False).execute()
        print(f"🎯 [성공] '{title}' 예약글 발행 완료 (발행 예정 시각: {scheduled_time})")
    except Exception as e:
        print(f"❌ 구글 블로그 업로드 에러: {str(e)}")

if __name__ == "__main__":
    main()
