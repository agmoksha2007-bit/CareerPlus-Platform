"""
PURPOSE
-------
Business logic for CareerVault: create, retrieve, list, update, and delete
vault items. This layer depends ONLY on CareerVaultRepository — it never
imports Beanie or app.models.career_vault.CareerVaultItem directly, and it
never constructs a MongoDB query itself.

Per Milestone 2 Step 4's design, the create path's metadata validation
happens entirely in the request schema (CareerVaultItemCreateRequest),
before this service is ever called. The UPDATE path's metadata validation
happens here instead, because it depends on the existing item's item_type
— information only this layer has access to, after loading the item via
the repository.
"""
from beanie import PydanticObjectId

from app.core.exceptions import CareerVaultItemNotFoundError
from app.models.career_vault import VaultItemType
from app.repositories.career_vault_repository import CareerVaultRepository
from app.schemas.career_vault import CareerVaultItemPublic, _validate_metadata_for_type

# NOTE on importing a "private" (underscore-prefixed) function across
# module boundaries: _validate_metadata_for_type was deliberately built
# in Step 4 as shared dispatch logic for EXACTLY this situation — the
# create schema's own validator uses it, and this service's update path
# needs the identical item_type -> metadata-schema mapping. Duplicating
# that lookup here would let the two copies drift out of sync; importing
# the single shared implementation is the intentional choice, not an
# architecture violation. See Step 4's docstring for the same reasoning.


class CareerVaultService:
    """
    Orchestrates CareerVaultRepository to implement the five CareerVault
    operations. Holds no state beyond the repository it's constructed
    with — cheap to create per-request, same pattern as AuthService.
    """

    def __init__(self, vault_repository: CareerVaultRepository):
        self._vault_repo = vault_repository

    async def create_item(
        self,
        user_id: PydanticObjectId,
        item_type: VaultItemType,
        title: str,
        description: str | None,
        metadata: dict,
        attachment_url: str | None,
    ) -> CareerVaultItemPublic:
        """
        Creates a new vault item for the given user.

        No metadata validation happens here — by the time this method is
        called, `metadata` has already been validated against `item_type`
        by CareerVaultItemCreateRequest's own model_validator (Step 4).
        This method's job is purely orchestration: hand the
        already-validated fields to the repository, map the result to
        the public response shape.

        Returns:
            CareerVaultItemPublic: the newly created item.
        """
        item = await self._vault_repo.create(
            user_id=user_id,
            item_type=item_type,
            title=title,
            description=description,
            metadata=metadata,
            attachment_url=attachment_url,
        )
        return self._to_public(item)

    async def get_item(self, item_id: str, user_id: PydanticObjectId) -> CareerVaultItemPublic:
        """
        Retrieves a single vault item by id, scoped to the requesting
        user.

        Raises:
            CareerVaultItemNotFoundError: if no matching item exists for
                this id + user_id combination (whether because the id is
                malformed, doesn't exist, or belongs to a different
                user — all three are indistinguishable at the repository
                layer, per Step 3's design, and stay indistinguishable
                here).
        """
        item = await self._vault_repo.get_by_id(item_id, user_id)
        if item is None:
            raise CareerVaultItemNotFoundError("Vault item not found")
        return self._to_public(item)

    async def list_items(
        self,
        user_id: PydanticObjectId,
        item_type: VaultItemType | None = None,
    ) -> list[CareerVaultItemPublic]:
        """
        Lists all vault items belonging to the given user, optionally
        filtered to one item_type. An empty result is a normal outcome
        (a user with no vault items yet) — never an error.
        """
        items = await self._vault_repo.list_by_user(user_id, item_type)
        return [self._to_public(item) for item in items]

    async def update_item(
        self,
        item_id: str,
        user_id: PydanticObjectId,
        updates: dict,
    ) -> CareerVaultItemPublic:
        """
        Applies a partial update to an existing vault item.

        `updates` is expected to be built by the router via
        CareerVaultItemUpdateRequest.model_dump(exclude_unset=True) — so
        it contains ONLY the fields the client actually sent, not every
        field defaulted to None. This matters specifically for
        `metadata`: its presence as a key in `updates` means "the client
        provided new metadata," which must be validated; its ABSENCE
        means "leave existing metadata untouched," which needs no
        validation at all.

        Business rule enforced here (per Step 5's requirement): if
        `updates` includes a new `metadata` value, it is validated
        against the EXISTING item's item_type — not any value the client
        might have supplied, since CareerVaultItemUpdateRequest (Step 4)
        deliberately does not accept item_type at all. This is only
        possible here, after loading the existing item, which is why
        this validation could not live in the schema layer.

        Args:
            item_id: the vault item to update.
            user_id: the requesting user — the update is scoped to this
                user regardless of what item_id claims to be.
            updates: dict of fields to change, as produced by
                CareerVaultItemUpdateRequest.model_dump(exclude_unset=True).

        Returns:
            CareerVaultItemPublic: the item after the update is applied.

        Raises:
            CareerVaultItemNotFoundError: if no matching item exists for
                this id + user_id combination.
            (Pydantic ValidationError, surfaced as a 422 via the global
            handler): if `updates["metadata"]` doesn't match the
            existing item's item_type.
        """
        existing_item = await self._vault_repo.get_by_id(item_id, user_id)
        if existing_item is None:
            raise CareerVaultItemNotFoundError("Vault item not found")

        if "metadata" in updates and updates["metadata"] is not None:
            updates["metadata"] = _validate_metadata_for_type(
                existing_item.item_type, updates["metadata"]
            )

        updated_item = await self._vault_repo.update(item_id, user_id, updates)
        if updated_item is None:
            # Defensive: should be unreachable, since existing_item was
            # just confirmed to exist for this exact id + user_id pair
            # above. Kept as an explicit check rather than assuming the
            # repository call between the two lines can never fail, per
            # this codebase's "no silent shortcuts" standard.
            raise CareerVaultItemNotFoundError("Vault item not found")

        return self._to_public(updated_item)

    async def delete_item(self, item_id: str, user_id: PydanticObjectId) -> None:
        """
        Deletes a vault item, scoped to the requesting user.

        Raises:
            CareerVaultItemNotFoundError: if no matching item exists for
                this id + user_id combination.
        """
        deleted = await self._vault_repo.delete(item_id, user_id)
        if not deleted:
            raise CareerVaultItemNotFoundError("Vault item not found")

    # ------------------------------------------------------------------
    # Private helper — the one place that maps a repository-returned
    # CareerVaultItem onto the public response schema, same pattern as
    # AuthService._to_user_public in Milestone 1.
    # ------------------------------------------------------------------

    @staticmethod
    def _to_public(item) -> CareerVaultItemPublic:
        return CareerVaultItemPublic(
            id=str(item.id),
            item_type=item.item_type,
            title=item.title,
            description=item.description,
            metadata=item.metadata,
            attachment_url=item.attachment_url,
            created_at=item.created_at,
            updated_at=item.updated_at,
        )