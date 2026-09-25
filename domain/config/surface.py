"""CloudLens System Configuration Surface.

Defines the configuration surface for:
1. database
2. cache
3. queue
4. object_storage
5. secret_store
6. identity_provider
7. notification_channels
8. observability
9. rate_limits
10. pagination
11. export_limits

Every field has a documented default and an explicit is_secret indicator where appropriate.
"""

from pydantic import BaseModel, Field


class DatabaseConfig(BaseModel):
    """Database connectivity, connection pooling, and timeout configuration."""

    host: str = Field(default="localhost", description="PostgreSQL host address")
    port: int = Field(default=5432, description="PostgreSQL listening port")
    name: str = Field(default="cloudlens", description="PostgreSQL database name")
    user: str = Field(default="cloudlens", description="PostgreSQL application username")
    password: str = Field(
        default="cloudlens_dev_password",
        description="PostgreSQL password",
        json_schema_extra={"is_secret": True},
    )
    pool_size: int = Field(default=10, description="SQLAlchemy connection pool base size")
    max_overflow: int = Field(
        default=20, description="SQLAlchemy connection pool max overflow connections"
    )
    timeout_seconds: float = Field(
        default=30.0, description="Database connection and query timeout in seconds"
    )


class CacheConfig(BaseModel):
    """Distributed cache (Redis) configuration."""

    url: str = Field(
        default="redis://localhost:6379/0",
        description="Redis connection URL",
        json_schema_extra={"is_secret": True},
    )
    host: str = Field(default="localhost", description="Redis host address")
    port: int = Field(default=6379, description="Redis listening port")
    password: str = Field(
        default="",
        description="Redis auth password",
        json_schema_extra={"is_secret": True},
    )
    default_ttl_seconds: int = Field(default=3600, description="Default cache TTL in seconds")
    max_connections: int = Field(default=50, description="Redis connection pool limit")


class QueueConfig(BaseModel):
    """Asynchronous task queue (Celery/Redis) configuration."""

    broker_url: str = Field(
        default="redis://localhost:6379/1",
        description="Celery broker URL",
        json_schema_extra={"is_secret": True},
    )
    result_backend: str = Field(
        default="redis://localhost:6379/2",
        description="Celery task result backend URL",
        json_schema_extra={"is_secret": True},
    )
    default_queue: str = Field(default="cloudlens_tasks", description="Default task queue name")
    task_timeout_seconds: int = Field(
        default=300, description="Maximum task run duration before revocation"
    )


class ObjectStorageConfig(BaseModel):
    """S3-compatible object storage (MinIO / AWS S3) configuration."""

    endpoint_url: str = Field(
        default="http://localhost:9000", description="S3 / MinIO endpoint URL"
    )
    bucket_name: str = Field(
        default="cloudlens-data", description="Primary object store bucket name"
    )
    access_key: str = Field(
        default="cloudlens_minio",
        description="S3 access key ID",
        json_schema_extra={"is_secret": True},
    )
    secret_key: str = Field(
        default="cloudlens_minio_password",
        description="S3 secret access key",
        json_schema_extra={"is_secret": True},
    )
    region: str = Field(default="us-east-1", description="Object store region identifier")
    use_ssl: bool = Field(
        default=False, description="Whether to use TLS/SSL for S3 endpoint connections"
    )


class SecretStoreConfig(BaseModel):
    """External secret management (HashiCorp Vault / Cloud KMS) configuration."""

    backend_type: str = Field(default="vault", description="Secret store type: 'vault' or 'env'")
    vault_url: str = Field(
        default="http://localhost:8200", description="HashiCorp Vault server URL"
    )
    vault_token: str = Field(
        default="dev-vault-token-cloudlens",
        description="Vault authentication token",
        json_schema_extra={"is_secret": True},
    )
    mount_point: str = Field(default="secret", description="Vault KV v2 mount point")


