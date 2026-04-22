import json
import re

from openai import OpenAI

from .. import settings_store
from ..collectors.arxiv_collector import Paper
from ..collectors.geeknews_collector import NewsItem


SYSTEM_PROMPT = (
    "너는 한국어로 답변하는 기술 동향 분석가다. "
    "주어진 논문과 뉴스를 읽고, 반드시 한국어 마크다운으로 간결하고 구조적으로 정리한다. "
    "불필요한 추론 과정은 생략하고 결론만 명료하게 작성한다. "
    "코드/다이어그램이 의미 있을 때만 ```language ...``` 또는 ```mermaid ...``` 블록을 사용한다."
)

USER_TEMPLATE = """아래 자료를 읽고 다음 마크다운 형식으로 작성해라.

## 핵심 요약
- 2~3개 불릿으로 오늘 동향의 핵심

## 논문 요약
각 논문별 소제목(###) + 1~2문장 설명 + 기여점/의의

## 뉴스 요약
각 뉴스별 소제목(###) + 1~2문장 설명

## 공통 트렌드
3개 이내 포인트. 논문과 뉴스를 연결지어 해석.

## 실무 적용 결론
1~2문장.

마지막 줄에는 반드시 아래 형식으로 토픽 태그를 출력해라. JSON 배열만, 주석 없이.

### KEYWORDS
["기술용어1", "기술용어2", "기술용어3", "기술용어4", "기술용어5"]

--- 자료 ---
{body}
"""


def build_prompt(papers: list[Paper], news: list[NewsItem]) -> str:
    parts: list[str] = []
    for p in papers:
        parts.append(f"[논문] {p.title}\n{p.summary}")
    for n in news:
        parts.append(f"[뉴스] {n.title}\n{n.summary}")
    return "\n\n".join(parts) if parts else "(수집된 자료 없음)"


def _extract_text(message) -> str:
    content = (getattr(message, "content", None) or "").strip()
    reasoning = (getattr(message, "reasoning", None) or "").strip()

    if content and len(content) >= 40:
        return content
    if content and reasoning:
        return f"{content}\n\n--- (reasoning trace) ---\n{reasoning}"
    if reasoning:
        return reasoning
    return content or "(빈 응답)"


_KEYWORDS_RE = re.compile(r"###\s*KEYWORDS\s*\n+\s*(\[[^\[\]]*\])", re.IGNORECASE)


def _parse_tags(text: str) -> list[str]:
    match = _KEYWORDS_RE.search(text)
    if not match:
        return []
    try:
        raw = json.loads(match.group(1))
    except Exception:
        return []
    if not isinstance(raw, list):
        return []
    tags = []
    seen = set()
    for item in raw:
        t = str(item).strip()
        if t and t.lower() not in seen:
            seen.add(t.lower())
            tags.append(t)
    return tags[:12]


def _strip_tags_section(text: str) -> str:
    return re.sub(r"\n*###\s*KEYWORDS[\s\S]*$", "", text, flags=re.IGNORECASE).rstrip()


def analyze(papers: list[Paper], news: list[NewsItem]) -> tuple[str, list[str]]:
    cfg = settings_store.get_all()
    client = OpenAI(api_key=cfg["vllm_api_key"], base_url=cfg["vllm_base_url"])
    body = build_prompt(papers, news)
    response = client.chat.completions.create(
        model=cfg["vllm_model"],
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_TEMPLATE.format(body=body)},
        ],
        temperature=cfg["llm_temperature"],
        max_tokens=cfg["llm_max_tokens"],
    )
    raw = _extract_text(response.choices[0].message)
    tags = _parse_tags(raw)
    cleaned = _strip_tags_section(raw)
    return cleaned, tags
