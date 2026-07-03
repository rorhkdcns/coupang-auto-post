import base64
import datetime
import hashlib
import hmac
import io
import json
import os
import pickle
import random
import re
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import warnings
from pathlib import Path

warnings.filterwarnings("ignore", category=FutureWarning)

required_modules = [
    "requests", "google-auth-oauthlib", "google-auth-httplib2", 
    "google-api-python-client", "google-genai", "Pillow"
]

for module in required_modules:
    try:
        if module == "google-genai": import google.genai
        elif module == "Pillow": import PIL
        else: __import__(module.replace('-', '_'))
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", module])
        time.sleep(1)

import requests
from PIL import Image, ImageDraw, ImageFont
from google import genai
from google.genai import types
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# =====================================================================
# ⚙️ [고유 설정 정보]
# =====================================================================
TEST_MODE = True

BLOG_ID = "8715372631292128719"  
GOOGLE_ADSENSE_CLIENT = "ca-pub-4292478378917157"
GOOGLE_ADSENSE_SLOT = "7988651325"

BLOG_DOMAIN = "blogspot.com"
GITHUB_USER_ID = "rorhkdcns"
GITHUB_REPO_NAME = (os.environ.get("GITHUB_REPOSITORY") or "rorhkdcns/blogger-auto-post").split("/")[-1]

def get_coupang_v2_products(access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    path = "/v2/providers/affiliate_open_api/apis/openapi/v2/products/reco"
    req_data = {
        "site": {"domain": BLOG_DOMAIN, "id": BLOG_ID},
        "device": {"id": "DESKTOP_ID", "ip": "127.0.0.1", "lmt": 0, "ua": "Mozilla/5.0"},
        "imp": {"ad_type": 2, "imageSize": "180x180", "placementid": "blog_main", "pos": 1},
        "user": {"puid": "blogger_user"}
    }
    gmt_now = datetime.datetime.now(datetime.timezone.utc)
    datetime_gmt = gmt_now.strftime('%y%m%dT%H%M%SZ')
    message = datetime_gmt + "POST" + path
    signature = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256).hexdigest()
    authorization_header = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

    headers = {"Content-Type": "application/json", "Authorization": authorization_header}
    try:
        res = requests.post(f"{domain}{path}", headers=headers, json=req_data, timeout=10)
        if res.status_code != 200: return []
        res_json = res.json()
        data_node = res_json.get("data")
        products_list = data_node if isinstance(data_node, list) else (data_node.get("result", []) or data_node.get("recoProducts", []) or data_node.get("products", []))
        return products_list[:4] 
    except Exception as e:
        print(f"💥 쿠팡 V2 통신 예외: {str(e)}")
        return []

def check_already_posted(blogger, blog_id):
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(kst)
    try:
        for status_type in ['LIVE', 'SCHEDULED']:
            posts = blogger.posts().list(blogId=blog_id, maxResults=10, status=status_type).execute()
            for item in posts.get('items', []):
                up_str = item.get('updated', '') 
                if up_str:
                    up_time = datetime.datetime.fromisoformat(up_str.replace('Z', '+00:00')).astimezone(kst)
                    if 0 <= (now - up_time).total_seconds() / 60 < 30.0:
                        print(f"⏳ 최근 30분 내 포스팅({status_type}) 감지. 중복 차단.")
                        return True
    except Exception as e: print(f"⚠️ 중복 체크 에러: {e}")
    return False

