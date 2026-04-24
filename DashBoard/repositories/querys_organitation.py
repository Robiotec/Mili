import os
import sys
from typing import Any, Optional

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from db.connection import db as conn
else:
    from db.connection import db as conn


class OrganizationRepository:
    def __init__(self) -> None:
        self._select_organizations_query = """
            SELECT
                o.id,
                o.nombre,
                o.descripcion,
                o.propietario_usuario_id,
                o.creado_por_usuario_id,
                o.activa,
                o.creado_en,
                o.actualizado_en,
                owner_user.usuario AS propietario_usuario,
                owner_user.email AS propietario_email,
                owner_user.nombre AS propietario_nombre,
                owner_user.apellido AS propietario_apellido,
                owner_user.telefono AS propietario_telefono,
                owner_role.codigo AS propietario_rol_codigo,
                owner_role.nombre AS propietario_rol_nombre,
                owner_role.nivel_orden AS propietario_nivel_orden,
                creator_user.usuario AS creado_por_usuario,
                creator_user.email AS creado_por_email
            FROM organizaciones o
            JOIN usuarios owner_user ON owner_user.id = o.propietario_usuario_id
            JOIN roles owner_role ON owner_role.id = owner_user.rol_id
            JOIN usuarios creator_user ON creator_user.id = o.creado_por_usuario_id
            ORDER BY o.id;
        """
        self._select_organization_by_id_query = """
            SELECT
                o.id,
                o.nombre,
                o.descripcion,
                o.propietario_usuario_id,
                o.creado_por_usuario_id,
                o.activa,
                o.creado_en,
                o.actualizado_en,
                owner_user.usuario AS propietario_usuario,
                owner_user.email AS propietario_email,
                owner_user.nombre AS propietario_nombre,
                owner_user.apellido AS propietario_apellido,
                owner_user.telefono AS propietario_telefono,
                owner_role.codigo AS propietario_rol_codigo,
                owner_role.nombre AS propietario_rol_nombre,
                owner_role.nivel_orden AS propietario_nivel_orden,
                creator_user.usuario AS creado_por_usuario,
                creator_user.email AS creado_por_email
            FROM organizaciones o
            JOIN usuarios owner_user ON owner_user.id = o.propietario_usuario_id
            JOIN roles owner_role ON owner_role.id = owner_user.rol_id
            JOIN usuarios creator_user ON creator_user.id = o.creado_por_usuario_id
            WHERE o.id = %s;
        """
        self._select_organization_by_name_and_owner_query = """
            SELECT id
            FROM organizaciones
            WHERE LOWER(nombre) = LOWER(%s)
              AND propietario_usuario_id = %s
            LIMIT 1;
        """
        self._insert_organization_query = """
            INSERT INTO organizaciones (
                nombre,
                descripcion,
                propietario_usuario_id,
                creado_por_usuario_id,
                activa
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id;
        """
        self._update_organization_query = """
            UPDATE organizaciones
            SET
                nombre = %s,
                descripcion = %s,
                propietario_usuario_id = %s,
                activa = %s,
                actualizado_en = CURRENT_TIMESTAMP
            WHERE id = %s
            RETURNING id;
        """
        self._delete_organization_query = """
            DELETE FROM organizaciones
            WHERE id = %s
            RETURNING id, nombre;
        """

    def list_organizations(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_organizations_query)

    def get_organization_by_id(self, organization_id: int) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_organization_by_id_query, (organization_id,))

    def create_organization(
        self,
        *,
        name: str,
        description: str | None = None,
        owner_user_id: int,
        created_by_user_id: int,
        active: bool = True,
    ) -> dict[str, Any]:
        normalized_name = self._normalize_name(name)
        normalized_description = self._normalize_description(description)
        normalized_owner_user_id = self._normalize_positive_int(
            owner_user_id,
            error_code="invalid_owner_user_id",
        )
        normalized_created_by_user_id = self._normalize_positive_int(
            created_by_user_id,
            error_code="invalid_creator_user_id",
        )
        normalized_active = self._normalize_bool(active, default=True)

        duplicate_id = self._get_organization_id_by_owner_and_name(
            normalized_name,
            normalized_owner_user_id,
        )
        if duplicate_id is not None:
            raise ValueError("organization_already_exists")

        created = conn.execute_returning_one(
            self._insert_organization_query,
            (
                normalized_name,
                normalized_description,
                normalized_owner_user_id,
                normalized_created_by_user_id,
                normalized_active,
            ),
        )
        if not created or "id" not in created:
            raise ValueError("organization_creation_failed")

        organization = self.get_organization_by_id(int(created["id"]))
        if organization is None:
            raise ValueError("organization_creation_failed")
        return organization

    def update_organization(
        self,
        organization_id: int,
        *,
        name: str,
        description: str | None = None,
        owner_user_id: int,
        active: bool = True,
    ) -> dict[str, Any]:
        existing = self.get_organization_by_id(organization_id)
        if existing is None:
            raise ValueError("organization_not_found")

        normalized_name = self._normalize_name(name)
        normalized_description = self._normalize_description(description)
        normalized_owner_user_id = self._normalize_positive_int(
            owner_user_id,
            error_code="invalid_owner_user_id",
        )
        normalized_active = self._normalize_bool(active, default=bool(existing.get("activa")))

        duplicate_id = self._get_organization_id_by_owner_and_name(
            normalized_name,
            normalized_owner_user_id,
        )
        if duplicate_id is not None and duplicate_id != organization_id:
            raise ValueError("organization_already_exists")

        updated = conn.execute_returning_one(
            self._update_organization_query,
            (
                normalized_name,
                normalized_description,
                normalized_owner_user_id,
                normalized_active,
                organization_id,
            ),
        )
        if not updated or "id" not in updated:
            raise ValueError("organization_update_failed")

        organization = self.get_organization_by_id(organization_id)
        if organization is None:
            raise ValueError("organization_update_failed")
        return organization

    def delete_organization(self, organization_id: int) -> dict[str, Any]:
        existing = self.get_organization_by_id(organization_id)
        if existing is None:
            raise ValueError("organization_not_found")

        deleted = conn.fetch_one(self._delete_organization_query, (organization_id,))
        if deleted is None:
            raise ValueError("organization_delete_failed")
        return existing

    def _get_organization_id_by_owner_and_name(
        self,
        name: str,
        owner_user_id: int,
    ) -> Optional[int]:
        row = conn.fetch_one(
            self._select_organization_by_name_and_owner_query,
            (name, owner_user_id),
        )
        if row is None:
            return None
        try:
            return int(row["id"])
        except (KeyError, TypeError, ValueError):
            return None

    def _normalize_name(self, name: str) -> str:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise ValueError("invalid_organization_name")
        if len(normalized_name) > 150:
            raise ValueError("organization_name_too_long")
        return normalized_name

    def _normalize_description(self, description: str | None) -> str | None:
        normalized_description = str(description or "").strip()
        return normalized_description or None

    def _normalize_positive_int(self, value: Any, *, error_code: str) -> int:
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            raise ValueError(error_code) from None
        if normalized_value <= 0:
            raise ValueError(error_code)
        return normalized_value

    def _normalize_bool(self, value: Any, *, default: bool) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            normalized_value = value.strip().casefold()
            if normalized_value in {"1", "true", "si", "sí", "yes", "on", "activo", "activa"}:
                return True
            if normalized_value in {"0", "false", "no", "off", "inactivo", "inactiva"}:
                return False
        return default
