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
    with open(file_name, "rb") as f: encoded = base64.b64encode(f.read()).decode("utf-8")
    git_path = f"blog_images/coupang/{file_name}"
    url = f"https://api.github.com/repos/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}/contents/{git_path}"
    headers = {"Authorization": f"Bearer {gh_token}", "Accept": "application/vnd.github.v3+json"}
    try:
        res_put = requests.put(url, headers=headers, json={"message": f"CP-Card: {file_name}", "content": encoded, "branch": "main"}, timeout=10)
        if res_put.status_code in [200, 201]: return f"https://cdn.jsdelivr.net/gh/{GITHUB_USER_ID}/{GITHUB_REPO_NAME}@main/{git_path}"
    except: pass
    return ""

# ★ 핵심: 환경에 상관없이 100% 사진을 보장하는 3중 방어 이미지 추출기
def get_bulletproof_image_url(raw_coupang_url, prod_name, price_str, bullets):
    clean_target = re.sub(r'^https?://', '', raw_coupang_url)
    weserv_proxy = f"https://images.weserv.nl/?url={urllib.parse.quote(clean_target)}"
    
    # 1안: PIL 카드 제작 (깃허브 액션 환경일 때 성공)
    card_cdn = bake_pil_summary_card(prod_name, price_str, weserv_proxy, bullets)
    if card_cdn: return card_cdn, True
    
    # 2안: 원본 박제 (깃허브 액션 환경일 때 성공)
    hero_cdn = download_and_upload_image_to_github(weserv_proxy, prefix="hero")
    if hero_cdn: return hero_cdn, False
    
    # 3안: 내 PC 로컬 테스트 등 깃허브 업로드 불가 시 다이렉트 프록시 송출!
    print("⚠️ [로컬 환경 감지] 깃허브 업로드를 생략하고 실시간 이미지 우회 링크로 대체 송출합니다.")
    return weserv_proxy, False

def format_paragraphs(text):
    if not text or not text.strip(): return ""
    text = re.sub(r'\*\*(.*?)\*\*', r'<span style="color:#E52528; font-weight:bold; background-color:#FFF1F2; padding:2px 6px; border-radius:4px;">\1</span>', text)
    chunks, in_table, table_html = [], False, []
    clean_raw = text.replace('\r', ' ').replace('\n', ' ')
    sentences = re.split(r'(?<=[.!?])\s+', clean_raw)
    
    curr_paragraph = []
    for s in sentences:
        s = s.strip()
        if not s: continue
        if s.startswith('|') and s.endswith('|'):
            if curr_paragraph:
                chunks.append(f'<p style="font-size:16px; line-height:2.2; margin-bottom:35px; color:#222;">{" ".join(curr_paragraph)}</p>')
                curr_paragraph = []
            if not in_table:
                in_table = True
                table_html = ['<div style="margin: 30px 0; overflow-x: auto;"><table style="width: 100%; border-collapse: collapse; margin: 0 auto; text-align: left; font-size: 14px; border: 1px solid #cbd5e1;">']
            if re.match(r'^\|(?:[\s\-:]+\|)+$', s): continue
            cells = [c.strip() for c in s.split('|')[1:-1]]
            tds = ''
            for idx, c in enumerate(cells):
                bg = "#F8FAFC" if idx == 0 else "#FFFFFF"
                fw = "bold" if idx == 0 else "normal"
                co = "#1e293b" if idx == 0 else "#334155"
                tds += f'<td style="border:1px solid #cbd5e1; padding:12px; background-color:{bg}; font-weight:{fw}; color:{co};">{c}</td>'
            table_html.append(f'<tr>{tds}</tr>')
        else:
            if in_table:
                in_table = False
                table_html.append('</table></div>')
                chunks.append("".join(table_html))
                table_html = []
            curr_paragraph.append(s)
            if len(curr_paragraph) >= 2:
                chunks.append(f'<p style="font-size:16px; line-height:2.2; margin-bottom:35px; color:#222;">{" ".join(curr_paragraph)}</p>')
                curr_paragraph = []

    if curr_paragraph: chunks.append(f'<p style="font-size:16px; line-height:2.2; margin-bottom:35px; color:#222;">{" ".join(curr_paragraph)}</p>')
    if in_table:
        table_html.append('</table></div>')
        chunks.append("".join(table_html))
    return "".join(chunks)

