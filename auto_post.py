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
TEST_MODE = True # ★ 내일부터 서버 자동화 올릴 땐 반드시 False 로 바꾸세요!

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

def download_and_upload_image_to_github(proxy_url, prefix="prod"):
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token or not proxy_url: return ""
    try:
        res = requests.get(proxy_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
        if res.status_code != 200: return ""
        img = Image.open(io.BytesIO(res.content)).convert('RGB')
        img.thumbnail((600, 600), Image.Resampling.LANCZOS)
        file_name = f"{prefix}_{int(time.time())}_{random.randint(100,999)}.webp"
        buffer = io.BytesIO()
        img.save(buffer, format="WEBP", quality=85)
        encoded_img = base64.b64encode(buffer.getvalue()).decode("utf-8")
        git_path = f"blog_images/coupang/{file_name}"
        url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
        gh_headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
        res_put = requests.put(url, headers=gh_headers, json={"message": f"Upload: {file_name}", "content": encoded_img, "branch": "main"}, timeout=10)
        if res_put.status_code in [200, 201]: return f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
    except: pass
    return ""

def bake_pil_summary_card(prod_name, price_str, proxy_img_url, bullet_points):
    gh_token = os.environ.get("GITHUB_TOKEN")
    if not gh_token: return ""
    font_url = "https://github.com/google/fonts/raw/main/ofl/nanumgothic/NanumGothic-Bold.ttf"
    font_path = "NanumGothic-Bold.ttf"
    if not os.path.exists(font_path):
        try: urllib.request.urlretrieve(font_url, font_path)
        except: pass

    card = Image.new('RGB', (800, 800), color='#F8FAFC')
    draw = ImageDraw.Draw(card)
    draw.rounded_rectangle([40, 40, 760, 760], radius=24, fill='#FFFFFF', outline='#CBD5E1', width=2)
    try:
        title_font, price_font = ImageFont.truetype(font_path, 30), ImageFont.truetype(font_path, 42)
        bullet_font, badge_font = ImageFont.truetype(font_path, 23), ImageFont.truetype(font_path, 18)
    except:
        title_font = price_font = bullet_font = badge_font = ImageFont.load_default()

    try:
        res_img = requests.get(proxy_img_url, timeout=5)
        p_img = Image.open(io.BytesIO(res_img.content)).convert('RGBA')
        p_img.thumbnail((350, 350), Image.Resampling.LANCZOS)
        bg = Image.new('RGBA', p_img.size, (255, 255, 255))
        composite = Image.alpha_composite(bg, p_img).convert('RGB')
        card.paste(composite, ((800 - composite.width) // 2, 70))
    except: pass

    draw.rounded_rectangle([330, 440, 470, 475], radius=6, fill='#E52528')
    draw.text((400, 457), "COUPANG PICK", fill='#FFFFFF', font=badge_font, anchor="mm")
    clean_name = prod_name if len(prod_name) <= 22 else prod_name[:22] + "..."
    draw.text((400, 520), clean_name, fill='#0F172A', font=title_font, anchor="mm")
    draw.text((400, 575), f"할인 특가: {price_str}", fill='#2563EB', font=price_font, anchor="mm")
    draw.line([(100, 620), (700, 620)], fill='#E2E8F0', width=2)

    start_y = 650
    for bp in bullet_points[:3]:
        draw.text((120, start_y), f"✔  {bp}", fill='#334155', font=bullet_font)
        start_y += 36

    file_name = f"cp_card_{int(time.time())}.webp"
    card.save(file_name, "WEBP", quality=85)
    with open(file_name, "rb") as f: 
        encoded = base64.b64encode(f.read()).decode("utf-8")
    git_path = f"blog_images/coupang/{file_name}"
    url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
    try:
        res_put = requests.put(url, headers=headers, json={"message": f"CP-Card: {file_name}", "content": encoded, "branch": "main"}, timeout=10)
        if res_put.status_code in [200, 201]: return f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
    except: pass
    return ""

def generate_image_with_gemini(ai_client, prod_name, price_str, card_bullets):
    """PIL로 전문적인 상품 분석 이미지 카드 생성"""
    try:
        # Noto Sans 폰트 URL
        font_url = "https://github.com/google/fonts/raw/main/ofl/notosans/NotoSans-Bold.ttf"
        font_path = "NotoSans-Bold.ttf"
        if not os.path.exists(font_path):
            try: 
                urllib.request.urlretrieve(font_url, font_path)
            except: pass

        # 카드 크기: 1200x630 (16:9 비율, 소셜 미디어 최적)
        card = Image.new('RGB', (1200, 630), color='#FFFFFF')
        draw = ImageDraw.Draw(card)
        
        # 배경 그라데이션 효과
        for y in range(630):
            color_val = int(255 - (y / 630) * 10)
            draw.line([(0, y), (1200, y)], fill=(color_val, color_val, color_val))
        
        # 왼쪽 액센트 바
        draw.rectangle([0, 0, 6, 630], fill='#E52528')
        
        try:
            title_font = ImageFont.truetype(font_path, 48)
            price_font = ImageFont.truetype(font_path, 56)
            bullet_font = ImageFont.truetype(font_path, 24)
            badge_font = ImageFont.truetype(font_path, 20)
        except:
            title_font = price_font = bullet_font = badge_font = ImageFont.load_default()

        # 배지
        draw.rectangle([50, 40, 250, 75], fill='#E52528')
        draw.text((150, 57), "쿠팡 PICK", fill='#FFFFFF', font=badge_font, anchor="mm")
        
        # 상품명 (최대 2줄)
        clean_name = prod_name if len(prod_name) <= 30 else prod_name[:30] + "..."
        draw.text((80, 120), clean_name, fill='#1e293b', font=title_font, anchor="lm")
        
        # 가격
        draw.text((80, 220), f"{price_str}", fill='#E52528', font=price_font, anchor="lm")
        
        # 구분선
        draw.line([(80, 270), (1120, 270)], fill='#E2E8F0', width=2)
        
        # 핵심 포인트
        bullet_y = 320
        for i, bullet in enumerate(card_bullets[:3]):
            # 번호 원형 배경
            draw.ellipse([60, bullet_y-12, 95, bullet_y+20], fill='#E52528')
            draw.text((77, bullet_y+4), str(i+1), fill='#FFFFFF', font=bullet_font, anchor="mm")
            
            # 텍스트
            draw.text((120, bullet_y+4), bullet, fill='#334155', font=bullet_font, anchor="lm")
            bullet_y += 85

        file_name = f"card_{int(time.time())}.webp"
        card.save(file_name, "WEBP", quality=90)
        
        # GitHub 업로드
        gh_token = os.environ.get("GITHUB_TOKEN")
        if gh_token:
            with open(file_name, "rb") as f:
                encoded = base64.b64encode(f.read()).decode("utf-8")
            
            git_path = f"blog_images/cards/{file_name}"
            url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
            headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
            
            res_put = requests.put(
                url, 
                headers=headers, 
                json={"message": f"Product Card: {file_name}", "content": encoded, "branch": "main"}, 
                timeout=10
            )
            
            if res_put.status_code in [200, 201]:
                cdn_url = f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
                print(f"✅ 상품 카드 생성 및 업로드 성공: {cdn_url}")
                try: os.remove(file_name)
                except: pass
                return cdn_url, True
        
        # 로컬 파일 반환
        print(f"⚠️ 상품 카드 생성 완료 (로컬): {file_name}")
        return file_name, True
            
    except Exception as e:
        print(f"⚠️ 상품 카드 생성 실패: {e}")
    
    return None, False

def get_bulletproof_image_url(raw_coupang_url, prod_name, price_str, bullets, ai_client=None, use_gemini=True):
    """4중 방어: Gemini 생성 → PIL 카드 → 원본 박제 → 실시간 프록시"""
    
    # 1안: Gemini 이미지 생성 (가장 우선)
    if use_gemini and ai_client:
        gemini_url, is_generated = generate_image_with_gemini(ai_client, prod_name, price_str, bullets)
        if gemini_url:
            return gemini_url, True
    
    if not raw_coupang_url or not raw_coupang_url.strip():
        print("⚠️ [이미지 URL 공백] 기본 쿠팡 로고 링크로 대체")
        return "https://image.coupang.com/common/img_logo_coupang.png", False
    
    clean_target = re.sub(r'^https?://', '', raw_coupang_url)
    weserv_proxy = f"https://images.weserv.nl/?url={urllib.parse.quote(clean_target)}"
    
    # 2안: PIL 카드 제작
    card_cdn = bake_pil_summary_card(prod_name, price_str, weserv_proxy, bullets)
    if card_cdn:
        print(f"✅ PIL 카드 생성 성공: {card_cdn}")
        return card_cdn, True
    
    # 3안: 원본 박제
    hero_cdn = download_and_upload_image_to_github(weserv_proxy, prefix="hero")
    if hero_cdn:
        print(f"✅ 원본 이미지 업로드 성공: {hero_cdn}")
        return hero_cdn, False
    
    # 4안: 프록시
    print("⚠️ [로컬 환경 감지] 깃허브 업로드를 생략하고 실시간 이미지 우회 링크로 대체 송출합니다.")
    return weserv_proxy, False

def markdown_table_to_html(markdown_table):
    """마크다운 테이블을 HTML 테이블로 변환"""
    if not markdown_table or not markdown_table.strip():
        return ""
    
    lines = [line.strip() for line in markdown_table.split('\n') if line.strip() and line.strip().startswith('|')]
    if len(lines) < 2:
        return ""
    
    html = '<table style="border-collapse: collapse; width: 100%; margin: 0 auto; text-align: center; border: 1px solid #cbd5e1;">'
    
    # 헤더 처리
    header_cells = [cell.strip() for cell in lines[0].split('|')[1:-1]]
    html += '<thead style="background-color: #f1f5f9;"><tr>'
    for cell in header_cells:
        html += f'<th style="border: 1px solid #cbd5e1; padding: 12px; font-weight: bold; color: #1e293b; text-align: center;">{cell}</th>'
    html += '</tr></thead>'
    
    # 구분선 스킵하고 바디 처리
    html += '<tbody>'
    for line in lines[2:]:
        cells = [cell.strip() for cell in line.split('|')[1:-1]]
        html += '<tr>'
        for cell in cells:
            html += f'<td style="border: 1px solid #cbd5e1; padding: 10px; color: #475569; text-align: center;">{cell}</td>'
        html += '</tr>'
    html += '</tbody></table>'
    
    return html

def format_paragraphs(text):
    """텍스트 포맷팅: 마크다운 → HTML, 리스트, 공백 처리"""
    if not text or not text.strip(): 
        return ""
    
    # [핵심] **키워드**를 빨간 볼드로 치환
    text = re.sub(r'\*\*(.*?)\*\*', r'<span style="color:#E52528; font-weight:bold;">\1</span>', text)
    
    chunks = []
    lines = text.split('\n')
    in_list = False
    
    for line in lines:
        line = line.rstrip()
        
        # 빈 줄 처리
        if not line.strip():
            if in_list:
                chunks.append('</ul>')
                in_list = False
            chunks.append('<div style="height: 16px;"></div>')  # 공백
            continue
        
        # 제목 처리 (예: "🎯 장점" 또는 "⚠️ 단점")
        if line.startswith(('🎯', '⚠️', '💡', '🔍', '🚀', '✅')):
            if in_list:
                chunks.append('</ul>')
                in_list = False
            chunks.append(f'<h4 style="font-size: 17px; font-weight: bold; color: #1e293b; margin: 28px 0 14px 0; text-align: center;">{line}</h4>')
            continue
        
        # 리스트 항목 처리 (• 또는 -)
        if line.strip().startswith(('•', '-')):
            if not in_list:
                chunks.append('<ul style="margin: 12px auto; padding-left: 40px; list-style-type: none; text-align: center; display: inline-block;">')
                in_list = True
            list_text = re.sub(r'^[•\-]\s*', '', line.strip())
            chunks.append(f'<li style="margin-bottom: 8px; color: #475569; font-size: 15px; line-height: 1.6; text-align: left;">{list_text}</li>')
            continue
        
        # 표 처리
        if line.startswith('|'):
            if in_list:
                chunks.append('</ul>')
                in_list = False
            table_html = markdown_table_to_html(line)
            if table_html:
                chunks.append(f'<div style="margin: 28px auto; overflow-x: auto; width: 95%; text-align: center;">{table_html}</div>')
            continue
        
        # 일반 본문 처리
        if in_list:
            chunks.append('</ul>')
            in_list = False
        
        # 줄바꿈이 많은 텍스트는 여러 p로 분할
        chunks.append(f'<p style="text-align: center; font-size: 15px; line-height: 1.8; margin-bottom: 18px; color: #334155;">{line.strip()}</p>')
    
    # 마지막 리스트 종료
    if in_list:
        chunks.append('</ul>')
    
    return "".join(chunks)

def generate_adsense_html():
    """Google AdSense HTML 생성"""
    return f'<div class="adsense-container" style="margin:30px auto; text-align:center;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={GOOGLE_ADSENSE_CLIENT}" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="{GOOGLE_ADSENSE_CLIENT}" data-ad-slot="{GOOGLE_ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></div>'

def validate_ai_data(ai_data):
    """AI 응답 데이터 검증"""
    required_fields = ['title', 'slug', 'hook_intro', 'spec_table', 'pros_cons_body', 'verdict', 'card_bullets', 'tags']
    
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
    
    return True

def main():
    print("🔄 [쿠팡 파트너스 API V2] 정석 포스팅 공장을 가동합니다.")
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
            print("🧪 [테스트 모드 ON] 30분 중복 방지를 패스합니다.")
    except Exception as e:
        print(f"⚠️ 사전 중복 체크 에러: {e}")
        return

    products = get_coupang_v2_products(coupang_access, coupang_secret)
    if not products:
        print("❌ 쿠팡 상품 데이터 조회 실패")
        return
    
    target_p = products[0]
    raw_img = target_p.get('productImage', '').strip()
    img_url = 'https:' + raw_img if raw_img.startswith('//') else ('https://' + raw_img if raw_img and not raw_img.startswith('http') else raw_img)
    link_url = target_p.get('productUrl', target_p.get('landingUrl', ''))
    p_name = target_p.get('productName', '쿠팡 인기 추천 상품').replace('"', "'")
    raw_price = target_p.get('productPrice', 0)
    p_price_str = f"{int(raw_price):,}원" if str(raw_price).isdigit() else f"{raw_price}원"

    print(f"🛒 오늘의 집중 분석 주인공 선정 완료: {p_name}")

    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = (
        "너는 과장된 허세 없이 핵심 정보만 담백하게 짚어주는 '스마트 쇼핑 전문 에디터'야. "
        "아래 상품을 스마트폰에서 가독성 좋게 읽히는 깔끔한 칼럼으로 분석해줘.\n\n"
        f"[상품명]: {p_name}\n[가격]: {p_price_str}\n\n"
        "[필수 집필 지침]\n"
        "1. [제목]: 상품명 + 핵심 특징(예: '에어팟 프로 2세대 - 노이즈캔슬링 비교')\n"
        "2. [도입부(hook_intro)]: 공백 포함 400자 이상. 첫 문장부터 이 상품이 필요한 이유를 짚기. 불필요한 인사말 제거.\n"
        "3. [스펙표(spec_table)]: 마크다운 표 형식으로 주요 스펙 5행 이상.\n"
        "   형식: |항목|설명|\n|---|---|\n|스펙1|내용|\n\n"
        "4. [장점과 단점(pros_cons_body)]: 공백 포함 800자 이상.\n"
        "   형식:\n"
        "   🎯 장점\n"
        "   • 장점 1 (1줄 설명)\n"
        "   • 장점 2 (1줄 설명)\n"
        "   • 장점 3 (1줄 설명)\n\n"
        "   ⚠️ 단점 및 주의점\n"
        "   • 단점 1 (1줄 설명)\n\n"
        "5. [결론(verdict)]: 공백 포함 300자 이상. '이런 분들에게 추천합니다' 형식으로 정리.\n"
        "6. [카드 핵심(card_bullets)]: 3개 항목 배열, 각 15자 이내 (예: '노이즈캔슬링 강력', 'C타입 충전', '30시간 배터리')\n"
        "7. [태그(tags)]: 3~4개 배열\n"
        "8. [slug]: 영어 소문자 2~3개 단어를 하이픈으로 연결\n"
        "9. [금지어]: '파소나', 'PASONA', '내돈내산', '카피라이팅', 'AI', '인공지능', '자동화'.\n\n"
        "반드시 이 JSON 규격만 출력하라. 추가 텍스트 없이:\n"
        "{\n"
        '  "title": "에어팟 프로 2세대 - 노이즈캔슬링 비교",\n'
        '  "slug": "airpods-pro-2-review",\n'
        '  "hook_intro": "도입부 텍스트...",\n'
        '  "spec_table": "|항목|설명|\n|---|---|\n|기능|설명|\n|가격|설명|",\n'
        '  "pros_cons_body": "🎯 장점\n• 항목1\n• 항목2\n\n⚠️ 단점\n• 항목1",\n'
        '  "verdict": "결론 텍스트...",\n'
        '  "card_bullets": ["항목1", "항목2", "항목3"],\n'
        '  "tags": ["태그1", "태그2"]\n'
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
                    
                    # ★ AI 데이터 검증
                    if validate_ai_data(ai_data):
                        print(f"✅ AI 응답 검증 성공 ({model})")
                        break
                    else:
                        ai_data = {}
                        print(f"⚠️ AI 응답 검증 실패 ({model}), 재시도...")
                        time.sleep(2)
            except Exception as e:
                print(f"⚠️ AI 응답 파싱 에러 (시도 {attempt+1}): {e}")
                time.sleep(2)
        
        if ai_data:
            break

    if not ai_data:
        print("❌ AI 데이터 생성 실패")
        return

    title = ai_data['title']
    raw_slug = ai_data['slug']
    tags = ai_data['tags'][:4]
    slug = re.sub(r'[^a-z0-9\-]', '', raw_slug.lower()).strip('-') or "best-coupang-item"

    # ★ 4중 방어 이미지 추출 실행 (Gemini 생성 우선)
    best_img_url, is_card = get_bulletproof_image_url(
        img_url, p_name, p_price_str, 
        ai_data.get('card_bullets', []),
        ai_client=ai_client,
        use_gemini=True
    )

    # ★ CTA 버튼 정의 (중복 제거)
    cta_btn = f'<div style="margin:40px 0;"><a href="{link_url}" target="_blank" style="background-color:#E52528; color:#FFFFFF; font-size:17px; font-weight:bold; padding:18px 30px; text-decoration:none; border-radius:10px; display:inline-block; box-shadow:0 6px 16px rgba(229,37,40,0.25);">🚀 실시간 최저가 및 로켓배송 가능 여부 확인하기</a></div>'
    
    # ★ 이미지 영역 정의 (중복 제거)
    sub_txt = "👆 이미지를 터치하면 실시간 최저가 페이지로 이동합니다" if is_card else "👆 사진을 터치하면 로켓배송 확인 페이지로 이동합니다"
    hero_html = f'<div style="margin:35px 0;"><a href="{link_url}" target="_blank"><img src="{best_img_url}" alt="{title}" style="max-width:90%; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.08);"/></a><p style="font-size:12px; color:#94a3b8; margin-top:8px;">{sub_txt}</p></div>'

    ftc_msg = "<p style='color:#94a3b8; font-size:12px; margin-bottom:32px;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 일정액의 수수료를 제공받습니다.</p>"
    
    h3_style = 'font-size: 19px; font-weight: bold; color: #1e293b; margin: 48px 0 24px 0; display: inline-block; border-bottom: 3px solid #E52528; padding-bottom: 8px;'

    # ★ 최종 HTML 구성
    inner_content = (
        ftc_msg + 
        generate_adsense_html() + 
        f'<div style="height: 20px;"></div>' +
        format_paragraphs(ai_data['hook_intro']) + 
        f'<div style="height: 24px;"></div>' +
        hero_html + 
        f'<div style="height: 24px;"></div>' +
        cta_btn + 
        f'<div style="height: 32px;"></div>' +
        f'<h3 style="{h3_style}">📋 상세 스펙</h3>' + 
        f'<div style="height: 16px;"></div>' +
        format_paragraphs(ai_data['spec_table']) + 
        f'<div style="height: 32px;"></div>' +
        f'<h3 style="{h3_style}">✨ 장점과 단점</h3>' + 
        f'<div style="height: 16px;"></div>' +
        format_paragraphs(ai_data['pros_cons_body']) + 
        f'<div style="height: 32px;"></div>' +
        f'<h3 style="{h3_style}">🎯 추천 대상</h3>' + 
        f'<div style="height: 16px;"></div>' +
        format_paragraphs(ai_data['verdict']) + 
        f'<div style="height: 32px;"></div>' +
        cta_btn + 
        f'<div style="height: 24px;"></div>' +
        generate_adsense_html()
    )

    final_html = f'<div style="max-width: 680px; margin: 0 auto; padding: 0 16px; text-align: center; font-family: -apple-system, BlinkMacSystemFont, Pretendard, Roboto, sans-serif; color: #222222; line-height: 1.7;">{inner_content}</div>'

    publish_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    scheduled_iso = publish_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    try:
        print(f"🔗 [1연타] 예약 대기열에 영어 주소 방 생성 중... (/{slug}.html)")
        res_ins = blogger_service.posts().insert(
            blogId=BLOG_ID, 
            body={'title': slug, 'content': final_html, 'labels': tags, 'published': scheduled_iso}, 
            isDraft=False
        ).execute()
        pid = res_ins.get('id')

        time.sleep(1.5)

        print(f"✍️ [2연타] 방 제목만 정식 한글 문구('{title}')로 교체 중...")
        blogger_service.posts().patch(
            blogId=BLOG_ID, 
            postId=pid, 
            body={'title': title, 'content': final_html}
        ).execute()

        print("🚀 쿠팡 파트너스 정석 포스팅 완벽 생존 발행 성공!")
    except Exception as e:
        print(f"❌ 최종 발행 에러: {e}")

if __name__ == "__main__":
    main()
