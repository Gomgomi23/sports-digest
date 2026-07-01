import json
import os
import re
from datetime import datetime, timezone, timedelta
import anthropic

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

    return f"""당신은 스포츠 산업 전문 애널리스트입니다. 다음 뉴스 기사들을 분석하여 {date_str}의 스포츠 산업 일일 다이제스트를 아래 JSON 스키마에 맞게 작성해주세요. 마크다운 코드블록 없이 순수 JSON만 출력하세요.

=== 뉴스 기사 목록 ===
{articles_text}

=== JSON 스키마 ===
{{
  "date": "{date_str}",
  "top3": [
    {{"rank": 1, "title": "가장 중요한 뉴스 제목 (간결하게)", "body": "2~3문장 핵심 요약"}},
    {{"rank": 2, "title": "두 번째 중요 뉴스 제목", "body": "2~3문장 핵심 요약"}},
    {{"rank": 3, "title": "세 번째 중요 뉴스 제목", "body": "2~3문장 핵심 요약"}}
  ],
  "sections": [
    {{
      "title": "이모지 섹션제목 (예: 🎙️ 스포츠 중계권 & OTT)",
      "subsections": [
        {{
          "title": "소제목 (예: 국내) — 소제목이 필요 없으면 빈 문자열",
          "items": ["**굵은키워드:** 내용 설명", "**굵은키워드:** 내용 설명"]
        }}
      ]
    }}
  ],
  "media": [
    {{"type": "YouTube", "title": "제목", "description": "한 줄 설명"}},
    {{"type": "블로그", "title": "제목", "description": "한 줄 설명"}}
  ]
}}

작성 지침:
- top3: 오늘 가장 중요한 뉴스 3건 선정, 각 2~3문장으로 요약
- sections: 뉴스 내용에 따라 해당하는 섹션만 포함 (최대 4개)
  * 🎙️ 스포츠 중계권 & OTT — 소제목: 국내, 글로벌 OTT 동향
  * 💰 스포츠 스타트업 & 투자 — 소제목: 투자 동향, 정부 지원 (없으면 빈 문자열)
  * 🤖 스포츠 기술 & 데이터 & VR — 소제목 빈 문자열
  * 🌍 해외 주요 동향 — 소제목 빈 문자열
- media: 뉴스에서 언급된 유튜브/블로그/리서치 자료 (없으면 빈 배열 [])
- 각 items 항목: "**핵심키워드:** 설명" 형식으로 한 줄
- 한국어로 작성, 비즈니스 분석 톤 유지"""


def generate_digest(articles):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    today = datetime.now(KST)
    date_str = f"{today.year}년 {today.month}월 {today.day}일 ({WEEKDAYS[today.weekday()]})"

    prompt = build_prompt(articles, date_str)

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        messages=[{"role": "user", "content": prompt}]
    )

    content = message.content[0].text.strip()
    content = re.sub(r'^```(?:json)?\s*', '', content)
    content = re.sub(r'\s*```$', '', content)
    content = content.strip()

    return json.loads(content)


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


if __name__ == "__main__":
    main()