class IdentityProviderConfig(BaseModel):
    """OpenID Connect / OAuth2 Identity Provider configuration."""

    issuer_url: str = Field(
        default="https://auth.cloudlens.internal/oauth2/default",
        description="OIDC token issuer authority URL",
    )
    client_id: str = Field(default="cloudlens-api", description="OAuth2 client identifier")
    client_secret: str = Field(
        default="dev-client-secret",
        description="OAuth2 client secret",
        json_schema_extra={"is_secret": True},
    )
    audience: str = Field(default="cloudlens-api", description="Expected JWT token audience")
    jwks_uri: str = Field(
        default="https://auth.cloudlens.internal/.well-known/jwks.json",
        description="JSON Web Key Set URI for token verification",
    )


class NotificationChannelsConfig(BaseModel):
    """Alerting & notification channels configuration."""

    email_smtp_host: str = Field(
        default="localhost", description="SMTP server host for email notifications"
    )
    email_smtp_port: int = Field(default=587, description="SMTP server submission port")
    email_sender: str = Field(
        default="alerts@cloudlens.internal", description="From address for outgoing alerts"
    )
    webhook_timeout_seconds: float = Field(
        default=10.0, description="HTTP webhook dispatch timeout in seconds"
    )
    slack_webhook_url: str = Field(
        default="",
        description="Slack incoming webhook URL",
        json_schema_extra={"is_secret": True},
    )


class ObservabilityConfig(BaseModel):
    """OpenTelemetry and Prometheus observability endpoints."""

    otel_exporter_endpoint: str = Field(
        default="http://localhost:4317",
        description="OpenTelemetry gRPC/HTTP collector endpoint",
    )
    service_name: str = Field(default="cloudlens-platform", description="OTel service name tag")
    sample_rate: float = Field(default=1.0, description="Trace sampling ratio (0.0 to 1.0)")
    log_level: str = Field(
        default="INFO", description="Standard logging level: DEBUG, INFO, WARNING, ERROR"
    )
    prometheus_port: int = Field(default=9090, description="Prometheus metrics exporter port")


class RateLimitsConfig(BaseModel):
    """API ingress rate limit configurations."""

    default_requests_per_minute: int = Field(
        default=600,
        description="Standard authenticated user requests per minute",
    )
    burst_capacity: int = Field(default=100, description="Token bucket burst capacity")
    auth_requests_per_minute: int = Field(
        default=60,
        description="Unauthenticated login/auth endpoint rate limit per minute",
    )


class PaginationConfig(BaseModel):
    """API pagination default and upper bounds."""

    default_page_size: int = Field(
        default=50, description="Default number of items returned per page"
    )
    max_page_size: int = Field(
        default=250, description="Absolute maximum page size permitted by API"
    )


class ExportLimitsConfig(BaseModel):
    """Data export size and row limits."""

    max_rows_sync_export: int = Field(
        default=5000,
        description="Maximum rows permitted for direct synchronous CSV/Excel downloads",
    )
    max_rows_async_export: int = Field(
        default=500000,
        description="Maximum rows permitted for asynchronous background export jobs",
    )
    max_export_file_size_mb: int = Field(
        default=50,
        description="Maximum uncompressed file size for exports in megabytes",
    )


class SystemConfig(BaseModel):
    """Root platform configuration combining all system surfaces."""

    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    queue: QueueConfig = Field(default_factory=QueueConfig)
    object_storage: ObjectStorageConfig = Field(default_factory=ObjectStorageConfig)
    secret_store: SecretStoreConfig = Field(default_factory=SecretStoreConfig)
    identity_provider: IdentityProviderConfig = Field(default_factory=IdentityProviderConfig)
    notification_channels: NotificationChannelsConfig = Field(
        default_factory=NotificationChannelsConfig
    )
    observability: ObservabilityConfig = Field(default_factory=ObservabilityConfig)
    rate_limits: RateLimitsConfig = Field(default_factory=RateLimitsConfig)
    pagination: PaginationConfig = Field(default_factory=PaginationConfig)
    export_limits: ExportLimitsConfig = Field(default_factory=ExportLimitsConfig)
