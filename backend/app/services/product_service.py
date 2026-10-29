"""Product domain service implementing business operations and catalog querying."""

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.exceptions import NotFoundException, ValidationException
from app.db.models.enums import ActorType
from app.db.models.product import Product, ProductVariant
from app.schemas.pagination import PageParams
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.audit_service import AuditService


class ProductService:
    """Deterministic business operations for the catalog."""

    @staticmethod
    def create_product(
        db: Session,
        product_in: ProductCreate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> Product:
        """Create a new product with optional initial variants."""
        # Check SKU uniqueness
        existing_sku = db.scalar(select(Product).where(Product.sku == product_in.sku))
        if existing_sku:
            raise ValidationException(
                message=f"Product with SKU '{product_in.sku}' already exists.",
                details={"sku": product_in.sku},
            )

        # Check slug uniqueness
        existing_slug = db.scalar(select(Product).where(Product.slug == product_in.slug))
        if existing_slug:
            raise ValidationException(
                message=f"Product with slug '{product_in.slug}' already exists.",
                details={"slug": product_in.slug},
            )

        # Check for duplicate variant suffixes within the product payload
        seen_suffixes = set()
        for variant_in in product_in.variants:
            if variant_in.sku_suffix in seen_suffixes:
                raise ValidationException(
                    message=f"Duplicate variant SKU suffix '{variant_in.sku_suffix}' in product payload.",
                    details={"sku_suffix": variant_in.sku_suffix},
                )
            seen_suffixes.add(variant_in.sku_suffix)

        try:
            product_data = product_in.model_dump(exclude={"variants", "metadata_"})
            product = Product(
                **product_data,
                metadata_=product_in.metadata_,
            )
            db.add(product)
            db.flush()

            # Add variants
            for variant_in in product_in.variants:
                variant_data = variant_in.model_dump(exclude={"metadata_"})
                variant = ProductVariant(
                    product_id=product.id,
                    **variant_data,
                    metadata_=variant_in.metadata_,
                )
                db.add(variant)

            db.flush()
            db.refresh(product)

            AuditService.record(
                db=db,
                action="PRODUCT_CREATED",
                entity_type="Product",
                entity_id=product.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Created product '{product.name}' with SKU '{product.sku}'",
                after_state={
                    "sku": product.sku,
                    "name": product.name,
                    "base_price": str(product.base_price),
                    "variants_count": len(product_in.variants),
                },
            )
            db.commit()
            return product
        except IntegrityError as err:
            db.rollback()
            raise ValidationException(
                message=f"Product with SKU '{product_in.sku}' or slug '{product_in.slug}' already exists.",
                details={"sku": product_in.sku, "slug": product_in.slug},
            ) from err
        except Exception:
            db.rollback()
            raise

    @staticmethod
    def get_product(db: Session, product_id: str) -> Product:
        """Retrieve product by ID or raise NotFoundException."""
        stmt = (
            select(Product).where(Product.id == product_id).options(selectinload(Product.variants))
        )
        product = db.scalar(stmt)
        if not product:
            raise NotFoundException(
                message=f"Product with ID '{product_id}' not found.",
                details={"product_id": product_id},
            )
        return product

    @staticmethod
    def get_by_sku(db: Session, sku: str) -> Product | None:
        """Find product by unique SKU."""
        stmt = select(Product).where(Product.sku == sku).options(selectinload(Product.variants))
        return db.scalar(stmt)

    @staticmethod
    def get_by_slug(db: Session, slug: str) -> Product | None:
        """Find product by unique SEO slug."""
        stmt = select(Product).where(Product.slug == slug).options(selectinload(Product.variants))
        return db.scalar(stmt)

    @staticmethod
    def list_products(
        db: Session,
        page_params: PageParams,
        active_only: bool = True,
        material: str | None = None,
        category: str | None = None,
    ) -> tuple[list[Product], int]:
        """List products with pagination and business filtering."""
        query = select(Product).options(selectinload(Product.variants))
        count_query = select(func.count(Product.id))

        if active_only:
            query = query.where(Product.is_active.is_(True))
            count_query = count_query.where(Product.is_active.is_(True))

        if material:
            query = query.where(Product.material.ilike(f"%{material}%"))
            count_query = count_query.where(Product.material.ilike(f"%{material}%"))

        if category:
            query = query.where(Product.category.ilike(f"%{category}%"))
            count_query = count_query.where(Product.category.ilike(f"%{category}%"))

        total = db.scalar(count_query) or 0
        items = list(
            db.scalars(
                query.order_by(Product.created_at.desc())
                .offset(page_params.offset)
                .limit(page_params.limit)
            ).all()
        )
        return items, total

    @staticmethod
    def search_catalog(
        db: Session,
        query: str,
        limit: int = 5,
        active_only: bool = True,
    ) -> list[Product]:
        """Search active catalog products by keywords in name, material, category, SKU, or description."""
        stmt = select(Product).options(selectinload(Product.variants))
        if active_only:
            stmt = stmt.where(Product.is_active.is_(True))

        terms = [t.strip() for t in query.split() if len(t.strip()) > 2]
        if terms:
            conditions = []
            for term in terms[:5]:
                pattern = f"%{term}%"
                conditions.append(Product.name.ilike(pattern))
                conditions.append(Product.material.ilike(pattern))
                conditions.append(Product.sku.ilike(pattern))
                conditions.append(Product.category.ilike(pattern))
                conditions.append(Product.description.ilike(pattern))
            stmt = stmt.where(or_(*conditions))

        return list(db.scalars(stmt.order_by(Product.name.asc()).limit(limit)).all())

    @staticmethod
    def update_product(
        db: Session,
        product_id: str,
        updates: ProductUpdate,
        actor_id: str | None = None,
        actor_type: ActorType | str = ActorType.SYSTEM,
    ) -> Product:
        """Update existing product fields and record audit trail."""
        product = ProductService.get_product(db, product_id)
        before_state = {
            "name": product.name,
            "base_price": str(product.base_price),
            "is_active": product.is_active,
            "sku": product.sku,
            "slug": product.slug,
        }

        update_dict = updates.model_dump(exclude_unset=True)

        if "sku" in update_dict and update_dict["sku"]:
            existing_sku = db.scalar(
                select(Product).where(Product.sku == update_dict["sku"], Product.id != product.id)
            )
            if existing_sku:
                raise ValidationException(
                    message=f"Product with SKU '{update_dict['sku']}' already exists.",
                    details={"sku": update_dict["sku"]},
                )

        if "slug" in update_dict and update_dict["slug"]:
            existing_slug = db.scalar(
                select(Product).where(Product.slug == update_dict["slug"], Product.id != product.id)
            )
            if existing_slug:
                raise ValidationException(
                    message=f"Product with slug '{update_dict['slug']}' already exists.",
                    details={"slug": update_dict["slug"]},
                )

        if "metadata_" in update_dict and update_dict["metadata_"] is not None:
            product.metadata_ = {**product.metadata_, **update_dict.pop("metadata_")}

        for key, value in update_dict.items():
            if value is not None:
                setattr(product, key, value)

        try:
            db.flush()
            db.refresh(product)

            after_state = {
                "name": product.name,
                "base_price": str(product.base_price),
                "is_active": product.is_active,
                "sku": product.sku,
                "slug": product.slug,
            }

            AuditService.record(
                db=db,
                action="PRODUCT_UPDATED",
                entity_type="Product",
                entity_id=product.id,
                actor_id=actor_id,
                actor_type=actor_type,
                description=f"Updated product '{product.name}'",
                before_state=before_state,
                after_state=after_state,
            )
            db.commit()
            return product
        except IntegrityError as err:
            db.rollback()
            raise ValidationException(
                message="Product update failed due to duplicate SKU or slug conflict.",
                details={"product_id": product_id},
            ) from err
        except Exception:
            db.rollback()
            raise
