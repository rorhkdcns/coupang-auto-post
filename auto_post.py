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

# [1단계] 필수 라이브러리 검증 및 자동 설치
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
# ⚙️ [고유 설정 정보] (유저님 세팅 무결성 100% 보존)
# =====================================================================
BLOG_ID = "8715372631292128719"  
GOOGLE_ADSENSE_CLIENT = "ca-pub-4292478378917157"
GOOGLE_ADSENSE_SLOT = "7988651325"

BLOG_DOMAIN = "blogspot.com"

GITHUB_USER_ID = "rorhkdcns"
# 깃허브 액션 환경변수에서 현재 레포 이름을 동적으로 자동 추출합니다.
GITHUB_REPO_NAME = (os.environ.get("GITHUB_REPOSITORY") or "rorhkdcns/blogger-auto-post").split("/")[-1]

def get_coupang_v2_products(access_key, secret_key):
    domain = "https://api-gateway.coupang.com"
    path = "/v2/providers/affiliate_open_api/apis/openapi/v2/products/reco"
    
    req_data = {
        "site": {"domain": BLOG_DOMAIN, "id": BLOG_ID},
        "device": {"id": "DESKTOP_ID", "ip": "127.0.0.1", "lmt": 0, "ua": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
        "imp": {"ad_type": 2, "imageSize": "180x180", "placementid": "blog_main", "pos": 1},
        "user": {"puid": "blogger_user"}
    }
    
    gmt_now = datetime.datetime.now(datetime.timezone.utc)
    datetime_gmt = gmt_now.strftime('%y%m%dT%H%M%SZ')
    message = datetime_gmt + "POST" + path

    signature = hmac.new(bytes(secret_key, "utf-8"), bytes(message, "utf-8"), hashlib.sha256).hexdigest()
    authorization_header = f"CEA algorithm=HmacSHA256, access-key={access_key}, signed-date={datetime_gmt}, signature={signature}"

    headers = {"Content-Type": "application/json", "Authorization": authorization_header}
    url = f"{domain}{path}"

    try:
        res = requests.post(url, headers=headers, json=req_data, timeout=10)
        print(f"📡 쿠팡 V2 서버 응답 상태코드: {res.status_code}")
        if res.status_code != 200: return []
        res_json = res.json()
        data_node = res_json.get("data")
        products_list = []
        if isinstance(data_node, list): products_list = data_node
        elif isinstance(data_node, dict): products_list = data_node.get("result", []) or data_node.get("recoProducts", []) or data_node.get("products", [])
        return products_list[:4] 
    except Exception as e:
        print(f"💥 쿠팡 V2 통신 중 예외 발생: {str(e)}")
        return []

def clean_html_garbage(text):
    text = text.replace('`', '').replace('**', '').replace('__', '').replace('<span>', '').replace('</span>', '')
    text = re.sub(r'<\s*span[^>]*>', '', text) 
    text = re.sub(r'\[.*?\]\s*:\s*', '', text)
    return text.strip()

def check_already_posted(blogger, blog_id):
    kst = datetime.timezone(datetime.timedelta(hours=9))
    now = datetime.datetime.now(kst)
    try:
        for status_type in ['LIVE', 'SCHEDULED']:
            posts = blogger.posts().list(blogId=blog_id, maxResults=10, status=status_type).execute()
            for item in posts.get('items', []):
                up_str = item.get('updated', '') 
                if up_str:
                    clean_up = up_str.replace('Z', '+00:00')
                    up_time = datetime.datetime.fromisoformat(clean_up).astimezone(kst)
                    time_diff_minutes = (now - up_time).total_seconds() / 60
                    if 0 <= time_diff_minutes < 30.0:
                        print(f"⏳ 대기: 최근 {time_diff_minutes:.1f}분 전에 생성된 포스팅({status_type}) 존재. 중복 차단.")
                        return True
    except Exception as e:
        print(f"⚠️ 중복 체크 과정 중 오류 발생: {e}")
    return False

# =====================================================================
# 🎨 PIL 인포그래픽 '상품 스펙 카드' 생성기 (저작권 회피 및 클릭율 상승)
# =====================================================================
def bake_pil_summary_card(prod_name, price_str, img_url, bullet_points):
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

    # 원본 이미지 흰색 캔버스 합성
    try:
        res_img = requests.get(img_url, headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        p_img = Image.open(io.BytesIO(res_img.content)).convert('RGBA')
        p_img.thumbnail((350, 350), Image.Resampling.LANCZOS)
        bg = Image.new('RGBA', p_img.size, (255, 255, 255))
        composite = Image.alpha_composite(bg, p_img).convert('RGB')
        card.paste(composite, ((800 - composite.width) // 2, 70))
    except Exception as e: print(f"⚠️ 이미지 합성 대체 렌더링: {e}")

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

    with open(file_name, "rb") as f: encoded = base64.b64encode(f.read()).decode("utf-8")
    git_path = f"blog_images/coupang/{file_name}"
    url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
    
    try:
        res_put = requests.put(url, headers=headers, json={"message": f"CP-Card: {file_name}", "content": encoded, "branch": "main"}, timeout=10)
        if res_put.status_code in [200, 201]: return f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
    except: pass
    return ""

def format_paragraphs(text):
    if not text or not text.strip(): return ""
    text = re.sub(r'\*\*(.*?)\*\*', r'<strong style="color: #2563eb;">\1</strong>', text)
    processed_chunks, in_table, table_html = [], False, []
    for line in text.split('\n'):
        line = line.strip()
        if not line: continue
        if line.startswith('|') and line.endswith('|'):
            if not in_table:
                in_table = True
                table_html = ['<div style="overflow-x:auto; margin: 25px 0;"><table style="width:100%; border-collapse:collapse; border:1px solid #cbd5e1;">']
            if re.match(r'^\|(?:[\s\-:]+\|)+$', line): continue
            tds = ''.join([f'<td style="border:1px solid #cbd5e1; padding:12px; font-size:14px;">{c.strip()}</td>' for c in line.split('|')[1:-1]])
            table_html.append(f'<tr>{tds}</tr>')
        else:
            if in_table:
                in_table = False
                table_html.append('</table></div>')
                processed_chunks.append("".join(table_html))
                table_html = []
            processed_chunks.append(f'<p style="margin-bottom:22px; line-height:1.8; font-size:15px; color:#334155;">{line}</p>')
    if in_table:
        table_html.append('</table></div>')
        processed_chunks.append("".join(table_html))
    return "".join(processed_chunks)

def main():
    print("🔄 [쿠팡 파트너스 API V2 x 블로그스팟] 정석 포스팅 공장을 가동합니다.")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    
    if not (gemini_key and token_base64 and coupang_access and coupang_secret):
        print("❌ [중단] 깃허브 시크릿 금고 열쇠 확인 필요")
        return

    try:
        credentials = pickle.loads(base64.b64decode(token_base64))
        blogger_service = build('blogger', 'v3', credentials=credentials)
        if check_already_posted(blogger_service, BLOG_ID): return
    except Exception as e: print(f"⚠️ 사전 중복 체크 에러: {e}")

    print("🎯 [1단계: 소싱] 최신 V2 맞춤 추천 상품 호출 중...")
    products = get_coupang_v2_products(coupang_access, coupang_secret)
    if not products: return
    
    # ★ 전략적 변화: 4개 중 점수가 가장 높은 1번 상품을 메인 주인공으로 선정
    target_p = products[0]
    
    raw_img = target_p.get('productImage', '').strip()
    img_url = 'https:' + raw_img if raw_img.startswith('//') else ('https://' + raw_img if raw_img and not raw_img.startswith('http') else raw_img)
    link_url = target_p.get('productUrl', target_p.get('landingUrl', ''))
    p_name = target_p.get('productName', '쿠팡 인기 추천 상품').replace('"', "'")
    
    raw_price = target_p.get('productPrice', 0)
    p_price_str = f"{int(raw_price):,}원" if str(raw_price).isdigit() else f"{raw_price}원"

    print(f"🛒 오늘의 집중 분석 주인공 선정 완료: {p_name}")

    print("🤖 [2단계: AI 원고 생성] 단일 상품 고밀도 PASONA 원고 집필 중...")
    ai_client = genai.Client(api_key=gemini_key)
    
    prompt = (
        "너는 구독자 10만 명의 '내돈내산 쇼핑 칼럼니스트'야. "
        "아래 상품 정보를 바탕으로 검색 방문자가 신뢰하고 정독하게 만드는 집중 분석 칼럼을 작성해줘.\n\n"
        f"[상품명]: {p_name}\n[할인 가격]: {p_price_str}\n\n"
        "[필수 작성 지침]\n"
        "1. [제목]: '상품명 + 핵심 키워드(내돈내산 솔직 후기, 장단점, 가격 비교)' 조합으로 클릭률 높게 작성.\n"
        "2. [도입부(hook_intro)]: 공백 포함 450자 이상. 이 상품을 사기 전 소비자가 겪는 결정 장애와 답답함에 깊이 공감하며 시작할 것.\n"
        "3. [스펙 비교표(spec_table)]: 마크다운 표 문법(|구분|상세 스펙|)을 사용해 주요 스펙을 4행 이상 명쾌하게 정리할 것.\n"
        "4. [장단점 본문(pros_cons_body)]: 공백 포함 700자 이상. 장점 3가지와 '구매 전 반드시 알아야 할 아쉬운 점(단점) 1가지'를 솔직하게 작성해 신뢰도를 높여라.\n"
        "5. [구매 추천 대상(verdict)]: 공백 포함 300자 이상. '이런 분들께는 강력 추천 / 이런 분들은 사지 마세요' 형태로 정리.\n"
        "6. [카드 요약(card_bullets)]: 인포그래픽 요약 카드에 인쇄할 핵심 장점 딱 3문장을 각각 15자 이내 배열로 출력.\n"
        "7. [태그(tags)]: 상품과 직결되는 핵심 키워드 딱 3~4개만 배열로 출력. (60개씩 넣는 스팸 행위 절대 금지)\n"
        "8. [퍼머링크(slug)]: 영어 소문자 단어 2~3개 하이픈 연결.\n"
        "9. [금지어]: '파소나', 'PASONA', '카피라이팅', 'AI', '인공지능', '자동화', '프로그램'.\n\n"
        "반드시 아래 JSON 규격만 출력하라.\n"
        "{\n"
        '  "title": "에어팟 프로 2세대 내돈내산 솔직 후기 및 장단점",\n'
        '  "slug": "airpods-pro-2-review",\n'
        '  "hook_intro": "도입부 내용...",\n'
        '  "spec_table": "|스펙|내용| 표...",\n'
        '  "pros_cons_body": "장단점 분석...",\n'
        '  "verdict": "추천 대상 정리...",\n'
        '  "card_bullets": ["노이즈캔슬링 압도적", "C타입 호환성 굿", "배터리 30시간 지속"],\n'
        '  "tags": ["에어팟프로2", "무선이어폰추천", "애플이어폰"]\n'
        "}"
    )

    config = types.GenerateContentConfig(response_mime_type="application/json", temperature=0.7)
    ai_data = {}
    for model in ['gemini-2.5-flash', 'gemini-2.5-pro']:
        for _ in range(3):
            try:
                res = ai_client.models.generate_content(model=model, contents=prompt, config=config)
                if res and res.text: 
                    ai_data = json.loads(res.text.replace('```json','').replace('```','').strip())
                    break
            except: time.sleep(5)
        if ai_data: break

    if not ai_data: return

    title, raw_slug, tags = ai_data['title'], ai_data['slug'], ai_data['tags'][:4]
    slug = re.sub(r'[^a-z0-9\-]', '', raw_slug.lower()).strip('-') or "best-coupang-item"

    # PIL 스펙 카드 제작 가동
    card_cdn_url = bake_pil_summary_card(p_name, p_price_str, img_url, ai_data['card_bullets'])

    def generate_adsense_html():
        return f'<div class="adsense-container" style="text-align:center; margin:30px 0;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={GOOGLE_ADSENSE_CLIENT}" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="{GOOGLE_ADSENSE_CLIENT}" data-ad-slot="{GOOGLE_ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></div>'

    cta_btn_html = f'<div style="text-align:center; margin:35px 0;"><a href="{link_url}" target="_blank" style="background-color:#E52528; color:white; font-size:17px; font-weight:bold; padding:16px 32px; text-decoration:none; border-radius:8px; display:inline-block; box-shadow:0 4px 12px rgba(229,37,40,0.25);">🚀 실시간 최저가 및 로켓배송 가능 여부 확인하기</a></div>'

    card_img_html = f'<div style="text-align:center; margin:25px 0;"><a href="{link_url}" target="_blank"><img src="{card_cdn_url}" alt="{title}" style="max-width:100%; border-radius:16px; box-shadow:0 8px 24px rgba(0,0,0,0.08);"/></a><p style="font-size:12px; color:#94A3B8; margin-top:6px;">👆 이미지를 클릭하면 상품 상세 페이지로 이동합니다</p></div>' if card_cdn_url else ""

    ftc_disclosure = "<p style='color:#94a3b8; font-size:12px; text-align:center; margin-bottom:20px;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>"

    final_html = ftc_disclosure + generate_adsense_html() + \
                 format_paragraphs(ai_data['hook_intro']) + card_img_html + cta_btn_html + \
                 f'<h3 style="font-size:20px; font-weight:bold; color:#1e293b; border-bottom:2px solid #E52528; padding-bottom:8px; margin-top:40px;">💡 주요 스펙 한눈에 보기</h3>{format_paragraphs(ai_data["spec_table"])}' + \
                 f'<h3 style="font-size:20px; font-weight:bold; color:#1e293b; border-bottom:2px solid #E52528; padding-bottom:8px; margin-top:40px;">🔍 내돈내산 장단점 집중 분석</h3>{format_paragraphs(ai_data["pros_cons_body"])}' + \
                 f'<h3 style="font-size:20px; font-weight:bold; color:#1e293b; border-bottom:2px solid #E52528; padding-bottom:8px; margin-top:40px;">🎯 총평: 이런 분들께 추천합니다</h3>{format_paragraphs(ai_data["verdict"])}' + \
                 cta_btn_html + generate_adsense_html()

    publish_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=1)
    scheduled_iso = publish_time.strftime('%Y-%m-%dT%H:%M:%SZ')

    # [쿠팡 완벽 3연타 발행] 영어 주소 고정 -> 한글 제목 덮어쓰기 -> 내일 시간으로 예약 유배
    try:
        print(f"🔗 [1연타] 영어 퍼머링크 출생신고 중... (/{slug}.html)")
        res_ins = blogger_service.posts().insert(
            blogId=BLOG_ID, 
            body={'title': slug, 'content': final_html, 'labels': tags}, 
            isDraft=False
        ).execute()
        pid = res_ins.get('id')

        time.sleep(1.5)
        print(f"✍️ [2연타] 한글 정식 제목('{title}') 안전 박제 중...")
        blogger_service.posts().patch(
            blogId=BLOG_ID, 
            postId=pid, 
            body={'title': title, 'content': final_html, 'labels': tags}
        ).execute()

        time.sleep(1.0)
        print(f"⏰ [3연타] 내일 시각({scheduled_iso})으로 예약 유배 전송 중...")
        blogger_service.posts().patch(
            blogId=BLOG_ID, 
            postId=pid, 
            body={'published': scheduled_iso}
        ).execute()

        print("🚀 쿠팡 파트너스 API V2 자동화 정석 리뷰 포스팅 완벽 성공!")
    except Exception as e:
        print(f"❌ 최종 발행 에러: {e}")

if __name__ == "__main__":
    main()
