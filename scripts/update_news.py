import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
import html as html_lib
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import requests

KST = timezone(timedelta(hours=9))

KEYWORDS = [
    ("스포츠 중계권",               "스포츠 중계권"),
    ("스포츠 OTT 쿠팡플레이 DAZN",  "스포츠 OTT"),
    ("스포츠 스타트업 투자",         "스포츠 스타트업"),
    ("스포츠 기술 혁신",             "스포츠 기술"),
    ("스포츠 데이터 분석",           "스포츠 데이터"),
    ("스포츠 VR AR 가상현실",        "스포츠 VR/AR"),
    ("sports broadcasting rights",   "스포츠 중계권"),
    ("sports OTT streaming",         "스포츠 OTT"),
    ("sports startup investment",    "스포츠 스타트업"),
    ("sports technology innovation", "스포츠 기술"),
    ("sports data analytics",        "스포츠 데이터"),
    ("sports VR AR",                 "스포츠 VR/AR"),
]

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/124.0 Safari/537.36",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8",
})


def fetch_google_news(query, category, max_items=4):
    url = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko".format(
        urllib.parse.quote(query)
    )
    articles = []
    try:
        resp = SESSION.get(url, timeout=15)
        root = ET.fromstring(resp.content)
        for item in root.findall(".//item")[:max_items]:
            title_raw = item.findtext("title", "").strip()
            link      = item.findtext("link", "").strip()
            pub_date  = item.findtext("pubDate", "")
            # RSS description 텍스트 추출 (HTML 태그 제거)
            desc_raw  = item.findtext("description", "")
            desc_text = re.sub(r"<[^>]+>", "", desc_raw).strip()
            desc_text = html_lib.unescape(desc_text)

            if " - " in title_raw:
                title, source = title_raw.rsplit(" - ", 1)
                title, source = title.strip(), source.strip()
            else:
                title, source = title_raw, ""

            try:
                date_str = parsedate_to_datetime(pub_date).astimezone(KST).strftime("%Y-%m-%d")
            except Exception:
                date_str = datetime.now(KST).strftime("%Y-%m-%d")

            if title and link:
                articles.append({
                    "title":    title,
                    "url":      link,
                    "source":   source,
                    "summary":  desc_text if len(desc_text) > 20 else "",
                    "category": category,
                    "date":     date_str,
                })
    except Exception as e:
        print(f"[WARN] RSS fetch failed ({query}): {e}")
    return articles


def fetch_summary_from_url(url):
    """기사 URL에서 og:description / meta description 추출."""
    try:
        resp = SESSION.get(url, timeout=8, allow_redirects=True)
        final_url = resp.url
        html = resp.text[:65536]

        # 최초 3건만 디버그 출력
        if getattr(fetch_summary_from_url, "_debug_count", 0) < 3:
            fetch_summary_from_url._debug_count = getattr(fetch_summary_from_url, "_debug_count", 0) + 1
            print(f"    [DEBUG] final_url: {final_url[:80]}")
            og = re.search(r'property=["\']og:description["\']', html, re.IGNORECASE)
            print(f"    [DEBUG] og:description tag found: {bool(og)}")

        patterns = [
            r'<meta\b[^>]*\bproperty\s*=\s*"og:description"\s*[^>]*\bcontent\s*=\s*"([^"]{20,})"',
            r'<meta\b[^>]*\bcontent\s*=\s*"([^"]{20,})"\s*[^>]*\bproperty\s*=\s*"og:description"',
            r"<meta\b[^>]*\bproperty\s*=\s*'og:description'\s*[^>]*\bcontent\s*=\s*'([^']{20,})'",
            r'<meta\b[^>]*\bname\s*=\s*"description"\s*[^>]*\bcontent\s*=\s*"([^"]{20,})"',
            r'<meta\b[^>]*\bcontent\s*=\s*"([^"]{20,})"\s*[^>]*\bname\s*=\s*"description"',
            r'<meta\b[^>]*\bname\s*=\s*"twitter:description"\s*[^>]*\bcontent\s*=\s*"([^"]{20,})"',
        ]
        for pattern in patterns:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                return html_lib.unescape(m.group(1)).strip()[:300]

        # JSON-LD fallback
        ld = re.search(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', html, re.DOTALL | re.IGNORECASE)
        if ld:
            try:
                data = json.loads(ld.group(1))
                if isinstance(data, list):
                    data = data[0]
                desc = data.get("description", "")
                if desc and len(desc) > 20:
                    return desc[:300]
            except Exception:
                pass
    except Exception as e:
        pass
    return ""


# ── 뉴스 수집 ──────────────────────────────────────────────
seen_urls = set()
all_articles = []

for query, category in KEYWORDS:
    for article in fetch_google_news(query, category):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

all_articles.sort(key=lambda x: x["date"], reverse=True)

# ── 요약 보강 (RSS desc가 없는 기사만 URL fetch) ────────────
print(f"기사 {len(all_articles)}건 수집 완료. 요약 보강 중...")
for i, article in enumerate(all_articles):
    if not article["summary"]:
        article["summary"] = fetch_summary_from_url(article["url"])
    status = "OK  " if article["summary"] else "없음"
    print(f"  [{i+1:02d}/{len(all_articles)}] {status} — {article['title'][:40]}")

# ── 저장 ──────────────────────────────────────────────────
news_data = {
    "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)"),
    "articles":   all_articles,
}

with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(news_data, f, ensure_ascii=False, indent=2)

filled = sum(1 for a in all_articles if a["summary"])
print(f"\n완료: {len(all_articles)}건 저장 (요약 {filled}/{len(all_articles)}건)")