def create_pil_card(prod_name, price_str, card_bullets):
    """★ 절대 실패하지 않는 PIL 카드 생성 (시원시원한 큰 글씨 버전)"""
    try:
        print("🎨 PIL 카드 생성 중...")
        
        try:
            font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
            font_path = "/tmp/font.ttf"
            if not os.path.exists(font_path):
                urllib.request.urlretrieve(font_url, font_path)
            title_font = ImageFont.truetype(font_path, 64)
            price_font = ImageFont.truetype(font_path, 74)
            bullet_font = ImageFont.truetype(font_path, 34)
            badge_font = ImageFont.truetype(font_path, 30)
        except:
            title_font = price_font = bullet_font = badge_font = ImageFont.load_default()

        card = Image.new('RGB', (1200, 630), color='#FFFFFF')
        draw = ImageDraw.Draw(card)
        
        for y in range(630):
            val = int(255 - y * 0.05)
            draw.line([(0, y), (1200, y)], fill=(val, val, val))
        
        draw.rectangle([0, 0, 10, 630], fill='#E52528', width=0)
        
        draw.rectangle([60, 40, 310, 100], fill='#E52528', width=0)
        draw.text((185, 70), "COUPANG PICK", fill='#FFFFFF', font=badge_font, anchor="mm")
        
        clean_name = prod_name if len(prod_name) <= 28 else prod_name[:28] + "..."
        draw.text((90, 175), clean_name, fill='#1e293b', font=title_font, anchor="lm")
        
        draw.text((90, 295), price_str, fill='#E52528', font=price_font, anchor="lm")
        
        draw.line([(90, 345), (1100, 345)], fill='#E2E8F0', width=3)
        
        start_y = 400
        for i, bullet in enumerate(card_bullets[:3]):
            draw.ellipse([75, start_y-20, 133, start_y+38], fill='#E52528', width=0)
            draw.text((104, start_y+9), str(i+1), fill='#FFFFFF', font=bullet_font, anchor="mm")
            draw.text((155, start_y+9), bullet[:20], fill='#334155', font=bullet_font, anchor="lm")
            start_y += 80

        file_name = f"card_{int(time.time())}_{random.randint(1000, 9999)}.webp"
        card.save(file_name, "WEBP", quality=92)
        print(f"✅ PIL 카드 로컬 생성 완료: {file_name}")
        return file_name, True
        
    except Exception as e:
        print(f"❌ PIL 카드 생성 실패: {e}")
        return None, False

def upload_image_to_github(file_path):
    """이미지를 GitHub에 업로드"""
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token:
        print("⚠️ GitHub 토큰 없음, 로컬 파일만 유지")
        return None
    
    try:
        with open(file_path, "rb") as f:
            encoded = base64.b64encode(f.read()).decode("utf-8")
        
        file_name = os.path.basename(file_path)
        git_path = f"blog_images/cards/{file_name}"
        url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
        headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
        
        res = requests.put(
            url,
            headers=headers,
            json={"message": f"Card: {file_name}", "content": encoded, "branch": "main"},
            timeout=10
        )
        
        if res.status_code in [200, 201]:
            cdn_url = f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
            print(f"✅ GitHub 업로드 성공: {cdn_url}")
            return cdn_url
    except Exception as e:
        print(f"⚠️ GitHub 업로드 실패: {e}")
    
    return None

def get_clean_title(raw_title):
    """제목 정제: 중복 제거, 길이 조정"""
    clean = raw_title.replace("휴대폼", "휴대용")
    
    words = clean.split()
    seen = set()
    unique_words = []
    for word in words:
        if word not in seen:
            unique_words.append(word)
            seen.add(word)
    
    clean = " ".join(unique_words)
    
    if len(clean) > 45:
        clean = clean[:42] + "..."
    
    return clean

def markdown_table_to_html(markdown_table):
    """마크다운 표를 HTML 표로 변환"""
    if not markdown_table or not markdown_table.strip():
        return ""
    
    lines = [line.strip() for line in markdown_table.split('\n') if line.strip() and line.strip().startswith('|')]
    if len(lines) < 2:
        return ""
    
    html = '<table style="border-collapse: collapse; width: 100%; margin: 0 auto; text-align: center; border: 2px solid #cbd5e1;">'
    
    header_cells = [cell.strip() for cell in lines[0].split('|')[1:-1]]
    html += '<thead><tr style="background-color: #f1f5f9;">'
    for cell in header_cells:
        html += f'<th style="border: 1px solid #cbd5e1; padding: 14px 10px; font-weight: bold; color: #1e293b; text-align: center; font-size: 16px;">{cell}</th>'
    html += '</tr></thead>'
    
    html += '<tbody>'
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        html += '<tr>'
        for cell in cells:
            html += f'<td style="border: 1px solid #cbd5e1; padding: 12px 10px; color: #475569; text-align: center; font-size: 15px;">{cell}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    
    return html

