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
                    "summary":  "",
                    "category": category,
                    "date":     date_str,
                })
    except Exception as e:
        print(f"[WARN] RSS fetch failed ({query}): {e}")
    return articles


def extract_meta(html, *names):
    """property 또는 name 기준으로 <meta> content 값을 추출."""
    for name in names:
        for pattern in [
            rf'<meta\b[^>]*\bproperty\s*=\s*["\']{re.escape(name)}["\'][^>]*\bcontent\s*=\s*"([^"]*)"',
            rf'<meta\b[^>]*\bcontent\s*=\s*"([^"]*)"\s[^>]*\bproperty\s*=\s*["\']{re.escape(name)}["\']',
            rf'<meta\b[^>]*\bproperty\s*=\s*["\']{re.escape(name)}["\'][^>]*\bcontent\s*=\s*\'([^\']*)\'',
            rf'<meta\b[^>]*\bname\s*=\s*["\']{re.escape(name)}["\'][^>]*\bcontent\s*=\s*"([^"]*)"',
            rf'<meta\b[^>]*\bcontent\s*=\s*"([^"]*)"\s[^>]*\bname\s*=\s*["\']{re.escape(name)}["\']',
        ]:
            m = re.search(pattern, html, re.IGNORECASE)
            if m:
                text = html_lib.unescape(m.group(1)).strip()
                if len(text) > 20:
                    return text[:300]
    return ""


def fetch_summary(url):
    """기사 URL에서 og:description 또는 meta description 추출."""
    try:
        resp = SESSION.get(url, timeout=8, allow_redirects=True)
        html = resp.text[:65536]
        return extract_meta(html, "og:description", "description", "twitter:description")
    except Exception:
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

# ── 요약 추출 ──────────────────────────────────────────────
print(f"기사 {len(all_articles)}건 수집 완료. 요약 추출 중...")
for i, article in enumerate(all_articles):
    summary = fetch_summary(article["url"])
    article["summary"] = summary
    print(f"  [{i+1:02d}/{len(all_articles)}] {'OK  ' if summary else '없음'} — {article['title'][:40]}")

# ── 저장 ──────────────────────────────────────────────────
news_data = {
    "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)"),
    "articles":   all_articles,
}

with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(news_data, f, ensure_ascii=False, indent=2)

filled = sum(1 for a in all_articles if a["summary"])
print(f"\n완료: {len(all_articles)}건 저장 (요약 {filled}건)")
