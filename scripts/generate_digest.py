import json
import os
import re
from datetime import datetime, timezone, timedelta
from google import genai
from google.genai import types

KST = timezone(timedelta(hours=9))
WEEKDAYS = ['월', '화', '수', '목', '금', '토', '일']


def load_news():
    with open("data/news.json", "r", encoding="utf-8") as f:
        return json.load(f)


def build_prompt(articles, date_str):
    lines = []
    for i, a in enumerate(articles[:60], 1):
        line = f"{i}. [{a['category']}] {a['title']}"
        if a.get('summary') and len(a['summary']) > 30:
            line += f"\n   {a['summary'][:250]}"
        line += f"\n   출처: {a.get('source', '')} ({a.get('date', '')})"
        lines.append(line)

    articles_text = "\n\n".join(lines)
    n = len(articles[:60])

    return f"""당신은 스포츠 산업 전문 애널리스트입니다. 다음 뉴스 기사들을 분석하여 {date_str}의 스포츠 산업 일일 다이제스트를 아래 JSON 스키마에 맞게 작성해주세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

=== 뉴스 기사 목록 ===
{articles_text}

=== JSON 스키마 ===
{{
  "date": "{date_str}",
  "top3": [
    {{"rank": 1, "title": "가장 중요한 뉴스 제목 (간결하게)", "body": "2~3문장 핵심 요약", "article_num": 3}},
    {{"rank": 2, "title": "두 번째 중요 뉴스 제목", "body": "2~3문장 핵심 요약", "article_num": 7}},
    {{"rank": 3, "title": "세 번째 중요 뉴스 제목", "body": "2~3문장 핵심 요약", "article_num": 12}}
  ],
  "sections": [
    {{
      "title": "이모지 섹션제목 (예: 🎙️ 스포츠 중계권 & OTT)",
      "subsections": [
        {{
          "title": "소제목 (예: 국내) — 소제목이 필요 없으면 빈 문자열",
          "items": [
            {{"text": "**굵은키워드:** 내용 설명", "article_num": 2}},
            {{"text": "**굵은키워드:** 내용 설명", "article_num": 5}}
          ]
        }}
      ]
    }}
  ],
  "media": [
    {{"type": "YouTube", "title": "영상 제목", "description": "한 줄 설명", "search_query": "YouTube 검색어"}},
    {{"type": "블로그", "title": "글 제목", "description": "한 줄 설명", "search_query": "Google 검색어"}},
    {{"type": "리서치", "title": "리포트 제목", "description": "한 줄 설명", "search_query": "Google 검색어"}}
  ]
}}

작성 지침:
- top3: 오늘 가장 중요한 뉴스 3건 선정, 각 2~3문장으로 요약. article_num은 위 목록에서 대표 기사 번호 (1~{n}).
- sections: 뉴스 내용에 따라 해당하는 섹션만 포함 (최대 4개)
  * 🎙️ 스포츠 중계권 & OTT — 소제목: 국내, 글로벌 OTT 동향
  * 💰 스포츠 스타트업 & 투자 — 소제목: 투자 동향, 정부 지원 (없으면 빈 문자열)
  * 🤖 스포츠 기술 & 데이터 & VR — 소제목 빈 문자열
  * 🌍 해외 주요 동향 — 소제목 빈 문자열
- items의 article_num: 해당 아이템과 가장 관련 있는 기사 번호 (1~{n}). 직접 대응 기사가 없으면 0.
- media: 오늘 뉴스의 핵심 키워드와 관련된 콘텐츠(영상·글·리포트) 5~8개 추천. URL은 직접 쓰지 말 것.
  * search_query: YouTube 또는 Google에서 그 콘텐츠를 찾을 수 있는 구체적인 검색어 (제목+저자/채널명 등).
  * 국내외 모두 포함 — 영어권 콘텐츠도 적극 추천 (스포츠 비즈니스, OTT 전략, 스포츠테크, 투자 동향).
- 한국어로 작성, 비즈니스 분석 톤 유지"""


def attach_urls(digest, articles):
    url_map = {i + 1: a.get('url', '') for i, a in enumerate(articles[:60])}

    for item in digest.get('top3', []):
        num = item.pop('article_num', 0)
        url = url_map.get(num, '')
        if url:
            item['url'] = url

    for sec in digest.get('sections', []):
        for sub in sec.get('subsections', []):
            new_items = []
            for item in sub.get('items', []):
                if isinstance(item, str):
                    new_items.append({'text': item})
                elif isinstance(item, dict):
                    num = item.pop('article_num', 0)
                    url = url_map.get(num, '')
                    if url:
                        item['url'] = url
                    new_items.append(item)
            sub['items'] = new_items

    # search_query 필드 정리 (URL 확보는 fetch_media_urls_grounded에서 처리)
    for m in digest.get('media', []):
        m.pop('search_query', None)


def fetch_media_urls_grounded(media_items, client):
    """Gemini 검색 그라운딩으로 각 미디어 추천 항목의 실제 직접 URL을 확보한다."""
    if not media_items:
        return

    lines = "\n".join(
        f"{i}. [{'YouTube 영상' if m.get('type') == 'YouTube' else '블로그·리서치 글'}] {m.get('title', '')}"
        for i, m in enumerate(media_items, 1)
    )

    prompt = f"""다음 각 콘텐츠를 검색하여 실제 직접 URL을 찾아주세요.
YouTube 항목은 youtube.com/watch?v= 형식, 나머지는 해당 글·리포트의 직접 URL을 반환하세요.

{lines}

순수 JSON 배열만 출력하세요 (마크다운·설명 없이):
[{{"i":1,"url":"https://..."}},{{"i":2,"url":"https://..."}}]
URL을 찾지 못한 항목은 제외하세요."""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        text = response.text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        match = re.search(r'\[.*?\]', text, re.DOTALL)
        if match:
            url_map = {entry['i']: entry['url'] for entry in json.loads(match.group())}
            for i, m in enumerate(media_items, 1):
                if i in url_map:
                    m['url'] = url_map[i]
        found = sum(1 for m in media_items if m.get('url'))
        print(f"  미디어 URL 확보: {found}/{len(media_items)}건")
    except Exception as e:
        print(f"  미디어 URL 검색 실패: {e}")


def generate_digest(articles):
    client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

    today = datetime.now(KST)
    date_str = f"{today.year}년 {today.month}월 {today.day}일 ({WEEKDAYS[today.weekday()]})"

    prompt = build_prompt(articles, date_str)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)

    content = response.text.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    digest = json.loads(content)
    attach_urls(digest, articles)
    fetch_media_urls_grounded(digest.get('media', []), client)
    return digest


def main():
    data = load_news()
    articles = data.get("articles", [])

    if not articles:
        print("기사가 없어 다이제스트 생성을 건너뜁니다.")
        return

    print(f"기사 {len(articles)}건으로 다이제스트 생성 중...")

    digest = generate_digest(articles)
    digest["generated_at"] = datetime.now(KST).strftime("%Y-%m-%d %H:%M (KST)")

    with open("data/digest.json", "w", encoding="utf-8") as f:
        json.dump(digest, f, ensure_ascii=False, indent=2)

    print(f"완료: {digest.get('date', '')}")
    print(f"  Top 3: {len(digest.get('top3', []))}건")
    print(f"  섹션: {len(digest.get('sections', []))}개")
    print(f"  미디어: {len(digest.get('media', []))}개")


if __name__ == "__main__":
    main()
