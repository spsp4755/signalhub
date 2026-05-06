import os
import sys
import tempfile
from pathlib import Path


os.environ["DB_PATH"] = os.path.join(tempfile.gettempdir(), "signalhub-smoke.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

try:
    os.remove(os.environ["DB_PATH"])
except FileNotFoundError:
    pass

from fastapi.testclient import TestClient

from app import settings_store
from app.main import app
from app.services import mailer


def _sample_outcome(keyword_id: int, keyword: str) -> dict:
    return {
        "id": keyword_id,
        "keyword_id": keyword_id,
        "keyword": keyword,
        "run_type": "auto",
        "result": (
            "## 뉴스 브리핑\n"
            f"### [{keyword} 뉴스](https://news.example.com/{keyword})\n"
            "시장 변화와 실무 영향까지 정리한 내용입니다.\n\n"
            "## 논문·모델 브리핑\n"
            f"### [{keyword} 논문](https://paper.example.com/{keyword})\n"
            "핵심 아이디어와 적용 한계를 정리한 내용입니다."
        ),
        "tags": [keyword, "AI"],
        "sources": {
            "geeknews": [
                {
                    "title": f"{keyword} news source",
                    "url": f"https://news.example.com/{keyword}",
                }
            ],
            "aitimes": [],
            "arxiv": [
                {
                    "title": f"{keyword} paper source",
                    "url": f"https://paper.example.com/{keyword}",
                    "authors": ["A. Researcher"],
                }
            ],
            "huggingface_papers": [],
            "huggingface_models": [],
        },
        "arxiv": 1,
        "huggingface": 0,
        "geeknews": 1,
        "aitimes": 0,
    }


def main() -> None:
    with TestClient(app) as client:
        assert client.get("/healthz").json() == {"ok": True}

        bulk = client.post(
            "/keywords/bulk",
            json={"names": ["RAG", "MoE", "GraphRAG", "RAG"], "enabled": True},
        )
        assert bulk.status_code == 201, bulk.text
        assert len(bulk.json()["created"]) == 3

        keywords = client.get("/keywords").json()
        selected = [k for k in keywords if k["name"] in {"RAG", "MoE", "GraphRAG"}]
        ids_by_name = {k["name"]: k["id"] for k in selected}
        assert set(ids_by_name) == {"RAG", "MoE", "GraphRAG"}

        recipient = client.post(
            "/recipients",
            json={"email": "ops@example.com", "enabled": True},
        )
        assert recipient.status_code == 201, recipient.text
        recipient_id = recipient.json()["id"]

        patch = client.patch(
            f"/recipients/{recipient_id}/keywords",
            json={"keyword_ids": [ids_by_name["RAG"], ids_by_name["MoE"]]},
        )
        assert patch.status_code == 200, patch.text
        assert set(patch.json()["keyword_ids"]) == {ids_by_name["RAG"], ids_by_name["MoE"]}

        settings_store.update(
            {"smtp_host": "smtp.local", "smtp_sender": "signalhub@example.com"}
        )

        sent = []
        original_send = mailer._send_via_smtp

        def fake_send(msg, recipients, cfg):
            sent.append((msg, recipients, cfg))

        mailer._send_via_smtp = fake_send
        try:
            outcomes = [
                {
                    "keyword_id": ids_by_name["RAG"],
                    "keyword": "RAG",
                    "ok": True,
                    "id": 1,
                    "outcome": _sample_outcome(ids_by_name["RAG"], "RAG"),
                },
                {
                    "keyword_id": ids_by_name["GraphRAG"],
                    "keyword": "GraphRAG",
                    "ok": True,
                    "id": 2,
                    "outcome": _sample_outcome(ids_by_name["GraphRAG"], "GraphRAG"),
                },
            ]
            assert mailer.send_digest_email(outcomes)
        finally:
            mailer._send_via_smtp = original_send

        assert len(sent) == 1
        msg, recipients, _ = sent[0]
        assert recipients == ["ops@example.com"]
        html_body = msg.get_body(preferencelist=("html",)).get_content()
        assert "RAG" in html_body
        assert "GraphRAG" not in html_body
        assert "https://news.example.com/RAG" in html_body
        assert html_body.index("뉴스") < html_body.index("논문")

    print("smoke ok")


if __name__ == "__main__":
    main()