def format_content(text):
    """본문 포맷팅: 리스트, 제목, 표 처리"""
    if not text or not text.strip(): 
        return ""
    
    text = re.sub(r'\*\*(.*?)\*\*', r'<span style="color:#E52528; font-weight:bold;">\1</span>', text)
    
    chunks = []
    lines = text.split('\n')
    in_list = False
    
    for line in lines:
        line = line.rstrip()
        
        if not line.strip():
            if in_list:
                chunks.append('</ul>')
                in_list = False
            chunks.append('<div style="height: 20px;"></div>')
            continue
        
        if line.startswith(('🎯', '⚠️', '💡', '🔍', '✨', '📋')):
            if in_list:
                chunks.append('</ul>')
                in_list = False
            chunks.append(f'<h4 style="font-size: 20px; font-weight: bold; color: #1e293b; margin: 30px 0 16px 0; text-align: center; border-bottom: 2px solid #E52528; padding-bottom: 8px; display: inline-block; width: 100%;">{line}</h4>')
            continue
        
        if line.strip().startswith(('•', '-', '◆', '▶')):
            if not in_list:
                chunks.append('<ul style="margin: 16px auto; padding-left: 0; list-style-type: none; text-align: center; display: inline-block;">')
                in_list = True
            list_text = re.sub(r'^[•\-◆▶]\s*', '', line.strip())
            chunks.append(f'<li style="margin-bottom: 10px; color: #475569; font-size: 17px; line-height: 1.6; text-align: left; margin-left: 30px;">{list_text}</li>')
            continue
        
        if line.startswith('|'):
            if in_list:
                chunks.append('</ul>')
                in_list = False
            table_html = markdown_table_to_html(line)
            if table_html:
                chunks.append(f'<div style="margin: 30px auto; overflow-x: auto; width: 95%;">{table_html}</div>')
            continue
        
        if in_list:
            chunks.append('</ul>')
            in_list = False
        
        chunks.append(f'<p style="text-align: center; font-size: 17px; line-height: 1.9; margin-bottom: 16px; color: #334155;">{line.strip()}</p>')
    
    if in_list:
        chunks.append('</ul>')
    
    return "".join(chunks)

def generate_adsense_html():
    """Google AdSense"""
    return f'<div style="margin: 40px 0; text-align: center;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={GOOGLE_ADSENSE_CLIENT}" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="{GOOGLE_ADSENSE_CLIENT}" data-ad-slot="{GOOGLE_ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></div>'

# [신규] 목차(TOC) 박스
def build_toc_html():
    return '''
<div style="max-width: 500px; margin: 30px auto; background:#fff5f5; border:1px solid #fecaca; border-radius:12px; padding:20px 24px; text-align:left;">
    <p style="font-weight:700; font-size:16px; color:#1e293b; margin:0 0 12px 0; text-align:center;">📋 목차</p>
    <ul style="margin:0; padding-left:20px; font-size:16px; color:#334155; line-height:2;">
        <li><a href="#spec" style="color:#E52528; text-decoration:none;">주요 스펙</a></li>
        <li><a href="#proscons" style="color:#E52528; text-decoration:none;">장점과 단점</a></li>
        <li><a href="#verdict" style="color:#E52528; text-decoration:none;">추천 대상</a></li>
        <li><a href="#faq" style="color:#E52528; text-decoration:none;">자주 묻는 질문</a></li>
        <li><a href="#conclusion" style="color:#E52528; text-decoration:none;">결론</a></li>
    </ul>
</div>
'''

# [신규] 섹션별 "✅ 요약" 박스
def make_section_summary(text):
    if not text or not text.strip(): return ""
    return f'''
<div style="max-width: 500px; margin: 20px auto 10px auto; background:#fff5f5; border:1px solid #fecaca; border-radius:10px; padding:14px 20px; text-align:left;">
    <p style="margin:0; font-size:15px; color:#E52528; font-weight:700;">✅ 요약</p>
    <p style="margin:6px 0 0 0; font-size:16px; color:#334155; line-height:1.6;">{text}</p>
</div>
'''

