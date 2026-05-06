import json
import re

from openai import OpenAI

from .. import settings_store
from ..collectors.arxiv_collector import Paper
from ..collectors.geeknews_collector import NewsItem


SYSTEM_PROMPT = (
    "너는 한국어로 답변하는 기술 동향 분석가다. "
    "주어진 뉴스, 논문, 모델 정보를 읽고 반드시 한국어 마크다운으로 구조적으로 정리한다. "
    "제목이나 초록을 그대로 옮기지 말고, 왜 중요한지와 실무 영향까지 해석한다. "
    "각 항목 제목은 URL이 있으면 반드시 [제목](URL) 형식으로 쓴다. "
    "코드/다이어그램이 의미 있을 때만 ```language ...``` 또는 ```mermaid ...``` 블록을 사용한다."
)

USER_TEMPLATE = """아래 자료를 읽고 다음 마크다운 형식으로 작성해라.

## 핵심 요약
- 3~5개 불릿으로 오늘 동향의 핵심을 설명한다.
- 단순 번역/복붙이 아니라, 어떤 변화가 있고 왜 중요한지까지 쓴다.

## 뉴스 브리핑
각 뉴스별로 `### [제목](URL)` 형식의 소제목을 쓰고, 아래 내용을 2~4문장으로 정리한다.
- 새로 나온 사실
- 업계/제품/연구 흐름에서의 의미
- 실무자가 확인해야 할 포인트

## 논문·모델 브리핑
각 논문/모델별로 `### [제목](URL)` 형식의 소제목을 쓰고, 아래 내용을 2~4문장으로 정리한다.
- 핵심 아이디어
- 기존 접근과 다른 점
- 적용 가능성과 한계

## 공통 트렌드
3개 이내 포인트로 뉴스와 논문/모델을 연결지어 해석한다.

## 실무 적용 결론
팀에서 바로 점검하거나 실험해볼 만한 항목을 2~3문장으로 제안한다.

마지막 줄에는 반드시 아래 형식으로 토픽 태그를 출력해라. JSON 배열만, 주석 없이.

### KEYWORDS
["기술용어1", "기술용어2", "기술용어3", "기술용어4", "기술용어5"]

--- 자료 ---
{body}
"""


def build_prompt(papers: list[Paper], news: list[NewsItem]) -> str:
    parts: list[str] = []
    for n in news:
        parts.append(f"[뉴스] {n.title}\nURL: {n.url}\n요약: {n.summary}")
    for p in papers:
        authors = ", ".join(p.authors[:5]) if p.authors else "-"
        parts.append(
            f"[논문/모델] {p.title}\nURL: {p.url}\n저자: {authors}\n요약: {p.summary}"
        )
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
