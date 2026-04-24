import os
import re
import sys
from typing import Any, Optional

if __package__ is None or __package__ == "":
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))
    from db.connection import db as conn
    from surveillance.security import hash_password, password_needs_rehash, verify_password
else:
    from db.connection import db as conn
    from surveillance.security import hash_password, password_needs_rehash, verify_password


class UserRepository:
    # Queries relacionados con usuarios y roles.
    def __init__(self) -> None:
        self._select_roles_query = """
            SELECT
                r.id,
                r.codigo,
                r.nombre,
                r.nivel_orden,
                r.es_sistema,
                r.creado_en,
                COUNT(u.id)::INT AS usuarios_asignados
            FROM roles r
            LEFT JOIN usuarios u ON u.rol_id = r.id
            GROUP BY r.id, r.codigo, r.nombre, r.nivel_orden, r.es_sistema, r.creado_en
            ORDER BY r.nivel_orden DESC, r.nombre ASC;
        """
        self._select_role_by_id_query = """
            SELECT
                r.id,
                r.codigo,
                r.nombre,
                r.nivel_orden,
                r.es_sistema,
                r.creado_en,
                COUNT(u.id)::INT AS usuarios_asignados
            FROM roles r
            LEFT JOIN usuarios u ON u.rol_id = r.id
            WHERE r.id = %s
            GROUP BY r.id, r.codigo, r.nombre, r.nivel_orden, r.es_sistema, r.creado_en;
        """
        self._insert_role_query = """
            INSERT INTO roles (
                codigo,
                nombre,
                nivel_orden,
                es_sistema
            )
            VALUES (%s, %s, %s, %s)
            RETURNING id;
        """
        self._update_role_query = """
            UPDATE roles
            SET
                codigo = %s,
                nombre = %s,
                nivel_orden = %s,
                es_sistema = %s
            WHERE id = %s
            RETURNING id;
        """
        self._delete_role_query = """
            DELETE FROM roles
            WHERE id = %s
            RETURNING id, codigo, nombre;
        """
        self._select_role_by_code_query = """
            SELECT id
            FROM roles
            WHERE LOWER(codigo) = LOWER(%s)
            LIMIT 1;
        """
        self._select_role_by_name_query = """
            SELECT id
            FROM roles
            WHERE LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._count_users_by_role_query = """
            SELECT COUNT(*)::INT AS total
            FROM usuarios
            WHERE rol_id = %s;
        """
        self._select_users_query = """
            SELECT
                u.id,
                u.usuario,
                u.email,
                u.password_hash,
                u.nombre,
                u.apellido,
                u.telefono,
                u.activo,
                u.cambiar_password,
                u.creado_por_usuario_id,
                u.usuario_padre_id,
                u.ultimo_login,
                u.creado_en,
                u.actualizado_en,
                u.rol_id,
                r.codigo AS rol_codigo,
                r.nombre AS rol_nombre,
                r.nivel_orden
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            ORDER BY u.id;
        """
        
        self._select_user_by_id_query = """
            SELECT
                u.id,
                u.usuario,
                u.email,
                u.password_hash,
                u.nombre,
                u.apellido,
                u.telefono,
                u.activo,
                u.cambiar_password,
                u.creado_por_usuario_id,
                u.usuario_padre_id,
                u.ultimo_login,
                u.creado_en,
                u.actualizado_en,
                u.rol_id,
                r.codigo AS rol_codigo,
                r.nombre AS rol_nombre,
                r.nivel_orden
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            WHERE u.id = %s;
        """
        
        self._select_user_by_username_query = """
            SELECT
                u.id,
                u.usuario,
                u.email,
                u.password_hash,
                u.nombre,
                u.apellido,
                u.telefono,
                u.activo,
                u.cambiar_password,
                u.creado_por_usuario_id,
                u.usuario_padre_id,
                u.ultimo_login,
                u.creado_en,
                u.actualizado_en,
                u.rol_id,
                r.codigo AS rol_codigo,
                r.nombre AS rol_nombre,
                r.nivel_orden
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            WHERE LOWER(u.usuario) = LOWER(%s)
            LIMIT 1;
        """
        self._select_user_by_email_query = """
            SELECT id, email
            FROM usuarios
            WHERE LOWER(email) = LOWER(%s)
            LIMIT 1;
        """

        self._insert_user_query = """
            INSERT INTO usuarios (
                usuario,
                email,
                password_hash,
                nombre,
                apellido,
                telefono,
                rol_id,
                activo,
                cambiar_password,
                creado_por_usuario_id,
                usuario_padre_id
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
        """

        self._update_user_query = """
            UPDATE usuarios
            SET
                usuario = %s,
                email = %s,
                nombre = %s,
                apellido = %s,
                telefono = %s,
                rol_id = %s,
                activo = %s,
                cambiar_password = %s,
                creado_por_usuario_id = %s,
                usuario_padre_id = %s
            WHERE id = %s
            RETURNING id;
        """

        self._update_user_password_query = """
            UPDATE usuarios
            SET
                password_hash = %s,
                cambiar_password = %s
            WHERE id = %s
            RETURNING id, usuario, email, cambiar_password, actualizado_en;
        """

        self._delete_user_query = """
            DELETE FROM usuarios
            WHERE id = %s
            RETURNING id, usuario, email;
        """
        
        self._autenticate_user_query = """
            SELECT
                u.id,
                u.usuario,
                u.email,
                u.password_hash,
                u.nombre,
                u.apellido,
                u.telefono,
                u.activo,
                u.cambiar_password,
                u.creado_por_usuario_id,
                u.usuario_padre_id,
                u.ultimo_login,
                u.creado_en,
                u.actualizado_en,
                u.rol_id,
                r.codigo AS rol_codigo,
                r.nombre AS rol_nombre,
                r.nivel_orden
            FROM usuarios u
            JOIN roles r ON u.rol_id = r.id
            WHERE (
                LOWER(u.usuario) = LOWER(%s)
                OR LOWER(u.email) = LOWER(%s)
            )
              AND u.activo = TRUE
            LIMIT 1;
        """
        
        self._resolve_role_id_query = """
            SELECT
                id
            FROM roles
            WHERE LOWER(codigo) = LOWER(%s)
               OR LOWER(nombre) = LOWER(%s)
            LIMIT 1;
        """
        self._list_roles_query = self._select_roles_query
        
    # CRUD para roles
    
    def get_roles_all(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_roles_query)

    def get_role_by_id(self, role_id: int) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_role_by_id_query, (role_id,))

    def create_role(
        self,
        *,
        code: str,
        name: str,
        level: int,
        is_system: bool = True,
    ) -> dict[str, Any]:
        normalized_code = self._normalize_role_code(code)
        normalized_name = self._normalize_role_name(name)
        normalized_level = self._normalize_role_level(level)
        normalized_is_system = self._normalize_bool(is_system, default=True)

        if self._get_role_id_by_code(normalized_code) is not None:
            raise ValueError("role_already_exists")
        if self._get_role_id_by_name(normalized_name) is not None:
            raise ValueError("role_already_exists")

        created = conn.execute_returning_one(
            self._insert_role_query,
            (normalized_code, normalized_name, normalized_level, normalized_is_system),
        )
        if not created or "id" not in created:
            raise ValueError("role_creation_failed")

        role = self.get_role_by_id(int(created["id"]))
        if role is None:
            raise ValueError("role_creation_failed")
        return role

    def update_role(
        self,
        role_id: int,
        *,
        code: str,
        name: str,
        level: int,
        is_system: bool,
    ) -> dict[str, Any]:
        existing = self.get_role_by_id(role_id)
        if existing is None:
            raise ValueError("role_not_found")

        normalized_code = self._normalize_role_code(code)
        normalized_name = self._normalize_role_name(name)
        normalized_level = self._normalize_role_level(level)
        normalized_is_system = self._normalize_bool(is_system, default=True)

        duplicate_code_id = self._get_role_id_by_code(normalized_code)
        if duplicate_code_id is not None and duplicate_code_id != role_id:
            raise ValueError("role_already_exists")
        duplicate_name_id = self._get_role_id_by_name(normalized_name)
        if duplicate_name_id is not None and duplicate_name_id != role_id:
            raise ValueError("role_already_exists")

        updated = conn.execute_returning_one(
            self._update_role_query,
            (normalized_code, normalized_name, normalized_level, normalized_is_system, role_id),
        )
        if not updated or "id" not in updated:
            raise ValueError("role_update_failed")

        role = self.get_role_by_id(role_id)
        if role is None:
            raise ValueError("role_update_failed")
        return role

    def delete_role(self, role_id: int) -> dict[str, Any]:
        existing = self.get_role_by_id(role_id)
        if existing is None:
            raise ValueError("role_not_found")
        if self._count_users_by_role(role_id) > 0:
            raise ValueError("role_in_use")

        deleted = conn.fetch_one(self._delete_role_query, (role_id,))
        if deleted is None:
            raise ValueError("role_delete_failed")
        return existing

    # CRUD para usuarios
    def get_user_all(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._select_users_query)

    def get_user_by_id(self, user_id: int) -> Optional[dict[str, Any]]:
        return conn.fetch_one(self._select_user_by_id_query, (user_id,))

    def get_user_by_username(self, username: str) -> Optional[dict[str, Any]]:
        normalized_username = self._normalize_username(username)
        return conn.fetch_one(self._select_user_by_username_query, (normalized_username,))

    def get_user_by_email(self, email: str) -> Optional[dict[str, Any]]:
        normalized_email = self._normalize_email(email)
        return conn.fetch_one(self._select_user_by_email_query, (normalized_email,))

    def create_user(
        self,
        *,
        username: str,
        email: str,
        password: str,
        name: str,
        role: str,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        active: bool = True,
        change_password: bool = False,
        created_by_user_id: Optional[int] = None,
        parent_user_id: Optional[int] = None,
    ) -> dict[str, Any]:
        normalized_username = self._normalize_username(username)
        normalized_email = self._normalize_email(email)
        normalized_password = self._normalize_password(password, required=True)
        normalized_name = self._normalize_required_text(name, max_length=80, error_code="invalid_name")
        normalized_last_name = self._normalize_optional_text(last_name, max_length=80, error_code="invalid_last_name")
        normalized_phone = self._normalize_optional_text(phone, max_length=25, error_code="invalid_phone")
        normalized_active = self._normalize_bool(active, default=True)
        normalized_change_password = self._normalize_bool(change_password, default=False)
        normalized_created_by_user_id = self._normalize_optional_positive_int(created_by_user_id)
        normalized_parent_user_id = self._normalize_optional_positive_int(parent_user_id)

        role_id = self._resolve_role_id(role)
        if role_id is None:
            raise ValueError("role_not_found")
        if self.get_user_by_username(normalized_username) is not None:
            raise ValueError("user_already_exists")
        if self.get_user_by_email(normalized_email) is not None:
            raise ValueError("email_already_exists")

        created = conn.execute_returning_one(
            self._insert_user_query,
            (
                normalized_username,
                normalized_email,
                hash_password(normalized_password),
                normalized_name,
                normalized_last_name,
                normalized_phone,
                role_id,
                normalized_active,
                normalized_change_password,
                normalized_created_by_user_id,
                normalized_parent_user_id,
            ),
        )
        if not created or "id" not in created:
            raise ValueError("user_creation_failed")

        user = self.get_user_by_id(int(created["id"]))
        if user is None:
            raise ValueError("user_creation_failed")
        return user

    def update_user(
        self,
        user_id: int,
        *,
        username: str,
        email: str,
        name: str,
        role: str,
        password: str | None = None,
        last_name: Optional[str] = None,
        phone: Optional[str] = None,
        active: bool = True,
        change_password: bool | None = None,
    ) -> dict[str, Any]:
        existing = self.get_user_by_id(user_id)
        if existing is None:
            raise ValueError("user_not_found")

        normalized_username = self._normalize_username(username)
        normalized_email = self._normalize_email(email)
        normalized_password = self._normalize_password(password, required=False)
        normalized_name = self._normalize_required_text(name, max_length=80, error_code="invalid_name")
        normalized_last_name = self._normalize_optional_text(last_name, max_length=80, error_code="invalid_last_name")
        normalized_phone = self._normalize_optional_text(phone, max_length=25, error_code="invalid_phone")
        normalized_active = self._normalize_bool(active, default=bool(existing.get("activo")))
        normalized_change_password = (
            bool(existing.get("cambiar_password"))
            if change_password is None
            else self._normalize_bool(change_password, default=bool(existing.get("cambiar_password")))
        )

        role_id = self._resolve_role_id(role)
        if role_id is None:
            raise ValueError("role_not_found")

        duplicate_user = self.get_user_by_username(normalized_username)
        if duplicate_user is not None and int(duplicate_user["id"]) != user_id:
            raise ValueError("user_already_exists")
        duplicate_email = self.get_user_by_email(normalized_email)
        if duplicate_email is not None and int(duplicate_email["id"]) != user_id:
            raise ValueError("email_already_exists")

        updated = conn.execute_returning_one(
            self._update_user_query,
            (
                normalized_username,
                normalized_email,
                normalized_name,
                normalized_last_name,
                normalized_phone,
                role_id,
                normalized_active,
                normalized_change_password,
                self._normalize_optional_positive_int(existing.get("creado_por_usuario_id")),
                self._normalize_optional_positive_int(existing.get("usuario_padre_id")),
                user_id,
            ),
        )
        if not updated or "id" not in updated:
            raise ValueError("user_update_failed")

        if normalized_password is not None:
            self.update_user_password(
                user_id,
                hash_password(normalized_password),
                cambiar_password=normalized_change_password,
            )

        user = self.get_user_by_id(user_id)
        if user is None:
            raise ValueError("user_update_failed")
        return user

    def update_user_password(
        self,
        user_id: int,
        new_password_hash: str,
        cambiar_password: bool = False,
    ) -> Optional[dict[str, Any]]:
        return conn.fetch_one(
            self._update_user_password_query,
            (new_password_hash, cambiar_password, user_id),
        )

    def delete_user(self, user_id: int) -> dict[str, Any]:
        existing = self.get_user_by_id(user_id)
        if existing is None:
            raise ValueError("user_not_found")

        deleted = conn.fetch_one(self._delete_user_query, (user_id,))
        if deleted is None:
            raise ValueError("user_delete_failed")
        return existing

    def authenticate_user(self, identity: str, password: str) -> Optional[dict[str, Any]]:
        normalized_identity = str(identity or "").strip()
        raw_password = str(password or "")
        if not normalized_identity or not raw_password:
            return None

        user = conn.fetch_one(self._autenticate_user_query, (normalized_identity, normalized_identity))
        if user is None:
            return None

        stored_password_hash = str(user.get("password_hash") or "")
        if not verify_password(raw_password, stored_password_hash):
            return None

        if password_needs_rehash(stored_password_hash):
            self.update_user_password(
                int(user["id"]),
                hash_password(raw_password),
                cambiar_password=bool(user.get("cambiar_password")),
            )
            refreshed = self.get_user_by_id(int(user["id"]))
            if refreshed is not None:
                return refreshed
        return user

    def _resolve_role_id(self, role_name: str) -> Optional[int]:
        normalized_role = str(role_name or "").strip()
        if not normalized_role:
            return None
        role_row = conn.fetch_one(self._resolve_role_id_query, (normalized_role, normalized_role))
        if role_row is None:
            return None
        try:
            return int(role_row["id"])
        except (KeyError, TypeError, ValueError):
            return None

    def list_roles(self) -> list[dict[str, Any]]:
        return conn.fetch_all(self._list_roles_query)

    def _get_role_id_by_code(self, code: str) -> Optional[int]:
        row = conn.fetch_one(self._select_role_by_code_query, (code,))
        if row is None:
            return None
        try:
            return int(row["id"])
        except (KeyError, TypeError, ValueError):
            return None

    def _get_role_id_by_name(self, name: str) -> Optional[int]:
        row = conn.fetch_one(self._select_role_by_name_query, (name,))
        if row is None:
            return None
        try:
            return int(row["id"])
        except (KeyError, TypeError, ValueError):
            return None

    def _count_users_by_role(self, role_id: int) -> int:
        row = conn.fetch_one(self._count_users_by_role_query, (role_id,))
        if row is None:
            return 0
        try:
            return int(row["total"])
        except (KeyError, TypeError, ValueError):
            return 0

    def _normalize_username(self, username: str) -> str:
        normalized_username = str(username or "").strip()
        if not normalized_username:
            raise ValueError("invalid_username")
        if len(normalized_username) > 20:
            raise ValueError("username_too_long")
        return normalized_username

    def _normalize_email(self, email: str) -> str:
        normalized_email = str(email or "").strip().lower()
        if not normalized_email or "@" not in normalized_email:
            raise ValueError("invalid_email")
        if len(normalized_email) > 120:
            raise ValueError("invalid_email")
        return normalized_email

    def _normalize_role_code(self, role_code: str) -> str:
        normalized_role = re.sub(r"[^a-z0-9_]+", "_", str(role_code or "").strip().lower())
        normalized_role = re.sub(r"_+", "_", normalized_role).strip("_")
        if not normalized_role or len(normalized_role) > 30:
            raise ValueError("invalid_role_code")
        return normalized_role

    def _normalize_role_name(self, role_name: str) -> str:
        normalized_name = str(role_name or "").strip()
        if not normalized_name or len(normalized_name) > 50:
            raise ValueError("invalid_role_name")
        return normalized_name

    def _normalize_role_level(self, level: int | str) -> int:
        try:
            normalized_level = int(level)
        except (TypeError, ValueError) as exc:
            raise ValueError("invalid_role_level") from exc
        if normalized_level < 0 or normalized_level > 32767:
            raise ValueError("invalid_role_level")
        return normalized_level

    def _normalize_required_text(self, value: str, *, max_length: int, error_code: str) -> str:
        normalized_value = str(value or "").strip()
        if not normalized_value or len(normalized_value) > max_length:
            raise ValueError(error_code)
        return normalized_value

    def _normalize_optional_text(self, value: str | None, *, max_length: int, error_code: str) -> str | None:
        normalized_value = str(value or "").strip()
        if not normalized_value:
            return None
        if len(normalized_value) > max_length:
            raise ValueError(error_code)
        return normalized_value

    def _normalize_optional_positive_int(self, value: object) -> int | None:
        if value in (None, "", 0, "0"):
            return None
        try:
            normalized_value = int(value)
        except (TypeError, ValueError):
            return None
        return normalized_value if normalized_value > 0 else None

    def _normalize_password(self, password: str | None, *, required: bool) -> str | None:
        raw_password = "" if password is None else str(password)
        normalized_password = raw_password.strip()
        if not normalized_password:
            if required:
                raise ValueError("invalid_password")
            return None
        return normalized_password

    def _normalize_bool(self, value: object, *, default: bool) -> bool:
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



if __name__ == "__main__":
    from db.connection import db

    db.open()

    repo = UserRepository()
    roles = repo.get_roles_all()
    usuarios = repo.get_user_all()
    #nuevo_usuario = repo.create_user(
    #    usuario="admin2",
    #    email="admin2@robiotec.com",
    #    password_hash="123456",
    #    nombre="Admin",
    #    apellido="Dos",
    #    telefono="0999999999",
    #    rol_id=2,
    #    activo=True,
    #    cambiar_password=False,p
    #    creado_por_usuario_id=1,
    #    usuario_padre_id=1,
    #)
    search_usuario = repo.get_user_by_username("admin1")
    print(search_usuario)
    
    #actualizado = repo.update_user(
    #    user_id=2,
    #    usuario="admin1",
    #    email="nuevo_admin@robiotec.com",
    #    nombre="Admin",
    #    apellido="Principal",
    #    telefono="0988888888",
    #    rol_id=2,
    #    activo=True,
    #    cambiar_password=False,
    #    creado_por_usuario_id=1,
    #    usuario_padre_id=1,
    #)
    #
    #repo.update_user_password(
    #    user_id=2,
    #    new_password_hash="nueva_clave_123",
    #    cambiar_password=False,
    #)
    #
    #eliminado = repo.delete_user(4)
    #print(eliminado)

    #print(actualizado)

    #print(roles)
    #print(usuarios)

    db.close()