# [신규] FAQ 섹션
def build_faq_html(faq_list):
    if not faq_list: return ""
    items = ""
    for item in faq_list:
        q = (item.get("question") or "").strip()
        a = (item.get("answer") or "").strip()
        if not q or not a: continue
        items += f'''
        <div style="margin-bottom:20px; text-align:left;">
            <p style="font-weight:700; font-size:17px; color:#1e293b; margin:0 0 6px 0;">Q. {q}</p>
            <p style="font-size:16px; color:#475569; line-height:1.7; margin:0;">A. {a}</p>
        </div>'''
    if not items: return ""
    return f'''
<h3 id="faq" style="font-size: 21px; font-weight: bold; color: #1e293b; margin: 48px 0 24px 0; display: inline-block; border-bottom: 3px solid #E52528; padding-bottom: 8px;">❓ 자주 묻는 질문</h3>
<div style="max-width:600px; margin:20px auto 0 auto;">{items}</div>
'''

# [신규] 결론 섹션
def build_conclusion_html(conclusion_text):
    if not conclusion_text or not conclusion_text.strip(): return ""
    return f'<h3 id="conclusion" style="font-size: 21px; font-weight: bold; color: #1e293b; margin: 48px 0 24px 0; display: inline-block; border-bottom: 3px solid #E52528; padding-bottom: 8px;">🏁 결론</h3>{format_content(conclusion_text)}'

def validate_ai_data(ai_data):
    """AI 응답 검증"""
    required_fields = ['title', 'slug', 'hook_intro', 'spec_table', 'pros_cons_body', 'verdict', 'card_bullets', 'tags', 'faq', 'conclusion']
    
    for field in required_fields:
        if field not in ai_data or not ai_data[field]:
            print(f"⚠️ 필수 필드 누락: {field}")
            return False
    
    if not isinstance(ai_data['card_bullets'], list) or len(ai_data['card_bullets']) < 3:
        print("⚠️ card_bullets는 3개 이상의 배열이어야 합니다")
        return False
    
    if not isinstance(ai_data['tags'], list) or len(ai_data['tags']) < 1:
        print("⚠️ tags는 1개 이상의 배열이어야 합니다")
        return False
    
    if not isinstance(ai_data['faq'], list) or len(ai_data['faq']) < 2:
        print("⚠️ faq는 2개 이상의 배열이어야 합니다")
        return False
    
    return True

