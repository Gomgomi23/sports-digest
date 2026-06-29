import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
import json
import re
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime

KST = timezone(timedelta(hours=9))

KEYWORDS = [
    ("스포츠 중계권",              "스포츠 중계권"),
    ("스포츠 OTT 쿠팡플레이 DAZN", "스포츠 OTT"),
    ("스포츠 스타트업 투자",       "스포츠 스타트업"),
    ("스포츠 기술 혁신",           "스포츠 기술"),
    ("스포츠 데이터 분석",         "스포츠 데이터"),
    ("스포츠 VR AR 가상현실",      "스포츠 VR/AR"),
    ("sports broadcasting rights",   "스포츠 중계권"),
    ("sports OTT streaming",         "스포츠 OTT"),
    ("sports startup investment",    "스포츠 스타트업"),
    ("sports technology innovation", "스포츠 기술"),
    ("sports data analytics",        "스포츠 데이터"),
    ("sports VR AR",                 "스포츠 VR/AR"),
]

HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"}


def fetch_google_news(query, category, max_items=4):
    url = "https://news.google.com/rss/search?q={}&hl=ko&gl=KR&ceid=KR:ko".format(
        urllib.parse.quote(query)
    )
    articles = []
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            root = ET.fromstring(resp.read())
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


def fetch_summary(url):
    """기사 URL에서 og:description 또는 meta description 추출."""
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as resp:
            # 첫 60KB만 읽어 메타태그 추출
            html = resp.read(61440).decode("utf-8", errors="ignore")

        for pattern in [
            r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+property=["\']og:description["\']',
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\'](.*?)["\']',
            r'<meta[^>]+content=["\'](.*?)["\'][^>]+name=["\']description["\']',
        ]:
            m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
            if m:
                text = re.sub(r"<[^>]+>", "", m.group(1))  # HTML 태그 제거
                text = text.strip()
                if len(text) > 20:
                    return text[:300]
    except Exception:
        pass
    return ""


# 뉴스 수집
seen_urls = set()
all_articles = []

for query, category in KEYWORDS:
    for article in fetch_google_news(query, category):
        if article["url"] not in seen_urls:
            seen_urls.add(article["url"])
            all_articles.append(article)

all_articles.sort(key=lambda x: x["date"], reverse=True)

# 요약 추가
print(f"기사 {len(all_articles)}건 수집 완료. 요약 추출 중...")
for i, article in enumerate(all_articles):
    summary = fetch_summary(article["url"])
    article["summary"] = summary
    status = "OK" if summary else "없음"
    print(f"  [{i+1}/{len(all_articles)}] {status} — {article['title'][:40]}")

news_data = {
    "updated_at": datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)"),
    "articles":   all_articles,
}

with open("data/news.json", "w", encoding="utf-8") as f:
    json.dump(news_data, f, ensure_ascii=False, indent=2)

print(f"\n완료: {len(all_articles)}건 저장")
