"""운영 환경용 FastAPI 백엔드 서버를 실행합니다.

이 스크립트는 로컬 개발용 `scripts/run_server.py`와 비슷하지만 목적이 다릅니다.

- `backend/.env.prod`를 읽습니다.
- Ollama를 자동으로 실행하지 않습니다.
- Gemini 또는 OpenAI 같은 외부 LLM API 사용을 기본 운영 방식으로 봅니다.
- fallback slot에 local gemma4를 넣을 수는 있지만, 그 경우 Ollama는 서버 실행 전에
  직접 띄워 두어야 합니다.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import uvicorn

try:
    from scripts import run_server
except ImportError:  # pragma: no cover - 파일 경로로 직접 실행할 때 사용됩니다.
    import run_server  # type: ignore[no-redef]


def prepare_prod_environment(
    backend_root: Path,
    env_file_name: str = ".env.prod",
) -> None:
    """운영 서버 실행 전에 작업 디렉터리, import 경로, 환경변수를 준비합니다.

    실제 API 키는 `backend/.env.prod`에 넣으면 됩니다. 이 파일은 gitignore에
    포함되어 있으므로 저장소에 커밋되지 않습니다.

    이미 OS나 배포 환경에서 설정된 환경변수는 `.env.prod` 값으로 덮어쓰지 않습니다.
    그래서 Docker, 클라우드 배포, CI처럼 외부에서 환경변수를 주입하는 방식도 그대로
    사용할 수 있습니다.
    """

    os.chdir(backend_root)

    # `app:create_app`, `llm.settings` 같은 backend/src 모듈을 import할 수 있게 합니다.
    src_path = str(backend_root / "src")
    if src_path not in sys.path:
        sys.path.insert(0, src_path)

    # run_server의 env loader는 KEY=VALUE 형식만 읽고 기존 환경변수는 보존합니다.
    run_server.load_env_file(backend_root / env_file_name)
    os.environ.setdefault("ENVIRONMENT", "production")


def parse_args() -> argparse.Namespace:
    """운영 서버 실행 옵션을 읽습니다."""

    parser = argparse.ArgumentParser(
        description="QuestForge Agent 백엔드를 운영 모드로 실행합니다.",
    )
    parser.add_argument("--host", default=os.getenv("HOST", "0.0.0.0"))
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", "18000")),
        help="서버 포트입니다. 기본값은 18000입니다.",
    )
    parser.add_argument("--app", default=os.getenv("APP", "app:create_app"))
    parser.add_argument(
        "--reload",
        action="store_true",
        help="uvicorn reload를 켭니다. 일반 운영 환경에서는 끈 상태로 두는 것이 좋습니다.",
    )
    return parser.parse_args()


def _provider_summary(settings: object) -> str:
    """설정된 LLM slot을 짧고 안전한 문자열로 요약합니다.

    API key는 절대 출력하지 않습니다. 서버 시작 로그에서 `default:google:gemini-2.5-flash`
    같은 값을 보면 현재 Gemini, OpenAI, local, none 중 무엇을 쓰는지 확인할 수 있습니다.
    """

    slots = [settings.default, settings.fallback1, settings.fallback2]
    return ", ".join(
        f"{slot.name}:{slot.provider}:{slot.model or '-'}" for slot in slots
    )


def main(*, env_file_name: str = ".env.prod") -> None:
    """운영 환경변수를 읽고 uvicorn 서버를 시작합니다."""

    backend_root = Path(__file__).resolve().parents[1]
    prepare_prod_environment(backend_root, env_file_name)

    # prepare_prod_environment()가 backend/src를 sys.path에 넣은 뒤 import해야 합니다.
    from llm.settings import LLMSettings

    args = parse_args()
    settings = LLMSettings.from_env()
    print(f"[QuestForge] ENVIRONMENT={os.getenv('ENVIRONMENT', '')}")
    print(f"[QuestForge] ENV_FILE={env_file_name}")
    print(f"[QuestForge] LLM slots: {_provider_summary(settings)}")
    if settings.default.provider == "none":
        print(
            "[QuestForge] Warning: no default LLM provider configured. "
            "Set GEMINI_API_KEY, GOOGLE_API_KEY, OPENAI_API_KEY, or an explicit "
            "QUESTFORGE_LLM_DEFAULT_PROVIDER in .env.prod.",
        )

    # factory=True이므로 문자열 app target인 `app:create_app`을 함수로 호출해 앱을 만듭니다.
    uvicorn.run(
        args.app,
        host=args.host,
        port=args.port,
        reload=args.reload,
        factory=True,
    )


if __name__ == "__main__":
    main()
