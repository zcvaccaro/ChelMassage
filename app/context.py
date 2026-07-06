"""Tenant context for multi-tenant SaaS readiness."""

from dataclasses import dataclass

from app.config import BusinessConfig, load_business_config


@dataclass
class TenantContext:
    """Passed through workflows and repositories for tenant isolation."""

    tenant_id: str
    config: BusinessConfig

    @classmethod
    def default(cls) -> "TenantContext":
        return cls(tenant_id="default", config=load_business_config())
