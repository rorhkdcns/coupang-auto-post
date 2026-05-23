import os
import sys
import subprocess
import time
import re
import random

# [1단계] 라이브러리 자동 설치 및 검증
required_modules = [
    "google-auth-oauthlib", 
    "google-auth-httplib2", 
    "google-api-python-client", 
    "google-genai",
    "requests"
]

print("🔄 깃허브 액션 서버 환경 내 라이브러리 자동 설치 시작...")
for module in required_modules:
    try:
        if module == "google-genai":
            import google.genai
        else:
            __import__(module.replace('-', '_'))
    except ImportError:
        print(f"📦 {module} 설치 중...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", module])
        time.sleep(1)

print("✅ 모든 라이브러리 설치 및 인식 완료! 쿠팡 전용 자동화를 시작합니다.")
print("-" * 60)

import pickle
import base64
import datetime
import urllib.parse
import html
import requests
import hmac
import hashlib
from googleapiclient.discovery import build
from google import genai 
from google.genai import types  

# =====================================================================
# ⚙️ 고유 설정 정보
# =====================================================================
BLOG_ID = "8715372631292128719"  
GOOGLE_ADSENSE_CLIENT = "ca-pub-4292478378917157"
GOOGLE_ADSENSE_SLOT = "5317754949"

COUPANG_ACCESS_KEY = os.environ.get("COUPANG_ACCESS_KEY", "")
COUPANG_SECRET_KEY = os.environ.get("COUPANG_SECRET_KEY", "")

# 🎯 [자동 순환 키워드 풀] 실행될 때마다 이 중 하나를 랜덤 선정해 콘텐츠화합니다.
SUGGESTED_KEYWORDS = [
   "생수"
]

def generate_coupang_hmac(method, url, secret_key, access_key):
    path, _, query = url.partition('?')
    datetime_gmt = datetime.datetime.utcnow().strftime('%y%m%dT%H%M%SZ')
    message = datetime_gmt + method + path + query
    signature = hmac.new(bytes(secret_key, "utf-8"), msg=bytes(message, "utf-8"), digestmod=hashlib.sha256).hexdigest()
    authorization = f"CEA algorithm=HmacSHA256, accessKey={access_key}, signedDate={datetime_gmt}, signature={signature}"
    return authorization, datetime_gmt

