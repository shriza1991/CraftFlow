"""Domain Enums for controlled business state transitions and channels."""

from enum import StrEnum


class Channel(StrEnum):
    """Communication channels supported by CraftFlow."""

    WEBSITE = "WEBSITE"
    WHATSAPP = "WHATSAPP"
    INSTAGRAM = "INSTAGRAM"
    EMAIL = "EMAIL"
    PHONE = "PHONE"
    OTHER = "OTHER"


class CustomerSource(StrEnum):
    """Lead / Customer acquisition sources."""

    WEBSITE = "WEBSITE"
    WHATSAPP = "WHATSAPP"
    INSTAGRAM = "INSTAGRAM"
    FACEBOOK = "FACEBOOK"
    GOOGLE = "GOOGLE"
    REFERRAL = "REFERRAL"
    DIRECT = "DIRECT"
    OTHER = "OTHER"


class LeadStatus(StrEnum):
    """Deterministic sales opportunity pipeline statuses."""

    NEW = "NEW"
    CONTACTED = "CONTACTED"
    QUALIFIED = "QUALIFIED"
    PROPOSAL = "PROPOSAL"
    NEGOTIATION = "NEGOTIATION"
    WON = "WON"
    LOST = "LOST"


class LeadPriority(StrEnum):
    """Sales lead urgency / priority ranking."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class ConversationStatus(StrEnum):
    """Interaction session statuses."""

    OPEN = "OPEN"
    CLOSED = "CLOSED"
    ARCHIVED = "ARCHIVED"


class MessageDirection(StrEnum):
    """Inbound from customer vs outbound to customer."""

    INBOUND = "INBOUND"
    OUTBOUND = "OUTBOUND"


class SenderType(StrEnum):
    """Origin of a conversation message."""

    CUSTOMER = "CUSTOMER"
    AI = "AI"
    HUMAN_AGENT = "HUMAN_AGENT"
    SYSTEM = "SYSTEM"


class MessageType(StrEnum):
    """Message payload format."""

    TEXT = "TEXT"
    IMAGE = "IMAGE"
    VIDEO = "VIDEO"
    AUDIO = "AUDIO"
    DOCUMENT = "DOCUMENT"
    LOCATION = "LOCATION"
    OTHER = "OTHER"


class MessageStatus(StrEnum):
    """Lifecycle status of a message."""

    RECEIVED = "RECEIVED"
    PROCESSING = "PROCESSING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    READ = "READ"
    FAILED = "FAILED"


class FollowUpStatus(StrEnum):
    """Scheduled follow-up statuses."""

    PENDING = "PENDING"
    SCHEDULED = "SCHEDULED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AgentRunStatus(StrEnum):
    """Execution status of an AI agent run."""

    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class ToolCallStatus(StrEnum):
    """Execution status of a tool invocation."""

    REQUESTED = "REQUESTED"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    REJECTED = "REJECTED"


class ActorType(StrEnum):
    """Auditing actor types."""

    SYSTEM = "SYSTEM"
    HUMAN = "HUMAN"
    AI_AGENT = "AI_AGENT"
    ADMIN = "ADMIN"
    WEBHOOK = "WEBHOOK"


class ProductAvailability(StrEnum):
    """Stock / production availability."""

    IN_STOCK = "IN_STOCK"
    MADE_TO_ORDER = "MADE_TO_ORDER"
    DISCONTINUED = "DISCONTINUED"


class KnowledgeSourceType(StrEnum):
    """Origin categories for business knowledge."""

    PRODUCT_CATALOG = "PRODUCT_CATALOG"
    FAQ = "FAQ"
    BUSINESS_POLICY = "BUSINESS_POLICY"
    SHIPPING_POLICY = "SHIPPING_POLICY"
    INSTALLATION_GUIDE = "INSTALLATION_GUIDE"
    CARE_GUIDE = "CARE_GUIDE"
    MATERIAL_GUIDE = "MATERIAL_GUIDE"
    SALES_GUIDE = "SALES_GUIDE"
    CUSTOMIZATION_GUIDE = "CUSTOMIZATION_GUIDE"
    WARRANTY = "WARRANTY"
    COMPANY_INFORMATION = "COMPANY_INFORMATION"
    INTERNAL_PROCESS = "INTERNAL_PROCESS"
    OTHER = "OTHER"


class KnowledgeDocumentStatus(StrEnum):
    """Lifecycle status of a knowledge document."""

    DRAFT = "DRAFT"
    ACTIVE = "ACTIVE"
    ARCHIVED = "ARCHIVED"


class IndexingStatus(StrEnum):
    """Vector indexing and embedding status."""

    PENDING = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
