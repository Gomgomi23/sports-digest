# Sports Digest — 스포츠 산업 뉴스 브리핑

스포츠 산업 뉴스를 자동 수집·요약하는 정적 대시보드. GitHub Pages로 서빙: **https://gomgomi23.github.io/sports-digest/**

- `index.html` — 단일 페이지 UI (Tailwind CDN, DESIGN-bmw-m 디자인 적용)
- `data/news.json` · `data/digest.json` — 표시 데이터 (자동 생성물)
- `scripts/update_news.py` — Google News RSS로 뉴스 수집 → `data/news.json`
- `scripts/generate_digest.py` — Gemini로 일일 다이제스트 생성 → `data/digest.json`

## 갱신은 GitHub Actions가 전담한다 (⚠️ 중요)

이 저장소의 데이터는 **오직 GitHub Actions 워크플로로만** 갱신된다. Actions 러너는 GitHub 인프라에서 돌기 때문에 `git push`·외부 API에 네트워크 제약이 없다.

| 워크플로 | 스케줄 | 하는 일 |
|---|---|---|
| `.github/workflows/update-news.yml` | 6시간마다 + 수동 | 뉴스 수집 → `news.json` push |
| `.github/workflows/daily-digest.yml` | 매일 08:00 KST(23:00 UTC) + 수동 | 뉴스 수집 + Gemini 다이제스트 → `news.json`·`digest.json` push |

두 워크플로 모두 push 시 `fetch → rebase → 재시도` 루프로 동시 실행 충돌을 흡수한다.

### 필요한 설정
- **Repo Secret `GEMINI_API_KEY`** — `daily-digest`의 다이제스트 생성에 필수. Settings → Secrets and variables → Actions.

## ⚠️ 원격 Claude 세션에서 갱신 스크립트를 돌리지 말 것

`update_news.py`/`generate_digest.py`를 **원격 Claude Code(웹/클라우드) 세션의 정기 루틴으로 실행하지 않는다.** 그 실행 환경은 조직 네트워크 정책상 `api.github.com` 아웃바운드가 차단되어("GitHub access to this repository is not enabled for this session") 매일 아침 실패한다.

- 정기 자동화가 필요하면 **위 GitHub Actions에 추가/수정**한다 (원격 세션 크론·루틴 금지).
- 스크립트 자체는 `api.github.com`을 쓰지 않는다(Google News RSS + Gemini뿐). GitHub 연동은 Actions의 `git push`가 담당한다.
- 로컬에서 수동 확인만 할 때는 정적 서버로 `index.html`을 열면 된다(파이썬이 MS Store 스텁이면 Node 정적 서버 사용).
