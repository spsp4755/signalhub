# SignalHub

AI / Agents 분야의 기술 동향을 자동 수집·요약하고 팀에 공유하는 Intelligence Hub입니다.

- 수집: arXiv, HuggingFace, GeekNews RSS, AITimes
- 분석: OpenAI-compatible API (vLLM / Ollama 등)
- 저장: SQLite
- 스케줄: 매일 자동 실행
- 알림: SMTP 메일 발송
- 프런트엔드: 모든 정적 라이브러리 로컬 포함
- 오프라인 배포: wheelhouse 포함, `Podman` 기반 빌드 가능

## 오프라인/폐쇄망 준비

이 번들은 Python 패키지 의존성을 `wheels/`에 포함하고, `Dockerfile`은 인터넷 없이 설치되도록 구성되어 있습니다.

사전에 준비해야 하는 것은 베이스 이미지뿐입니다.

1. 인터넷이 되는 환경에서 베이스 이미지를 저장합니다.
   `podman pull docker.io/library/python:3.13-slim`
   `podman save -o python-3.13-slim.tar docker.io/library/python:3.13-slim`
2. 폐쇄망으로 `python-3.13-slim.tar` 와 이 프로젝트 전체를 반입합니다.
3. 폐쇄망에서 베이스 이미지를 로드합니다.
   `podman load -i python-3.13-slim.tar`
4. 프로젝트 디렉터리에서 이미지를 빌드합니다.
   `podman build -t signalhub:offline .`

## 실행

```bash
podman run -d \
  --name signalhub \
  -p 8765:8765 \
  -v ./data:/app/data \
  signalhub:offline
```

브라우저: `http://localhost:8765`

## Podman에서 호스트 LLM 연결

Podman 5.4 계열에서는 내부 호스트명으로 `host.containers.internal` 과 `host.docker.internal` 을 사용할 수 있습니다.

앱 설정에서 다음 중 하나를 `vllm_base_url` 로 사용하세요.

- `http://host.containers.internal:11434/v1`
- `http://host.docker.internal:11434/v1`

Podman은 이 호스트명을 기본 제공하므로 별도 `extra_hosts` 없이도 동작하도록 맞췄습니다.

## 릴리즈 아카이브 생성

```bash
bash scripts/build_release.sh latest
```

`podman` 이 있으면 `podman`, 없으면 `docker` 를 자동으로 사용합니다.

## 참고

- `data/analysis.db` 가 존재하면 기존 키워드/분석 이력이 함께 반입됩니다.
- 완전히 새 환경으로 시작하려면 `data/analysis.db` 를 제외한 상태로 배포하세요.