def main():
    print("🔄 [쿠팡 파트너스 API V2] 정석 포스팅 공장을 가동합니다.")
    coupang_access = (os.environ.get("COUPANG_ACCESS_KEY") or os.environ.get("ACCESS_KEY") or "").strip()
    coupang_secret = (os.environ.get("COUPANG_SECRET_KEY") or os.environ.get("SECRET_KEY") or "").strip()
    gemini_key = (os.environ.get("API_KEY") or "").strip()
    token_base64 = (os.environ.get("TOKEN_PICKLE_BASE64") or "").strip()
    if not (gemini_key and token_base64 and coupang_access and coupang_secret): return

    try:
        credentials = pickle.loads(base64.b64decode(token_base64))
        blogger_service = build('blogger', 'v3', credentials=credentials)
        if not TEST_MODE:
            if check_already_posted(blogger_service, BLOG_ID): return
        else:
            print("🧪 [테스트 모드 ON] 30분 중복 방지를 패스합니다.")
    except Exception as e: print(f"⚠️ 사전 중복 체크 에러: {e}")

    products = get_coupang_v2_products(coupang_access, coupang_secret)
    if not products: return
    
    target_p = products[0]
    raw_img = target_p.get('productImage', '').strip()
    img_url = 'https:' + raw_img if raw_img.startswith('//') else ('https://' + raw_img if raw_img and not raw_img.startswith('http') else raw_img)
    link_url = target_p.get('productUrl', target_p.get('landingUrl', ''))
    p_name = target_p.get('productName', '쿠팡 인기 추천 상품').replace('"', "'")
    raw_price = target_p.get('productPrice', 0)
    p_price_str = f"{int(raw_price):,}원" if str(raw_price).isdigit() else f"{raw_price}원"

    print(f"🛒 오늘의 집중 분석 주인공 선정 완료: {p_name}")

    ai_client = genai.Client(api_key=gemini_key)
    
    # ★ 페르소나 대공사: 허세 인플루언서 퇴출 -> 담백한 쇼핑 에디터 탑재
    prompt = (
        "너는 과장된 허세 없이 핵심 정보만 담백하게 짚어주는 '스마트 쇼핑 전문 에디터'야. "
        "아래 상품에 대해 스마트폰에서 가독성 좋게 정독되는 집중 분석 칼럼을 작성해줘.\n\n"
        f"[상품명]: {p_name}\n[할인 가격]: {p_price_str}\n\n"
        "[필수 집필 지침]\n"
        "1. [인사말 절대 금지]: '안녕하세요 여러분', '구독자님들', '오늘 소개할 제품은~' 같은 오글거리는 블로거 인사말을 서론에 단 한 글자도 쓰지 마라. 첫 문장부터 소비자가 겪는 현실적 페인포인트를 짚으며 본론으로 진입하라.\n"
        "2. [담백한 어조]: 인위적인 억지 공감(~했던 경험 다들 있으시죠?) 대신 객관적 스펙과 실사용 팩트 기반의 분석 톤을 유지하라.\n"
        "3. [제목]: '상품명 + 핵심 키워드(내돈내산 솔직 후기, 장단점, 가격 비교)' 조합으로 클릭률 높게 작성.\n"
        "4. [도입부(hook_intro)]: 공백 포함 450자 이상 상세 집필.\n"
        "5. [스펙 비교표(spec_table)]: 마크다운 표 문법(|구분|상세 스펙|) 주요 스펙 4행 이상 정리.\n"
        "6. [장단점 본문(pros_cons_body)]: 공백 포함 700자 이상. 장점 3가지와 '구매 전 알아야 할 주의점 1가지' 솔직 작성.\n"
        "7. [구매 추천 대상(verdict)]: 공백 포함 300자 이상 요약.\n"
        "8. [카드 요약(card_bullets)]: 핵심 장점 딱 3문장(각 15자 이내) 배열 출력.\n"
        "9. [태그(tags)]: 상품과 직결되는 핵심 키워드 딱 3~4개 배열 출력.\n"
        "10. [퍼머링크(slug)]: 영어 소문자 단어 2~3개 하이픈 연결.\n"
        "11. [금지어]: '파소나', 'PASONA', '카피라이팅', 'AI', '인공지능', '자동화', '프로그램'.\n\n"
        "반드시 아래 JSON 규격만 출력하라.\n"
        "{\n"
        '  "title": "에어팟 프로 2세대 내돈내산 솔직 후기",\n'
        '  "slug": "airpods-pro-2-review",\n'
        '  "hook_intro": "도입부...",\n'
        '  "spec_table": "|스펙|내용| 표...",\n'
        '  "pros_cons_body": "장단점...",\n'
        '  "verdict": "추천 대상...",\n'
        '  "card_bullets": ["노이즈캔슬링 압도적", "C타입 호환성 굿", "배터리 30시간 지속"],\n'
        '  "tags": ["에어팟프로2", "무선이어폰추천"]\n'
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

    # ★ 3중 방어 이미지 추출 실행
    best_img_url, is_card = get_bulletproof_image_url(img_url, p_name, p_price_str, ai_data.get('card_bullets', []))

    def generate_adsense_html():
        return f'<div class="adsense-container" style="margin:30px auto; text-align:center;"><script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client={GOOGLE_ADSENSE_CLIENT}" crossorigin="anonymous"></script><ins class="adsbygoogle" style="display:block" data-ad-client="{GOOGLE_ADSENSE_CLIENT}" data-ad-slot="{GOOGLE_ADSENSE_SLOT}" data-ad-format="auto" data-full-width-responsive="true"></ins><script>(adsbygoogle = window.adsbygoogle || []).push({{}});</script></div>'

    cta_btn = f'<div style="margin:40px 0;"><a href="{link_url}" target="_blank" style="background-color:#E52528; color:#FFFFFF; font-size:17px; font-weight:bold; padding:18px 30px; text-decoration:none; border-radius:10px; display:inline-block; box-shadow:0 6px 16px rgba(229,37,40,0.25);">🚀 실시간 최저가 및 로켓배송 가능 여부 확인하기</a></div>'

    sub_txt = "👆 이미지를 터치하면 실시간 최저가 페이지로 이동합니다" if is_card else "👆 사진을 터치하면 로켓배송 확인 페이지로 이동합니다"
    hero_html = f'<div style="margin:35px 0;"><a href="{link_url}" target="_blank"><img src="{best_img_url}" alt="{title}" style="max-width:90%; border-radius:16px; box-shadow:0 10px 25px rgba(0,0,0,0.08);"/></a><p style="font-size:12px; color:#94a3b8; margin-top:8px;">{sub_txt}</p></div>'

    ftc_msg = "<p style='color:#94a3b8; font-size:12px; margin-bottom:25px;'>💡 이 포스팅은 쿠팡 파트너스 활동의 일환으로, 이에 따른 일정액의 수수료를 제공받습니다.</p>"
    h3_style = 'font-size: 20px; font-weight: bold; color: #1e293b; margin: 45px 0 22px 0; display: inline-block; border-bottom: 2px solid #E52528; padding-bottom: 6px;'

    inner_content = ftc_msg + generate_adsense_html() + \
                    format_paragraphs(ai_data['hook_intro']) + hero_html + cta_btn + \
                    f'<h3 style="{h3_style}">💡 주요 스펙 한눈에 보기</h3>' + format_paragraphs(ai_data['spec_table']) + \
                    f'<h3 style="{h3_style}">🔍 내돈내산 장단점 집중 분석</h3>' + format_paragraphs(ai_data['pros_cons_body']) + \
                    f'<h3 style="{h3_style}">🎯 총평: 이런 분들께 추천합니다</h3>' + format_paragraphs(ai_data['verdict']) + \
                    cta_btn + generate_adsense_html()

    final_html = f'<div style="max-width: 660px; margin: 0 auto; text-align: center; word-break: keep-all; font-family: -apple-system, BlinkMacSystemFont, Pretendard, Roboto, sans-serif; color: #222222;">{inner_content}</div>'

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
    except Exception as e: print(f"❌ 최종 발행 에러: {e}")

if __name__ == "__main__":
    main()
