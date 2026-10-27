"""Knowledge Source domain service managing source origins."""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictException, NotFoundException
from app.db.models.enums import KnowledgeSourceType
from app.db.models.knowledge_source import KnowledgeSource
from app.schemas.knowledge import KnowledgeSourceCreate, KnowledgeSourceUpdate
from app.schemas.pagination import PageParams


class KnowledgeSourceService:
    """Operations for registering and querying knowledge origins."""

    @staticmethod
    def create_source(db: Session, source_in: KnowledgeSourceCreate) -> KnowledgeSource:
        """Create a new knowledge source verifying name uniqueness."""
        existing = db.scalar(select(KnowledgeSource).where(KnowledgeSource.name == source_in.name))
        if existing:
            raise ConflictException(
                message=f"KnowledgeSource with name '{source_in.name}' already exists.",
                details={"name": source_in.name, "existing_id": existing.id},
            )

        source = KnowledgeSource(
            name=source_in.name,
            source_type=source_in.source_type.value
            if hasattr(source_in.source_type, "value")
            else str(source_in.source_type),
            description=source_in.description,
            uri=source_in.uri,
            is_active=source_in.is_active,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    @staticmethod
    def get_or_create_source(
        db: Session,
        name: str,
        source_type: KnowledgeSourceType = KnowledgeSourceType.OTHER,
        description: str | None = None,
        uri: str | None = None,
    ) -> KnowledgeSource:
        """Retrieve existing source by name or create a new one deterministically."""
        existing = db.scalar(select(KnowledgeSource).where(KnowledgeSource.name == name))
        if existing:
            return existing

        source = KnowledgeSource(
            name=name,
            source_type=source_type.value if hasattr(source_type, "value") else str(source_type),
            description=description,
            uri=uri,
            is_active=True,
        )
        db.add(source)
        db.commit()
        db.refresh(source)
        return source

    @staticmethod
    def get_source(db: Session, source_id: str) -> KnowledgeSource:
        """Retrieve source by ID or raise NotFoundException."""
        source = db.get(KnowledgeSource, source_id)
        if not source:
            raise NotFoundException(
                message=f"KnowledgeSource with ID '{source_id}' not found.",
                details={"source_id": source_id},
            )
        return source

    @staticmethod
    def list_sources(
        db: Session,
        page_params: PageParams,
        active_only: bool = True,
    ) -> tuple[list[KnowledgeSource], int]:
        """List knowledge sources with pagination."""
        query = select(KnowledgeSource)
        count_query = select(func.count(KnowledgeSource.id))

        if active_only:
            query = query.where(KnowledgeSource.is_active.is_(True))
            count_query = count_query.where(KnowledgeSource.is_active.is_(True))

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(KnowledgeSource.name.asc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @staticmethod
    def update_source(
        db: Session,
        source_id: str,
        updates: KnowledgeSourceUpdate,
    ) -> KnowledgeSource:
        """Update knowledge source attributes."""
        source = KnowledgeSourceService.get_source(db, source_id)
        update_dict = updates.model_dump(exclude_unset=True)

        if "name" in update_dict and update_dict["name"] != source.name:
            existing = db.scalar(
                select(KnowledgeSource).where(KnowledgeSource.name == update_dict["name"])
            )
            if existing and existing.id != source.id:
                raise ConflictException(
                    message=f"KnowledgeSource with name '{update_dict['name']}' already exists.",
                    details={"name": update_dict["name"]},
                )

        if "source_type" in update_dict and update_dict["source_type"]:
            st = update_dict["source_type"]
            source.source_type = st.value if hasattr(st, "value") else str(st)

        for key, value in update_dict.items():
            if key != "source_type" and value is not None:
                setattr(source, key, value)

        db.commit()
        db.refresh(source)
        return source
