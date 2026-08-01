"""
PURPOSE
-------
Data access layer for the CareerVaultItem aggregate. This is the ONLY file
(besides app/core/database.py, which just registers the model) that queries
app.models.career_vault.CareerVaultItem directly.

CareerVaultService (a later step) depends on THIS class, never on Beanie or
CareerVaultItem directly — same pattern as UserRepository in Milestone 1.
No business rules live here, only database operations: what counts as a
valid item_type, whether a title is required, etc. are schema/service
concerns, not this file's.
"""
from datetime import datetime, timezone

from beanie import PydanticObjectId

from app.models.career_vault import CareerVaultItem, VaultItemType


class CareerVaultRepository:
    """
    Every read/write method here is scoped by user_id at the QUERY level,
    not via a separate ownership check performed after fetching. This is
    a deliberate security property: there is no code path in this class
    where an item belonging to one user can be returned, updated, or
    deleted by a request scoped to a different user_id.
    """

    async def create(
        self,
        user_id: PydanticObjectId,
        item_type: VaultItemType,
        title: str,
        description: str | None = None,
        metadata: dict | None = None,
        attachment_url: str | None = None,
    ) -> CareerVaultItem:
        """
        Creates and persists a new CareerVaultItem. user_id is always
        supplied by the caller (the service layer, sourced from the
        authenticated user) — never inferred here.
        """
        item = CareerVaultItem(
            user_id=user_id,
            item_type=item_type,
            title=title,
            description=description,
            metadata=metadata or {},
            attachment_url=attachment_url,
        )
        await item.insert()
        return item

    async def get_by_id(
        self, item_id: str, user_id: PydanticObjectId
    ) -> CareerVaultItem | None:
        """
        Fetches a single item by id, scoped to the given user_id in the
        SAME query. Returns None if the id is malformed, doesn't exist,
        or belongs to a different user — all three cases are
        indistinguishable at this layer by design (see design notes
        above), so a caller can't accidentally leak which case occurred.
        """
        try:
            object_id = PydanticObjectId(item_id)
        except Exception:
            return None

        return await CareerVaultItem.find_one(
            CareerVaultItem.id == object_id,
            CareerVaultItem.user_id == user_id,
        )

    async def list_by_user(
        self,
        user_id: PydanticObjectId,
        item_type: VaultItemType | None = None,
    ) -> list[CareerVaultItem]:
        """
        Returns all vault items belonging to user_id, optionally filtered
        to a single item_type. Sorted by created_at descending (most
        recently added first) — a reasonable default list ordering.
        """
        query = CareerVaultItem.find(CareerVaultItem.user_id == user_id)
        if item_type is not None:
            query = query.find(CareerVaultItem.item_type == item_type)

        return await query.sort(-CareerVaultItem.created_at).to_list()

    async def update(
        self,
        item_id: str,
        user_id: PydanticObjectId,
        updates: dict,
    ) -> CareerVaultItem | None:
        """
        Applies a partial update to an existing item, scoped to user_id.
        `updates` is a dict of {field_name: new_value} — only the keys
        present are changed; any field not included is left untouched.
        updated_at is set here, unconditionally, on every successful
        update, so the service layer never needs to remember to do it.

        Returns the updated item, or None if no matching item was found
        for this id + user_id combination (same semantics as
        get_by_id).
        """
        item = await self.get_by_id(item_id, user_id)
        if item is None:
            return None

        for field_name, value in updates.items():
            setattr(item, field_name, value)

        from datetime import datetime, timezone

        item.updated_at = datetime.now(timezone.utc)
        await item.save()
        return item

    async def delete(self, item_id: str, user_id: PydanticObjectId) -> bool:
        """
        Deletes an item scoped to user_id. Returns True if a matching
        item was found and deleted, False if no matching item existed
        for this id + user_id combination — the caller (service layer)
        decides what False should mean to an API consumer (typically a
        404), not this method.
        """
        item = await self.get_by_id(item_id, user_id)
        if item is None:
            return False

        await item.delete()
        return True