def fetch_coupang_products(keyword, limit=3):
    """쿠팡에서 타겟 키워드로 상위 N개의 상품 데이터를 긁어옵니다."""
    if not COUPANG_ACCESS_KEY or not COUPANG_SECRET_KEY:
        print("⚠️ 쿠팡 API 키 누락. 디버그용 샘플 데이터를 반환합니다.")
        return [
            {"title": f"🏆 프리미엄 {keyword} 추천형 A형", "link": "https://link.coupang.com", "image": "https://placehold.co/150x150/e2e8f0/475569/png?text=Product+A", "price": "49,000"},
            {"title": f"🔥 가성비 끝판왕 {keyword} B형", "link": "https://link.coupang.com", "image": "https://placehold.co/150x150/e2e8f0/475569/png?text=Product+B", "price": "29,900"},
            {"title": f"⭐ 실사용 만족도 1위 {keyword} C형", "link": "https://link.coupang.com", "image": "https://placehold.co/150x150/e2e8f0/475569/png?text=Product+C", "price": "35,500"},
        ]
    
    encoded_keyword = urllib.parse.quote(keyword)
    domain = "https://api-gateway.coupang.com"
    url_path = f"/v2/providers/coupang_partners/api/v1/products/search?keyword={encoded_keyword}&limit={limit}"
    
    auth_header, date_gmt = generate_coupang_hmac("GET", url_path, COUPANG_SECRET_KEY, COUPANG_ACCESS_KEY)
    headers = {
        "Authorization": auth_header,
        "X-Requested-With": date_gmt,
        "Content-Type": "application/json;charset=UTF-8"
    }
    
    try:
        res = requests.get(domain + url_path, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            products = data.get("data", {}).get("productData", [])
            if products:
                result = []
                for prod in products:
                    result.append({
                        "title": prod.get("productName"),
                        "link": prod.get("productUrl"),
                        "image": prod.get("productImage"),
                        "price": f"{prod.get('productPrice'):,}"
                    })
                return result
    except Exception as e:
        print(f"❌ 쿠팡 API 파싱 실패: {e}")
        
    return []

def calculate_scheduled_time():
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(kst) 
    today = now.date()
    candidates = [
        datetime.datetime.combine(today, datetime.time(9, 0), tzinfo=kst),
        datetime.datetime.combine(today, datetime.time(13, 0), tzinfo=kst),
        datetime.datetime.combine(today, datetime.time(16, 0), tzinfo=kst),
        datetime.datetime.combine(today, datetime.time(20, 0), tzinfo=kst)
    ]
    scheduled_time = None
    for c in candidates:
        if c > now: 
            scheduled_time = c
            break
    if not scheduled_time:
        tomorrow = today + datetime.timedelta(days=1)
        scheduled_time = datetime.datetime.combine(tomorrow, datetime.time(9, 0), tzinfo=kst)
        
    return scheduled_time.strftime('%Y-%m-%dT%H:%M:%S+09:00')

# 구글 애드센스 문자열 치환 안전코드 처리 완료
ADSENSE_TEMPLATE = """<div class="adsense-container" style="text-align:center; margin: 30px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={CLIENT}" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client={CLIENT} data-ad-slot={SLOT} data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({});</script></div>"""
ADSENSE_CODE = ADSENSE_TEMPLATE.replace("{CLIENT}", f'"{GOOGLE_ADSENSE_CLIENT}"').replace("{SLOT}", f'"{GOOGLE_ADSENSE_SLOT}"')

# =====================================================================
# ✍️ Gemini 프롬프트 고도화 (쿠팡 전용 상품 큐레이션 가이드)
# =====================================================================
def generate_product_review_content(keyword, products):
    api_key_direct = os.environ.get("API_KEY")
    client = genai.Client(
        api_key=api_key_direct,
        http_options=types.HttpOptions(api_version="v1")
    )
    
    prod_context = ""
    for i, p in enumerate(products):
        prod_context += f"[상품 {i+1}]\n명칭: {p['title']}\n가격: {p['price']}원\n\n"

    prompt = (
        f"너는 가전/리뷰 전문 이커머스 카피라이터이자 블로그 마케팅 전문가야.\n"
        f"제공된 핵심 키워드인 '{keyword}'와 관련된 실시간 쿠팡 상품 리스트를 바탕으로, "
        f"단순 광고가 아니라 소비자에게 신뢰를 주는 '구매 가이드 및 비교 추천 콘텐츠'를 작성해라.\n\n"
        f"[제공된 쿠팡 실시간 상품 정보]\n{prod_context}"
        f"[필수 작성 지침]\n"
        f"1. [★제목 법칙★]: 실전 SEO 키워드와 후킹 메시지를 조합하여 클릭을 유도해라. (예: '내돈내산 아깝지 않은 {keyword} 추천 TOP 3 비교, 구매 전 필독')\n"
        f"2. 전체 구조는 철저히 PASONA 기법을 따른다.\n"
        f"   - 파트 1 (P-A): 소비자가 이 상품을 검색하기까지 겪는 일상적인 불편함(Problem)과 스트레스 자극(Agitation).\n"
        f"   - 파트 2 (S-O): 해결책(Solution)으로서 해당 카테고리 상품을 고르는 기준 제시 및 각 상품별 특장점 요약(Offer).\n"
        f"   - 파트 3 (N-A): 지금 사야 하는 이유(Narrow)와 구매를 망설이지 않게 하는 행동 촉구(Action).\n"
        f"   - 단, 파소나, AI, 인공지능 단어는 절대 노출 금지.\n"
        f"3. 모바일 가독성을 위해 문장 단위로 줄바꿈을 철저히 하고 단락당 2~3줄의 간격을 유지해라.\n"
        f"4. 가장 중요한 소구점, 스펙, 장점 키워드는 반드시 <b><font color=\"#e11d48\">강조문구</font></b> 양식으로만 감싸라.\n"
        f"5. 영문 이미지 프롬프트(IMAGE_PROMPT)와 블로그 검색 태그(TAGS) 3~5개를 반드시 포맷에 맞춰 추출해라.\n\n"
        f"[출력 포맷 고정]\n"
        f"[TITLE]: 제목 정보\n"
        f"[TAGS]: 태그1, 태그2, 태그3\n"
        f"[IMAGE_PROMPT]: lifestyle laptop setup\n"
        f"[SUB_TITLE_1]: 소제목1 (불편함과 공감대 형성)\n"
        f"[BODY_1]: 내용1 (반드시 <b><font color=\"#e11d48\">강조문구</font></b> 포함)\n"
        f"[SUB_TITLE_2]: 소제목2 (실패 없는 선택 기준)\n"
        f"[BODY_2]: 내용2 (반드시 <b><font color=\"#e11d48\">강조문구</font></b> 포함)\n"
        f"[SUB_TITLE_3]: 소제목3 (합리적인 소비를 위한 최종 제안)\n"
        f"[BODY_3]: 내용3 (반드시 <b><font color=\"#e11d48\">강조문구</font></b> 포함)\n"
        f"[PROD_DESC_1]: 첫 번째 상품의 상세 셀링 포인트 요약 (2-3문장)\n"
        f"[PROD_DESC_2]: 두 번째 상품의 상세 셀링 포인트 요약 (2-3문장)\n"
        f"[PROD_DESC_3]: 세 번째 상품의 상세 셀링 포인트 요약 (2-3문장)"
    )
    
    target_models = ['gemini-2.5-flash', 'gemini-2.5-pro']
    for target_model in target_models:
        for attempt in range(3):
            try:
                print(f"🤖 Gemini API 호출 중... (모델: {target_model})")
                response = client.models.generate_content(model=target_model, contents=prompt)
                if response and response.text:
                    return response.text
            except Exception as e:
                print(f"⚠️ API 대기 중... 원인: {e}")
                if attempt < 2: time.sleep(10)
                    
    raise RuntimeError("🚨 블로그 콘텐츠 파싱 및 생성 실패")

def clean_html_garbage(text):
    text = text.replace('`', '').replace('**', '').replace('__', '')
    text = text.replace('<span>', '').replace('</span>', '')
    text = re.sub(r'<\s*span[^>]*>', '', text) 
    text = re.sub(r'\[.*?\]\s*:\s*', '', text)
    return text.strip()

# =====================================================================
# 🎨 가독성 극대화 상품 배너 렌더러 (Phase 3)
# =====================================================================
def make_html_product_card(prod, desc, index):
    """쿠팡 상품 단일 개체를 매력적인 UI 카드로 빌드"""
    card_html = f"""
    <div class="product-card-{index}" style="margin: 30px auto; padding: 22px; border: 1px solid #e2e8f0; border-radius: 16px; background-color: #ffffff; box-shadow: 0 4px 12px rgba(0,0,0,0.03); max-width: 580px; font-family: -apple-system, sans-serif;">
        <span style="display:inline-block; background:#e11d48; color:white; font-size:11px; font-weight:bold; padding:3px 9px; border-radius:20px; margin-bottom:12px;">실시간 추천 상품 {index}</span>
        <div style="display: flex; gap: 20px; align-items: flex-start;">
            <div style="flex-shrink: 0; width: 130px; height: 130px; background: #f8fafc; border-radius: 12px; overflow: hidden; display: flex; align-items: center; justify-content: center; border: 1px solid #f1f5f9;">
                <img src="{prod['image']}" alt="{prod['title']}" style="max-width: 100%; max-height: 100%; object-fit: contain;" />
            </div>
            <div style="flex-grow: 1;">
                <h4 style="margin: 0 0 8px 0; font-size: 15px; font-weight: 800; color: #0f172a; line-height: 1.4;">{prod['title']}</h4>
                <p style="margin: 0 0 10px 0; font-size: 13px; color: #475569; line-height: 1.5;">{desc}</p>
                <div style="display: flex; align-items: center; justify-content: space-between; margin-top: 15px;">
                    <span style="font-size: 18px; font-weight: 900; color: #dc2626;">{prod['price']}원</span>
                    <a href="{prod['link']}" target="_blank" rel="nofollow noopener noreferrer" style="background: #0f172a; color: white; padding: 9px 16px; border-radius: 8px; font-size: 12px; font-weight: bold; text-decoration: none;">최저가 보러가기 ➔</a>
                </div>
            </div>
        </div>
    </div>
    """
    return card_html

def main():
    b64_token = os.environ.get("TOKEN_PICKLE_BASE64")
    if not b64_token:
        print("❌ 에러: TOKEN_PICKLE_BASE64가 누락되었습니다.")
        return
        
    creds = pickle.loads(base64.b64decode(b64_token))
    blogger = build('blogger', 'v3', credentials=creds)
    
    target_keyword = random.choice(SUGGESTED_KEYWORDS)
    print(f"🎯 [아이템 소싱] 이번 포스팅 카테고리 테마: {target_keyword}")
    
    coupang_list = fetch_coupang_products(target_keyword, limit=3)
    if not coupang_list:
        print("🚨 소싱된 쿠팡 상품이 없어 프로세스를 홀딩합니다.")
        return
        
    ai_raw = generate_product_review_content(target_keyword, coupang_list)
    
    def re_extract_line(tag, text, default=""):
        pattern = r'\[?' + re.escape(tag) + r'\]?\s*:\s*(.*)'
        for line in text.split('\n'):
            if tag in line:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    return match.group(1).strip()
        return default

    title = re_extract_line('TITLE', ai_raw, f"합리적인 선택을 위한 {target_keyword} 추천 가이드")
    title = re.sub(r'<[^>]*>', '', title).replace('`', '').replace('**', '').replace('__', '').strip()
    
    tags_raw = re_extract_line('TAGS', ai_raw, "쿠팡파트너스, 상품추천, 가성비템")
    img_prompt = re_extract_line('IMAGE_PROMPT', ai_raw, "shopping setup").upper()
    
    sub1 = re_extract_line('SUB_TITLE_1', ai_raw, "💡 혹시 이런 불편함을 겪고 계시진 않나요?")
    sub2 = re_extract_line('SUB_TITLE_2', ai_raw, "📋 실패 없는 제품을 고르는 가이드")
    sub3 = re_extract_line('SUB_TITLE_3', ai_raw, "✨ 현명한 소비를 위한 최종 요약")
    
    def extract_block(text, start_tag, end_tag=None):
        try:
            start_idx = text.find(start_tag)
            if start_idx == -1: return ""
            start_idx += len(start_tag)
            if end_tag:
                end_idx = text.find(end_tag)
                return text[start_idx:end_idx].strip() if end_idx != -1 else text[start_idx:].strip()
            return text[start_idx:].strip()
        except:
            return ""

    body1 = clean_html_garbage(extract_block(ai_raw, '[BODY_1]:', '[SUB_TITLE_2]'))
    body2 = clean_html_garbage(extract_block(ai_raw, '[BODY_2]:', '[SUB_TITLE_3]'))
    body3 = clean_html_garbage(extract_block(ai_raw, '[BODY_3]:', '[PROD_DESC_1]'))
    
    desc1 = clean_html_garbage(extract_block(ai_raw, '[PROD_DESC_1]:', '[PROD_DESC_2]'))
    desc2 = clean_html_garbage(extract_block(ai_raw, '[PROD_DESC_2]:', '[PROD_DESC_3]'))
    desc3 = clean_html_garbage(extract_block(ai_raw, '[PROD_DESC_3]:'))

    tags = [t.strip() for t in tags_raw.replace('`','').replace('**','').split(',') if t.strip()]
    
    encoded_text = urllib.parse.quote(f"BEST BUY: {img_prompt}")
    thumbnail_url = f"https://placehold.co/800x450/0f172a/ffffff/png?text={encoded_text}&font=playfair"
    
    b1_html = body1.replace('\n', '<br>')
    b2_html = body2.replace('\n', '<br>')
    b3_html = body3.replace('\n', '<br>')

    card1_code = make_html_product_card(coupang_list[0], desc1, 1)
    card2_code = make_html_product_card(coupang_list[1], desc2, 2)
    card3_code = make_html_product_card(coupang_list[2], desc3, 3)

    final_html = f"""
    <div style="text-align:center; margin-bottom:30px;">
        <img src="{thumbnail_url}" alt="{target_keyword} Guide" style="max-width:100%; height:auto; border-radius:12px; box-shadow: 0 4px 10px rgba(0,0,0,0.05);"/>
    </div>
    
    <h3 style="font-size: 20px; color: #0f172a; border-left: 5px solid #e11d48; padding-left: 10px; margin-top: 35px; margin-bottom: 20px;">{sub1}</h3>
    <div class="post-p1" style="font-size:16px; line-height:1.9; color:#334155; margin-bottom: 25px; letter-spacing: -0.3px;">{b1_html}</div>
    
    {ADSENSE_CODE}
    
    <h3 style="font-size: 20px; color: #0f172a; border-left: 5px solid #e11d48; padding-left: 10px; margin-top: 35px; margin-bottom: 20px;">{sub2}</h3>
    <div class="post-p2" style="font-size:16px; line-height:1.9; color:#334155; margin-bottom: 25px; letter-spacing: -0.3px;">{b2_html}</div>
    
    {card1_code}
    {card2_code}
    {card3_code}
    
    <h3 style="font-size: 20px; color: #0f172a; border-left: 5px solid #e11d48; padding-left: 10px; margin-top: 35px; margin-bottom: 20px;">{sub3}</h3>
    <div class="post-p3" style="font-size:16px; line-height:1.9; color:#334155; margin-bottom: 25px; letter-spacing: -0.3px;">{b3_html}</div>
    
    {ADSENSE_CODE}
    
    <p style="margin: 40px 0 0 0; font-size: 11px; color: #94a3b8; text-align: center; line-height: 1.4; border-top: 1px solid #f1f5f9; padding-top: 20px;">
        이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.
    </p>
    """

    scheduled_publish_time = calculate_scheduled_time()

    post_data = {
        'title': title,
        'content': final_html,
        'labels': tags,
        'published': scheduled_publish_time
    }
    
    try:
        posts_service = blogger.posts()
        request = posts_service.insert(blogId=BLOG_ID, body=post_data, isDraft=False)
        created_post = request.execute()
        print(f"✅ [쿠팡 자동화 업로드 성공] 블로그에 완벽하게 등록되었습니다: {created_post.get('title')}")
    except Exception as api_err:
        print(f"❌ 구글 API 전송 오류: {api_err}")

if __name__ == "__main__":
    main()
