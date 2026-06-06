from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_STORAGE_ROOT = PROJECT_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "knowledge-base-core"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 18080
    app_api_prefix: str = "/api/v1"
    log_level: str = "INFO"
    max_upload_size_mb: int = 50
    app_api_key: str = "change-me"
    internal_token: str = "change-me"
    provider_timeout_seconds: float = 30.0
    provider_retry_count: int = 1
    health_probe_external_services: bool = False
    allow_provider_fallbacks: bool = True
    ingestion_mode: str = "sync"
    cors_allow_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    enable_folder_source: bool = False
    folder_source_allowed_roots: str = ""
    admin_manual_user_creation_enabled: bool = False
    admin_auth_enabled: bool = False
    admin_auth_user_headers: str = "X-Authenticated-User,X-User-Id"
    admin_auth_allowed_roles: str = "platform_admin"
    retrieval_authenticated_identity_required: bool = False
    auth_session_enabled: bool = False
    auth_session_secret: str | None = None
    auth_session_ttl_seconds: int = 3600
    auth_session_issuer: str = "knowledge-base-core"
    trusted_identity_header_enabled: bool = False
    trusted_identity_user_headers: str = "X-Authenticated-User,X-User-Id"
    trusted_identity_external_source_headers: str = "X-Identity-Source,X-Auth-Issuer"
    trusted_identity_external_id_headers: str = "X-Identity-External-Id,X-Auth-Subject"
    evaluation_retrieval_user_id: str = "evaluation-service"

    database_url: str | None = None
    postgres_host: str | None = None
    postgres_port: int = 5432
    postgres_db: str | None = None
    postgres_user: str | None = None
    postgres_password: str | None = None

    redis_url: str | None = Field(default=None, validation_alias=AliasChoices("REDIS_URL", "redis_url"))
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

    storage_root: Path = Field(default_factory=lambda: DEFAULT_STORAGE_ROOT)
    raw_data_dir: Path | None = None
    processed_data_dir: Path | None = None
    sample_data_dir: Path | None = None

    zilliz_uri: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ZILLIZ_URI", "ZILLIZ_ENDPOINT", "zilliz_uri"),
    )
    zilliz_token: str | None = Field(default=None, validation_alias=AliasChoices("ZILLIZ_TOKEN", "zilliz_token"))
    zilliz_collection: str = Field(
        default="oa_rag_chunks",
        validation_alias=AliasChoices("ZILLIZ_COLLECTION", "ZILLIZ_COLLECTION_NAME", "zilliz_collection"),
    )
    vector_store_provider: str = "local"

    embedding_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_API_BASE", "EMBEDDING_BASE_URL", "embedding_api_base"),
    )
    embedding_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_API_KEY", "embedding_api_key"),
    )
    embedding_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("EMBEDDING_MODEL", "embedding_model"),
    )
    embedding_vector_size: int = Field(
        default=2560,
        validation_alias=AliasChoices("EMBEDDING_VECTOR_SIZE", "EMBEDDING_DIM", "embedding_vector_size"),
    )

    llm_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_BASE", "LLM_BASE_URL", "llm_api_base"),
    )
    llm_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_API_KEY", "llm_api_key"),
    )
    llm_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("LLM_MODEL", "llm_model"),
    )
    llm_max_tokens: int = Field(
        default=1200,
        validation_alias=AliasChoices("LLM_MAX_TOKENS", "llm_max_tokens"),
    )
    llm_temperature: float = Field(
        default=0.1,
        validation_alias=AliasChoices("LLM_TEMPERATURE", "llm_temperature"),
    )

    dify_base_url: str = "http://127.0.0.1:8000"
    dify_app_key: str | None = None
    dify_retrieval_user_id: str = "dify-external"

    bot_response_mode: str = "qa"
    bot_top_k: int = 8
    bot_dedup_ttl_seconds: int = 300
    feishu_enabled: bool = False
    feishu_app_id: str | None = None
    feishu_app_secret: str | None = None
    feishu_verification_token: str | None = None
    feishu_encrypt_key: str | None = None
    feishu_base_url: str = "https://open.feishu.cn"
    wecom_enabled: bool = False
    wecom_corp_id: str | None = None
    wecom_agent_id: str | None = None
    wecom_secret: str | None = None
    wecom_callback_token: str | None = None
    wecom_encoding_aes_key: str | None = None
    wecom_base_url: str = "https://qyapi.weixin.qq.com"

    rerank_enabled: bool = False
    rerank_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RERANK_API_BASE", "rerank_api_base"),
    )
    rerank_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RERANK_API_KEY", "rerank_api_key"),
    )
    rerank_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RERANK_MODEL", "rerank_model"),
    )

    # 权限配置
    permission_mode: str = "none"  # none=无权限检查，plugin=使用插件
    permission_plugin: str = "app.permissions.noop.NoOpPermissionChecker"  # 插件类路径

    # 图片识别配置
    image_recognition_provider: str = Field(
        default="paddle_ocr",
        validation_alias=AliasChoices("IMAGE_RECOGNITION_PROVIDER", "image_recognition_provider"),
    )
    paddle_ocr_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("PADDLE_OCR_TOKEN", "paddle_ocr_token"),
    )
    multimodal_api_base: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MULTIMODAL_API_BASE", "multimodal_api_base"),
    )
    multimodal_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MULTIMODAL_API_KEY", "multimodal_api_key"),
    )
    multimodal_model: str | None = Field(
        default=None,
        validation_alias=AliasChoices("MULTIMODAL_MODEL", "multimodal_model"),
    )
    image_recognition_timeout: float = Field(
        default=30.0,
        validation_alias=AliasChoices("IMAGE_RECOGNITION_TIMEOUT", "image_recognition_timeout"),
    )
    image_recognition_batch_size: int = Field(
        default=5,
        validation_alias=AliasChoices("IMAGE_RECOGNITION_BATCH_SIZE", "image_recognition_batch_size"),
    )

    @model_validator(mode="after")
    def validate_required_config(self) -> "Settings":
        self.zilliz_collection = self._normalize_text(
            self.zilliz_collection,
            default="oa_rag_chunks",
        )
        self.vector_store_provider = self._normalize_text(
            self.vector_store_provider,
            default="local",
        )
        self.llm_api_base = self._normalize_text(self.llm_api_base)
        self.llm_api_key = self._normalize_text(self.llm_api_key)
        self.llm_model = self._normalize_text(self.llm_model)
        self.embedding_api_base = self._normalize_text(self.embedding_api_base)
        self.embedding_api_key = self._normalize_text(self.embedding_api_key)
        self.embedding_model = self._normalize_text(self.embedding_model)
        self.zilliz_uri = self._normalize_text(self.zilliz_uri)
        self.zilliz_token = self._normalize_text(self.zilliz_token)

        if not self.database_url:
            missing = [
                name
                for name, value in (
                    ("POSTGRES_HOST", self.postgres_host),
                    ("POSTGRES_DB", self.postgres_db),
                    ("POSTGRES_USER", self.postgres_user),
                    ("POSTGRES_PASSWORD", self.postgres_password),
                )
                if not value
            ]
            if missing:
                joined = ", ".join(missing)
                raise ValueError(
                    f"Missing database settings: {joined}. "
                    "Provide DATABASE_URL or the PostgreSQL settings."
                )

        if self.max_upload_size_mb <= 0:
            raise ValueError("MAX_UPLOAD_SIZE_MB must be greater than 0.")

        if self.provider_timeout_seconds <= 0:
            raise ValueError("PROVIDER_TIMEOUT_SECONDS must be greater than 0.")

        if self.provider_retry_count < 0:
            raise ValueError("PROVIDER_RETRY_COUNT must be greater than or equal to 0.")

        self.auth_session_secret = self._normalize_text(self.auth_session_secret)
        self.auth_session_issuer = self._normalize_text(
            self.auth_session_issuer,
            default="knowledge-base-core",
        ) or "knowledge-base-core"
        if self.auth_session_ttl_seconds <= 0:
            raise ValueError("AUTH_SESSION_TTL_SECONDS must be greater than 0.")
        if self.auth_session_enabled and not self.auth_session_secret:
            raise ValueError("AUTH_SESSION_SECRET is required when AUTH_SESSION_ENABLED=true.")

        if self.vector_store_provider == "local" and self.zilliz_uri and self.zilliz_token:
            self.vector_store_provider = "zilliz"

        self.rerank_api_base = self._normalize_text(self.rerank_api_base)
        self.rerank_api_key = self._normalize_text(self.rerank_api_key)
        self.rerank_model = self._normalize_text(self.rerank_model)
        self.evaluation_retrieval_user_id = self._normalize_text(
            self.evaluation_retrieval_user_id,
            default="evaluation-service",
        ) or "evaluation-service"
        self.dify_retrieval_user_id = self._normalize_text(
            self.dify_retrieval_user_id,
            default="dify-external",
        ) or "dify-external"
        self.bot_response_mode = self._normalize_text(self.bot_response_mode, default="qa") or "qa"
        if self.bot_response_mode not in {"qa", "search"}:
            raise ValueError("BOT_RESPONSE_MODE must be either 'qa' or 'search'.")
        if self.bot_top_k <= 0:
            raise ValueError("BOT_TOP_K must be greater than 0.")
        if self.bot_dedup_ttl_seconds <= 0:
            raise ValueError("BOT_DEDUP_TTL_SECONDS must be greater than 0.")
        self.feishu_app_id = self._normalize_text(self.feishu_app_id)
        self.feishu_app_secret = self._normalize_text(self.feishu_app_secret)
        self.feishu_verification_token = self._normalize_text(self.feishu_verification_token)
        self.feishu_encrypt_key = self._normalize_text(self.feishu_encrypt_key)
        self.feishu_base_url = self._normalize_text(self.feishu_base_url, default="https://open.feishu.cn") or "https://open.feishu.cn"
        self.wecom_corp_id = self._normalize_text(self.wecom_corp_id)
        self.wecom_agent_id = self._normalize_text(self.wecom_agent_id)
        self.wecom_secret = self._normalize_text(self.wecom_secret)
        self.wecom_callback_token = self._normalize_text(self.wecom_callback_token)
        self.wecom_encoding_aes_key = self._normalize_text(self.wecom_encoding_aes_key)
        self.wecom_base_url = self._normalize_text(self.wecom_base_url, default="https://qyapi.weixin.qq.com") or "https://qyapi.weixin.qq.com"
        if self.feishu_enabled and not (self.feishu_app_id and self.feishu_app_secret and self.feishu_verification_token):
            raise ValueError("FEISHU_APP_ID, FEISHU_APP_SECRET and FEISHU_VERIFICATION_TOKEN are required when FEISHU_ENABLED=true.")
        if self.wecom_enabled and not (
            self.wecom_corp_id and self.wecom_agent_id and self.wecom_secret and self.wecom_callback_token and self.wecom_encoding_aes_key
        ):
            raise ValueError("WECOM_CORP_ID, WECOM_AGENT_ID, WECOM_SECRET, WECOM_CALLBACK_TOKEN and WECOM_ENCODING_AES_KEY are required when WECOM_ENABLED=true.")

        # 图片识别配置验证
        self.image_recognition_provider = self._normalize_text(
            self.image_recognition_provider,
            default="paddle_ocr",
        ) or "paddle_ocr"
        
        # 根据提供者类型验证必需的配置
        if self.image_recognition_provider == "paddle_ocr":
            if not self.paddle_ocr_token:
                # PaddleOCR token是可选的，但如果没有配置，将无法使用
                pass
        elif self.image_recognition_provider == "multimodal":
            if not (self.multimodal_api_base and self.multimodal_api_key and self.multimodal_model):
                # 多模态提供者需要完整的配置
                pass
        
        # 规范化配置值
        self.paddle_ocr_token = self._normalize_text(self.paddle_ocr_token)
        self.multimodal_api_base = self._normalize_text(self.multimodal_api_base)
        self.multimodal_api_key = self._normalize_text(self.multimodal_api_key)
        self.multimodal_model = self._normalize_text(self.multimodal_model)
        
        # 验证超时和批量大小
        if self.image_recognition_timeout <= 0:
            raise ValueError("IMAGE_RECOGNITION_TIMEOUT must be greater than 0.")
        if self.image_recognition_batch_size <= 0:
            raise ValueError("IMAGE_RECOGNITION_BATCH_SIZE must be greater than 0.")

        return self

    @staticmethod
    def _normalize_text(value: str | None, default: str | None = None) -> str | None:
        if value is None:
            return default
        normalized = value.strip()
        if normalized == "":
            return default
        return normalized

    @property
    def sqlalchemy_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        assert self.postgres_host
        assert self.postgres_db
        assert self.postgres_user
        assert self.postgres_password
        return (
            f"postgresql+psycopg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def resolved_raw_data_dir(self) -> Path:
        return self.raw_data_dir or self.storage_root / "raw"

    @property
    def resolved_processed_data_dir(self) -> Path:
        return self.processed_data_dir or self.storage_root / "processed"

    @property
    def resolved_sample_data_dir(self) -> Path:
        return self.sample_data_dir or self.storage_root / "samples"

    @property
    def resolved_redis_url(self) -> str:
        if self.redis_url:
            return self.redis_url
        password_part = f":{self.redis_password}@" if self.redis_password else ""
        return (
            f"redis://{password_part}{self.redis_host}:{self.redis_port}/{self.redis_db}"
        )

    def ensure_storage_dirs(self) -> None:
        self.storage_root.mkdir(parents=True, exist_ok=True)
        self.resolved_raw_data_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_processed_data_dir.mkdir(parents=True, exist_ok=True)
        self.resolved_sample_data_dir.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_folder_source_allowed_roots(self) -> list[Path]:
        roots = [
            value.strip()
            for value in self.folder_source_allowed_roots.split(",")
            if value.strip()
        ]
        return [Path(root).expanduser().resolve() for root in roots]

    def is_external_service_configured(self, service_name: str) -> bool:
        mapping = {
            "zilliz": bool(self.zilliz_uri and self.zilliz_token and self.zilliz_collection),
            "embedding_provider": bool(
                self.embedding_api_base and self.embedding_api_key and self.embedding_model
            ),
            "llm_provider": bool(self.llm_api_base and self.llm_api_key and self.llm_model),
            "image_recognition": bool(
                (self.image_recognition_provider == "paddle_ocr" and self.paddle_ocr_token)
                or (self.image_recognition_provider == "multimodal" and self.multimodal_api_base and self.multimodal_api_key and self.multimodal_model)
            ),
        }
        return mapping.get(service_name, False)


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
