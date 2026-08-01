"""
PURPOSE
-------
HTTP layer for CareerVault endpoints (Milestone 2). Per the Router ->
Service -> Repository -> Model architecture, this file contains NO
business logic and NO database queries — it only parses requests (via the
schemas from app.schemas.career_vault), calls exactly one
CareerVaultService method per endpoint, and returns the result.

Every endpoint requires authentication via get_current_user
(app.dependencies.auth) and always scopes the operation to
current_user.id — this is the ONLY mechanism by which a user is
restricted to their own vault items; no ownership check is performed in
this file itself, since CareerVaultRepository (Step 3) already enforces
it at the query level for every operation.
"""
from fastapi import APIRouter, Depends, Query, status

from app.dependencies.auth import get_current_user
from app.models.career_vault import VaultItemType
from app.repositories.career_vault_repository import CareerVaultRepository
from app.schemas.career_vault import (
    CareerVaultItemCreateRequest,
    CareerVaultItemPublic,
    CareerVaultItemUpdateRequest,
)
from app.services.career_vault_service import CareerVaultService

router = APIRouter(
    prefix="/career-vault",
    tags=["CareerVault"],
)


def get_career_vault_service() -> CareerVaultService:
    """
    Provides a CareerVaultService instance, wired to a fresh
    CareerVaultRepository. Declared here (in the router file) rather
    than in app/dependencies/ for this step — see the accompanying
    explanation for why, and note this may move to
    app/dependencies/career_vault.py in a later step to match Milestone
    1's file layout exactly. Kept as a dependency provider (not
    instantiated inline in each endpoint) specifically so it can be
    overridden with a fake service in tests, same reasoning as every
    other *_service provider in this codebase.
    """
    return CareerVaultService(CareerVaultRepository())


@router.post("", response_model=CareerVaultItemPublic, status_code=status.HTTP_201_CREATED)
async def create_item(
    payload: CareerVaultItemCreateRequest,
    current_user=Depends(get_current_user),
    vault_service: CareerVaultService = Depends(get_career_vault_service),
) -> CareerVaultItemPublic:
    """
    Creates a new CareerVault item for the authenticated user.

    payload.metadata has already been validated against payload.item_type
    by CareerVaultItemCreateRequest's own model_validator (Step 4) before
    this function body runs — this endpoint does not re-validate it.

    Raises:
        (Pydantic validation errors -> HTTP 422, via the global handler):
            if the payload itself is malformed, including a metadata
            shape mismatched to item_type.
    """
    return await vault_service.create_item(
        user_id=current_user.id,
        item_type=payload.item_type,
        title=payload.title,
        description=payload.description,
        metadata=payload.metadata,
        attachment_url=payload.attachment_url,
    )


@router.get("/{item_id}", response_model=CareerVaultItemPublic)
async def get_item(
    item_id: str,
    current_user=Depends(get_current_user),
    vault_service: CareerVaultService = Depends(get_career_vault_service),
) -> CareerVaultItemPublic:
    """
    Retrieves a single CareerVault item by id, scoped to the
    authenticated user.

    Raises:
        CareerVaultItemNotFoundError (-> HTTP 404, via the global
            handler): if no item with this id exists for the
            authenticated user — including the case where the id
            belongs to a DIFFERENT user, which is deliberately
            indistinguishable from "doesn't exist at all" (see Step 3's
            design notes).
    """
    return await vault_service.get_item(item_id=item_id, user_id=current_user.id)


@router.get("", response_model=list[CareerVaultItemPublic])
async def list_items(
    item_type: VaultItemType | None = Query(
        default=None,
        description="Optional filter to only return items of this type.",
    ),
    current_user=Depends(get_current_user),
    vault_service: CareerVaultService = Depends(get_career_vault_service),
) -> list[CareerVaultItemPublic]:
    """
    Lists all CareerVault items belonging to the authenticated user,
    optionally filtered to a single item_type via the ?item_type= query
    parameter. Returns an empty list (not an error) if the user has no
    vault items yet, or none matching the filter.
    """
    return await vault_service.list_items(user_id=current_user.id, item_type=item_type)


@router.patch("/{item_id}", response_model=CareerVaultItemPublic)
async def update_item(
    item_id: str,
    payload: CareerVaultItemUpdateRequest,
    current_user=Depends(get_current_user),
    vault_service: CareerVaultService = Depends(get_career_vault_service),
) -> CareerVaultItemPublic:
    """
    Applies a partial update to an existing CareerVault item, scoped to
    the authenticated user.

    exclude_unset=True is the specific detail that makes this a PARTIAL
    update: only fields the client actually included in the request body
    are passed to the service. A field omitted entirely is left
    untouched; this is different from a field explicitly sent as null,
    which WOULD be included in the dict (with value None) and passed
    through. If payload.metadata is included, CareerVaultService
    validates it against the item's EXISTING item_type before applying
    it (Step 5) — this endpoint has no involvement in that validation.

    Raises:
        CareerVaultItemNotFoundError (-> HTTP 404, via the global
            handler): if no matching item exists for this user.
        (Pydantic validation errors -> HTTP 422, via the global handler):
            if provided metadata doesn't match the existing item's type.
    """
    updates = payload.model_dump(exclude_unset=True)
    return await vault_service.update_item(
        item_id=item_id, user_id=current_user.id, updates=updates
    )


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_item(
    item_id: str,
    current_user=Depends(get_current_user),
    vault_service: CareerVaultService = Depends(get_career_vault_service),
) -> None:
    """
    Deletes a CareerVault item, scoped to the authenticated user.
    Returns HTTP 204 with no response body on success — there is nothing
    meaningful to return once an item no longer exists.

    Raises:
        CareerVaultItemNotFoundError (-> HTTP 404, via the global
            handler): if no matching item exists for this user.
    """
    await vault_service.delete_item(item_id=item_id, user_id=current_user.id)