def main():
    print("🚀 [쿠팡 파트너스 블로그 자동화] 시작")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ 필수 환경 변수 누락")
        return

    try:
        credentials = pickle.loads(base64.b64decode(token_base64))
        blogger_service = build('blogger', 'v3', credentials=credentials)
        if not TEST_MODE:
            if check_already_posted(blogger_service, BLOG_ID): 
                return
        else:
            print("🧪 테스트 모드 ON")
    except Exception as e:
        print(f"❌ 초기화 에러: {e}")
        return

    products = get_coupang_v2_products(coupang_access, coupang_secret)
    if not products:
        print("❌ 상품 조회 실패")
        return
    
    target_p = products[0]
    raw_img = target_p.get('productImage', '').strip()
    img_url = 'https:' + raw_img if raw_img.startswith('//') else ('https://' + raw_img if raw_img and not raw_img.startswith('http') else raw_img)
    link_url = target_p.get('productUrl', target_p.get('landingUrl', ''))
    p_name = target_p.get('productName', '상품').replace('"', "'")
    raw_price = target_p.get('productPrice', 0)
    p_price_str = f"{int(raw_price):,}원" if str(raw_price).isdigit() else f"{raw_price}원"

    print(f"🛒 상품: {p_name} ({p_price_str})")

    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = (
        "너는 전문 쇼핑 에디터야. 아래 상품을 분석한 깔끔한 포스팅을 작성해줘.\n\n"
        f"[상품]: {p_name}\n[가격]: {p_price_str}\n\n"
        "[필수 지침]\n"
        "1. [제목]: 상품명 + 핵심 특징 (40자 이내)\n"
        "2. [도입부(hook_intro)]: 400자 이상. 이 상품이 필요한 이유부터 시작.\n"
        "3. [스펙표(spec_table)]: 정확한 마크다운 표 형식! 반드시 이렇게:\n"
        "   |항목|사양|\n"
        "   |---|---|\n"
        "   |기능|내용|\n"
        "   |크기|내용|\n"
        "   (5행 이상, 구분선 필수)\n"
        "4. [스펙 요약(spec_summary)]: 스펙표 핵심을 2줄(60~80자)로 압축 요약.\n"
        "5. [장점과 단점(pros_cons_body)]: 800자 이상.\n"
        "   형식:\n"
        "   🎯 장점\n"
        "   • 장점 1\n"
        "   • 장점 2\n"
        "   • 장점 3\n\n"
        "   ⚠️ 단점\n"
        "   • 단점 1\n"
        "6. [장단점 요약(pros_cons_summary)]: 장단점 핵심을 2줄로 압축 요약.\n"
        "7. [결론(verdict)]: 300자 이상. '이런 분들에게 추천' 형식.\n"
        "8. [추천대상 요약(verdict_summary)]: 추천 대상을 2줄로 압축 요약.\n"
        "9. [카드 핵심(card_bullets)]: 배열, 각 20자 이내\n"
        "10. [태그(tags)]: 3~4개 배열\n"
        "11. [slug]: 영어 소문자 2~3개 단어\n"
        "12. [FAQ]: faq 항목에 이 상품/카테고리에 대해 구매 전 실제로 궁금해할 질문 4개와 답변(2~3문장)을 작성하라.\n"
        "13. [결론문단(conclusion)]: 글 전체를 마무리하는 문단(200~300자). 핵심 재확인 + 구매 조언으로 끝내라.\n\n"
        "반드시 이 JSON만 출력하라:\n"
        "{\n"
        '  "title": "상품명 - 핵심 특징",\n'
        '  "slug": "product-slug",\n'
        '  "hook_intro": "도입부...",\n'
        '  "spec_table": "|항목|사양|\n|---|---|\n|항목1|설명|",\n'
        '  "spec_summary": "스펙 핵심 요약 2줄",\n'
        '  "pros_cons_body": "🎯 장점\n• 항목1\n\n⚠️ 단점\n• 항목1",\n'
        '  "pros_cons_summary": "장단점 핵심 요약 2줄",\n'
        '  "verdict": "결론...",\n'
        '  "verdict_summary": "추천대상 핵심 요약 2줄",\n'
        '  "card_bullets": ["항목1", "항목2", "항목3"],\n'
        '  "tags": ["태그1", "태그2"],\n'
        '  "faq": [\n'
        '    {"question": "질문1", "answer": "답변1"},\n'
        '    {"question": "질문2", "answer": "답변2"},\n'
        '    {"question": "질문3", "answer": "답변3"},\n'
        '    {"question": "질문4", "answer": "답변4"}\n'
        '  ],\n'
        '  "conclusion": "전체 내용을 마무리하는 결론 문단"\n'
        "}"
    )

    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
    ai_data = {}
    
    for model in ['gemini-2.5-flash', 'gemini-2.5-pro']:
        for attempt in range(3):
            try:
                res = ai_client.models.generate_content(model=model, contents=prompt, config=config)
                if res and res.text:
                    raw_json = res.text.replace('```json', '').replace('```', '').strip()
                    ai_data = json.loads(raw_json)
                    
                    if validate_ai_data(ai_data):
                        print(f"✅ AI 응답 성공 ({model})")
                        break
                    else:
                        ai_data = {}
                        time.sleep(2)
            except Exception as e:
                print(f"⚠️ AI 에러 (시도 {attempt+1}): {e}")
                time.sleep(2)
        
        if ai_data:
            break

    if not ai_data:
        print("❌ AI 분석 실패")
        return

    raw_title = ai_data['title']
    title = get_clean_title(raw_title)
    raw_slug = ai_data['slug']
    slug = re.sub(r'[^a-z0-9\-]', '', raw_slug.lower()).strip('-') or "best-product"
    tags = ai_data['tags'][:4]

    print(f"📝 제목: {title}")
    print(f"📌 슬러그: {slug}")

    card_file, is_card = create_pil_card(p_name, p_price_str, ai_data.get('card_bullets', []))
    best_img_url = None
    
    if card_file:
        cdn_url = upload_image_to_github(card_file)
        best_img_url = cdn_url if cdn_url else card_file
        print(f"🖼️ 이미지 URL: {best_img_url}")
    else:
        print("⚠️ 카드 생성 실패, 원본 이미지 사용")
        best_img_url = img_url
        is_card = False

    cta_btn = f'<div style="margin: 40px 0; text-align: center;"><a href="{link_url}" target="_blank" style="background-color: #E52528; color: #FFFFFF; font-size: 17px; font-weight: bold; padding: 18px 36px; text-decoration: none; border-radius: 10px; display: inline-block; box-shadow: 0 6px 16px rgba(229, 37, 40, 0.3);">🚀 쿠팡에서 최저가 확인하기</a></div>'
    
    hero_html = f'<div style="margin: 40px 0; text-align: center;"><a href="{link_url}" target="_blank"><img src="{best_img_url}" alt="{title}" style="max-width: 90%; border-radius: 16px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.1);"/></a><p style="font-size: 13px; color: #94a3b8; margin-top: 12px;">👆 이미지를 클릭하면 쿠팡 페이지로 이동합니다</p></div>'

    ftc_msg = "<p style='color: #94a3b8; font-size: 13px; margin-bottom: 32px;'>💡 이 포스팅은 쿠팡 파트너스 활동으로 일정 수수료를 제공받습니다.</p>"
    h3_style = 'font-size: 21px; font-weight: bold; color: #1e293b; margin: 48px 0 24px 0; display: inline-block; border-bottom: 3px solid #E52528; padding-bottom: 8px;'

    toc_html = build_toc_html()
    faq_html = build_faq_html(ai_data.get('faq', []))
    conclusion_html = build_conclusion_html(ai_data.get('conclusion', ''))

    inner_content = (
        ftc_msg + 
        generate_adsense_html() + 
        toc_html +
        '<div style="height: 24px;"></div>' +
        format_content(ai_data['hook_intro']) + 
        '<div style="height: 28px;"></div>' +
        hero_html + 
        '<div style="height: 28px;"></div>' +
        cta_btn + 
        '<div style="height: 40px;"></div>' +
        f'<h3 id="spec" style="{h3_style}">📋 주요 스펙</h3>' + 
        '<div style="height: 20px;"></div>' +
        format_content(ai_data['spec_table']) + 
        make_section_summary(ai_data.get('spec_summary', '')) +
        '<div style="height: 40px;"></div>' +
        f'<h3 id="proscons" style="{h3_style}">✨ 장점과 단점</h3>' + 
        '<div style="height: 20px;"></div>' +
        format_content(ai_data['pros_cons_body']) + 
        make_section_summary(ai_data.get('pros_cons_summary', '')) +
        '<div style="height: 40px;"></div>' +
        f'<h3 id="verdict" style="{h3_style}">🎯 추천 대상</h3>' + 
        '<div style="height: 20px;"></div>' +
        format_content(ai_data['verdict']) + 
        make_section_summary(ai_data.get('verdict_summary', '')) +
        '<div style="height: 40px;"></div>' +
        cta_btn + 
        '<div style="height: 28px;"></div>' +
        faq_html +
        '<div style="height: 28px;"></div>' +
        generate_adsense_html() +
        '<div style="height: 28px;"></div>' +
        conclusion_html
    )

    final_html = f'<div style="max-width: 720px; margin: 0 auto; padding: 0 16px; text-align: center; font-family: -apple-system, BlinkMacSystemFont, Pretendard, Roboto, sans-serif; color: #222222; line-height: 1.7;">{inner_content}</div>'

    publish_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    scheduled_iso = publish_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    try:
        print(f"📤 블로그 발행 중...")
        res_ins = blogger_service.posts().insert(
            blogId=BLOG_ID, 
            body={'title': slug, 'content': final_html, 'labels': tags, 'published': scheduled_iso}, 
            isDraft=False
        ).execute()
        pid = res_ins.get('id')

        time.sleep(1.5)

        print(f"✏️ 제목 업데이트 중...")
        blogger_service.posts().patch(
            blogId=BLOG_ID, 
            postId=pid, 
            body={'title': title, 'content': final_html}
        ).execute()

        print("🎉 포스팅 성공!")
        print(f"   제목: {title}")
        print(f"   이미지: {'카드' if is_card else '원본'}")
    except Exception as e:
        print(f"❌ 발행 실패: {e}")

if __name__ == "__main__":
    main()
