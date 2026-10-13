"""ORM models. Import everything so Alembic and the app see the full metadata."""
from app.models.assets import (  # noqa: F401
    Asset,
    AssetAnalysis,
    AssetDerivative,
    AssetSegment,
    AssetTag,
    Collection,
    CollectionAsset,
    ExternalReference,
)
from app.models.base import SCHEMA_VERSION, Base  # noqa: F401
from app.models.brand import (  # noqa: F401
    AestheticConcept,
    Brand,
    BrandVersion,
    ColorToken,
    DesignToken,
    Guideline,
    KnowledgeDomain,
    KnowledgeEntry,
    KnowledgeRevision,
    Palette,
    Principle,
    TypographySystem,
)
from app.models.identity import (  # noqa: F401
    ApiToken,
    AuditLog,
    AuthSession,
    Organization,
    OrganizationUser,
    Permission,
    Role,
    RolePermission,
    User,
)
from app.models.knowledge import (  # noqa: F401
    AiSuggestion,
    ContextPackage,
    Embedding,
    ExportJob,
    ImportJob,
    Integration,
    ProcessingJob,
    Project,
    PromptTemplate,
    Relationship,
    Review,
)
