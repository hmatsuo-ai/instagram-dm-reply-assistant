"""環境変数・設定（.env 対応）。"""

from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# リポジトリルート（bot_server の親）
_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # 直接 Webhook を受ける場合のみ。GAS 中継なら空でよい（秘密は GAS プロパティのみ）
    line_channel_secret: str = ""
    line_channel_access_token: str = ""

    # GAS → 自営サーバ専用。設定時のみ POST /internal/suggest-replies を有効化
    internal_webhook_secret: str = Field(default="", validation_alias="INTERNAL_WEBHOOK_SECRET")

    # false にすると /webhook/line を無効化（GAS 中継のみ許可・露出削減）
    allow_direct_line_webhook: bool = Field(default=True, validation_alias="ALLOW_DIRECT_LINE_WEBHOOK")

    # カンマ区切り。空ならホワイトリスト無効（開発用）
    line_allowed_user_ids: str = ""

    # OpenAI 互換（未設定時はルールベースの固定文のみ）
    openai_api_key: Optional[str] = None
    openai_base_url: Optional[str] = None
    openai_model: str = "gpt-4o-mini"

    rag_chunks_path: Path = Field(
        default=_ROOT / "output" / "rag_chunks.jsonl",
        validation_alias="RAG_CHUNKS_PATH",
    )
    rag_top_k: int = Field(default=8, validation_alias="RAG_TOP_K")

    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "info"

    def allowed_user_ids_set(self) -> Optional[set[str]]:
        raw = self.line_allowed_user_ids.strip()
        if not raw:
            return None
        return {x.strip() for x in raw.split(",") if x.strip()}

    @field_validator("rag_chunks_path", mode="before")
    @classmethod
    def _resolve_rag_path(cls, v: Any) -> Any:
        if v is None or v == "":
            return v
        p = Path(v)
        if not p.is_absolute():
            return _ROOT / p
        return p


@lru_cache
def get_settings() -> Settings:
    return Settings()
