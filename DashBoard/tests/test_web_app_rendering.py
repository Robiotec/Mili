import json
import unittest
from unittest import mock

import web_app


class DummyRequest(dict):
    def __init__(self, *, payload=None, cookies=None, headers=None, json_error: Exception | None = None, match_info=None, path="/"):
        super().__init__()
        self._payload = payload
        self._json_error = json_error
        self.cookies = cookies or {}
        self.headers = headers or {}
        self.match_info = match_info or {}
        self.path = path

    async def json(self):
        if self._json_error is not None:
            raise self._json_error
        return self._payload

    async def post(self):
        return self._payload or {}


class WebAppRenderingTests(unittest.TestCase):
    def test_render_template_appends_static_asset_version(self):
        rendered = web_app._render_template("index.html").decode("utf-8")

        self.assertIn("/static/web_app.css?v=", rendered)
        self.assertIn("/static/web_app.js?v=", rendered)
        self.assertIn("startWithoutCamera: true", rendered)
        self.assertIn('emptyCameraMessage: "No ha seleccionado ninguna cámara."', rendered)
        self.assertNotIn('class="viewer-audio-dock"', rendered)
        self.assertNotIn("Control del canal activo", rendered)
        self.assertNotIn("__STATIC_ASSET_VERSION__", rendered)
        self.assertNotIn("__AUTH_USERNAME__", rendered)
        self.assertNotIn("__INCLUDE:", rendered)
        self.assertEqual(rendered.count('class="app-sidebar"'), 1)

    def test_render_dashboard_uses_shared_telemetry_map_markup(self):
        rendered = web_app._render_template("index.html").decode("utf-8")

        self.assertIn("Mapa y Telemetría", rendered)
        self.assertIn("Vista rápida", rendered)
        self.assertIn("El panel queda vacío hasta que selecciones una cámara en el mapa.", rendered)
        self.assertIn('id="telemetry-map"', rendered)
        self.assertIn('id="telemetry-device-filter"', rendered)
        self.assertIn('id="telemetry-focus-card"', rendered)
        self.assertIn('id="telemetry-map-overlay-box"', rendered)
        self.assertIn('id="telemetry-map-overlay-preview"', rendered)
        self.assertIn('id="dashboard-camera-preview"', rendered)
        self.assertIn('id="dashboard-camera-preview-stage"', rendered)
        self.assertNotIn('id="locations-map"', rendered)

    def test_render_mapa_uses_shared_telemetry_map_markup(self):
        rendered = web_app._render_template("mapa.html").decode("utf-8")

        self.assertIn('id="telemetry-map"', rendered)
        self.assertIn('id="telemetry-device-filter"', rendered)
        self.assertIn('id="telemetry-focus-card"', rendered)
        self.assertIn('id="telemetry-map-overlay-box"', rendered)
        self.assertIn("hls.js", rendered)
        self.assertNotIn("__INCLUDE:", rendered)

    def test_json_response_disables_cache(self):
        response = web_app._json_response({"ok": True})
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_html_response_disables_cache(self):
        response = web_app._html_response("camaras.html")
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_render_camaras_keeps_visual_center_without_admin_modal_by_default(self):
        rendered = web_app._render_template("camaras.html").decode("utf-8")

        self.assertNotIn("Control del canal activo", rendered)
        self.assertIn("Centro de Cámaras", rendered)
        self.assertNotIn("Registrar nueva cámara", rendered)

    def test_camera_item_payload_exposes_inference_state_for_switcher(self):
        device = mock.Mock()
        device.capabilities = {"audio": True}

        with mock.patch.object(web_app.APP_CONTEXT.device_catalog, "by_camera_name", return_value=device), mock.patch.object(
            web_app.APP_CONTEXT,
            "camera_records_by_name",
            {"cam_a": {"id": 14, "organizacion_nombre": "Operaciones", "hacer_inferencia": True}},
        ):
            payload = web_app._camera_item_payload("cam_a", "cam-a")

        self.assertEqual(payload["camera_id"], 14)
        self.assertTrue(payload["hacer_inferencia"])
        self.assertEqual(payload["organization_name"], "Operaciones")
        self.assertEqual(payload["capabilities"], {"audio": True})

    def test_render_perfil_includes_base_and_profile_stylesheets(self):
        rendered = web_app._render_template("perfil.html").decode("utf-8")

        self.assertIn("/static/web_app.css?v=", rendered)
        self.assertIn("/static/perfil.css?v=", rendered)
        self.assertNotIn("__STATIC_ASSET_VERSION__", rendered)

    def test_render_eventos_exposes_logs_center_layout(self):
        rendered = web_app._render_template("eventos.html").decode("utf-8")

        self.assertIn("Centro de Logs", rendered)
        self.assertIn("Logs Operativos", rendered)
        self.assertIn('id="logs-mode-switch"', rendered)
        self.assertIn('id="events-device-filter"', rendered)
        self.assertIn('id="events-summary"', rendered)
        self.assertIn('id="events-detail"', rendered)
        self.assertNotIn("__INCLUDE:", rendered)

    def test_render_usuarios_exposes_crud_controls(self):
        rendered = web_app._render_template("usuarios.html").decode("utf-8")

        self.assertIn("Gestión de Accesos", rendered)
        self.assertIn('id="role-admin-form"', rendered)
        self.assertIn('id="role-admin-rail-list"', rendered)
        self.assertIn('id="role-admin-submit"', rendered)
        self.assertIn('id="user-admin-form"', rendered)
        self.assertIn('id="user-admin-rail-list"', rendered)
        self.assertIn('id="user-admin-submit"', rendered)
        self.assertNotIn('id="organization-admin-form"', rendered)
        self.assertNotIn('id="organization-admin-rail-list"', rendered)
        self.assertNotIn('id="organization-admin-submit"', rendered)
        self.assertNotIn("CRUD operativo de organizaciones", rendered)
        self.assertNotIn("__DEVELOPER_MENU_LINK__", rendered)

    def test_render_registros_exposes_organization_crud_controls(self):
        rendered = web_app._render_template("registros.html").decode("utf-8")

        self.assertIn("Registros", rendered)
        self.assertIn('id="organization-admin-form"', rendered)
        self.assertIn('id="organization-admin-rail-list"', rendered)
        self.assertIn('id="organization-admin-submit"', rendered)
        self.assertNotIn('id="camera-admin-form"', rendered)
        self.assertNotIn('id="camera-admin-rail-list"', rendered)
        self.assertNotIn('id="camera-admin-submit"', rendered)
        self.assertNotIn('id="camera-admin-map-open"', rendered)
        self.assertNotIn('id="camera-admin-map-modal"', rendered)
        self.assertNotIn('id="camera-admin-map"', rendered)
        self.assertNotIn("leaflet.css", rendered)
        self.assertNotIn("leaflet.js", rendered)
        self.assertNotIn("__DEVELOPER_MENU_LINK__", rendered)


class LoginSessionTests(unittest.TestCase):
    def test_encode_and_decode_session_round_trip(self):
        session_value = web_app._encode_session(
            {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
        )

        payload = web_app._decode_session(session_value)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["user_id"], 7)
        self.assertEqual(payload["usuario"], "pedro_c")
        self.assertEqual(payload["rol"], "desarrollador")

    def test_encode_session_accepts_database_role_aliases(self):
        session_value = web_app._encode_session(
            {
                "id": 3,
                "usuario": "admin1",
                "rol_codigo": "admin",
                "rol_nombre": "Administrador",
            }
        )

        payload = web_app._decode_session(session_value)

        self.assertIsNotNone(payload)
        self.assertEqual(payload["rol"], "admin")


class LoginHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_index_renders_authenticated_sidebar_username(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "pedro_admin", "rol": "admin"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            response = await web_app.handle_index(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Usuario activo", body)
        self.assertIn("pedro_admin", body)

    async def test_handle_camaras_renders_camera_admin_modal_for_privileged_user(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "pedro_admin", "rol": "admin"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"), mock.patch.object(
            web_app,
            "_connect_crops_ssh_for_camaras",
            return_value=None,
        ) as ssh_connect:
            response = await web_app.handle_camaras(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        ssh_connect.assert_called_once_with()
        self.assertIn("Registrar nueva cámara", body)
        self.assertIn('id="camera-register-open"', body)
        self.assertIn('id="camera-register-modal"', body)
        self.assertIn('id="camera-admin-form"', body)
        self.assertIn('id="camera-admin-brand"', body)
        self.assertIn('id="camera-admin-protocol-wrap"', body)
        self.assertIn('id="camera-admin-rtsp-url"', body)
        self.assertIn('id="camera-admin-inference-enabled"', body)
        self.assertIn('id="camera-admin-rtsp-builder"', body)
        self.assertIn('id="camera-admin-map-modal"', body)
        self.assertIn("leaflet.css", body)
        self.assertIn("leaflet.js", body)

    async def test_handle_login_submit_sets_auth_cookie_on_success(self):
        request = DummyRequest(payload={"identity": "admin", "password": "admin123"})
        repo = mock.Mock()
        repo.authenticate_user.return_value = {"id": 1, "usuario": "admin", "rol": "admin"}

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_login_submit(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["redirect"], "/")
        self.assertIn("access_token", payload)
        self.assertEqual(payload["token_type"], "Bearer")
        self.assertIn(web_app.SESSION_COOKIE_NAME, response.cookies)

    async def test_handle_login_submit_normalizes_database_role_fields(self):
        request = DummyRequest(payload={"identity": "admin1", "password": "admin123"})
        repo = mock.Mock()
        repo.authenticate_user.return_value = {
            "id": 3,
            "usuario": "admin1",
            "rol_codigo": "admin",
            "rol_nombre": "Administrador",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_login_submit(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["user"]["rol"], "admin")
        self.assertIn("access_token", payload)
        self.assertIn(web_app.SESSION_COOKIE_NAME, response.cookies)

    async def test_handle_login_submit_rejects_invalid_credentials(self):
        request = DummyRequest(payload={"identity": "admin", "password": "mala"})
        repo = mock.Mock()
        repo.authenticate_user.return_value = None

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_login_submit(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 401)
        self.assertEqual(payload["error"], "invalid_credentials")
        self.assertNotIn(web_app.SESSION_COOKIE_NAME, response.cookies)

    async def test_handle_auth_session_accepts_bearer_token(self):
        token, _ = web_app.issue_access_token(
            user_id=7,
            username="operador1",
            role="operador",
            role_level=30,
        )
        request = DummyRequest(
            headers={"Authorization": f"Bearer {token}"},
            path="/api/auth/session",
        )

        response = await web_app.handle_auth_session(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["authenticated_via"], "bearer")
        self.assertEqual(payload["user"]["usuario"], "operador1")

    async def test_handle_auth_session_accepts_cookie_session(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 1, "usuario": "admin", "rol": "admin", "nivel_orden": 80}
                )
            },
            path="/api/auth/session",
        )

        response = await web_app.handle_auth_session(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["authenticated_via"], "cookie")
        self.assertEqual(payload["user"]["usuario"], "admin")

    async def test_handle_login_redirects_authenticated_users(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 1, "usuario": "admin", "rol": "admin"}
                )
            }
        )

        with self.assertRaises(web_app.web.HTTPFound) as ctx:
            await web_app.handle_login(request)

        self.assertEqual(ctx.exception.location, "/")

    async def test_handle_logout_clears_auth_cookie(self):
        response = await web_app.handle_logout(DummyRequest())

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["redirect"], "/login")
        self.assertIn(web_app.SESSION_COOKIE_NAME, response.cookies)
        self.assertEqual(response.cookies[web_app.SESSION_COOKIE_NAME]["max-age"], "0")

    async def test_handle_perfil_renders_session_backed_profile_details(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"), mock.patch.object(
            web_app, "_snapshot_stream_states", return_value=[("cam1", "live", "Drone 1", 2)]
        ), mock.patch.object(
            web_app.APP_CONTEXT.device_catalog,
            "as_dicts",
            return_value=[{"device_id": "dr-1"}, {"device_id": "dr-2"}],
        ), mock.patch.object(
            web_app, "_ensure_database_ready"
        ), mock.patch.object(
            web_app.db, "health_check", return_value=True
        ):
            response = await web_app.handle_perfil(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Pedro C", body)
        self.assertIn("pedro_c", body)
        self.assertIn("Desarrollador", body)
        self.assertIn("Conectada", body)
        self.assertIn("Dashboard", body)
        self.assertNotIn("__PROFILE_", body)

    async def test_handle_index_shows_user_admin_menu_link_only_for_privileged_roles(self):
        developer_request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            }
        )
        admin_request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )
        engineer_request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )
        operator_request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 8, "usuario": "operador_1", "rol": "operador"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            developer_response = await web_app.handle_index(developer_request)
            admin_response = await web_app.handle_index(admin_request)
            engineer_response = await web_app.handle_index(engineer_request)
            operator_response = await web_app.handle_index(operator_request)

        self.assertIn('href="/usuarios"', developer_response.body.decode("utf-8"))
        self.assertIn('href="/registros"', developer_response.body.decode("utf-8"))
        self.assertIn('href="/usuarios"', admin_response.body.decode("utf-8"))
        self.assertIn('href="/registros"', admin_response.body.decode("utf-8"))
        self.assertIn('href="/usuarios"', engineer_response.body.decode("utf-8"))
        self.assertIn('href="/registros"', engineer_response.body.decode("utf-8"))
        self.assertNotIn('href="/usuarios"', operator_response.body.decode("utf-8"))
        self.assertNotIn('href="/registros"', operator_response.body.decode("utf-8"))

    async def test_handle_index_accepts_developer_role_code_alias(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "developer"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            response = await web_app.handle_index(request)

        self.assertIn('href="/usuarios"', response.body.decode("utf-8"))
        self.assertIn('href="/registros"', response.body.decode("utf-8"))


class UserManagementHandlerTests(unittest.IsolatedAsyncioTestCase):
    async def test_handle_usuarios_redirects_non_privileged_user(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 9, "usuario": "supervisor", "rol": "operador"}
                )
            }
        )

        with self.assertRaises(web_app.web.HTTPFound) as ctx:
            await web_app.handle_usuarios(request)

        self.assertEqual(ctx.exception.location, "/")

    async def test_handle_registros_redirects_non_privileged_user(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 9, "usuario": "supervisor", "rol": "operador"}
                )
            }
        )

        with self.assertRaises(web_app.web.HTTPFound) as ctx:
            await web_app.handle_registros(request)

        self.assertEqual(ctx.exception.location, "/")

    async def test_handle_usuarios_renders_for_admin_without_role_crud_section(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            response = await web_app.handle_usuarios(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Modo Administrador", body)
        self.assertIn("Tu rol administrador puede gestionar usuarios.", body)
        self.assertNotIn("CRUD operativo de roles", body)
        self.assertNotIn("CRUD operativo de organizaciones", body)
        self.assertNotIn('id="role-admin-form"', body)
        self.assertNotIn('id="role-admin-rail-list"', body)
        self.assertNotIn('id="role-admin-total"', body)
        self.assertNotIn('id="organization-admin-form"', body)

    async def test_handle_usuarios_renders_for_engineer_without_role_crud_section(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            response = await web_app.handle_usuarios(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Modo Ingeniero", body)
        self.assertIn("Tu rol ingeniero puede gestionar usuarios de ingeniero para abajo.", body)
        self.assertIn("Ingenieros", body)
        self.assertNotIn("CRUD operativo de roles", body)
        self.assertNotIn("CRUD operativo de organizaciones", body)
        self.assertNotIn('id="role-admin-form"', body)
        self.assertNotIn('id="role-admin-rail-list"', body)
        self.assertNotIn('id="role-admin-total"', body)
        self.assertNotIn('id="organization-admin-form"', body)

    async def test_handle_registros_renders_for_admin_with_organization_crud_only(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )

        with mock.patch.object(web_app.APP_CONTEXT, "ensure_initialized"):
            response = await web_app.handle_registros(request)

        body = response.body.decode("utf-8")
        self.assertEqual(response.status, 200)
        self.assertIn("Registros", body)
        self.assertIn("Modo Administrador", body)
        self.assertNotIn("CRUD operativo de organizaciones", body)
        self.assertNotIn("CRUD operativo de cámaras", body)
        self.assertIn("Tu rol administrador puede gestionar organizaciones de administradores, ingenieros y clientes.", body)
        self.assertNotIn("CRUD operativo de usuarios", body)
        self.assertNotIn('id="user-admin-form"', body)
        self.assertIn('id="organization-admin-form"', body)
        self.assertNotIn('id="camera-admin-form"', body)
        self.assertNotIn('id="camera-admin-map-modal"', body)

    async def test_handle_devices_filters_camera_catalog_by_role_level(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 2, "usuario": "admin", "rol": "admin", "nivel_orden": 80}
                )
            }
        )

        with mock.patch.object(
            web_app.APP_CONTEXT.device_catalog,
            "as_dicts",
            return_value=[
                {"camera_name": "cam_dev", "owner_level": 100},
                {"camera_name": "cam_admin", "owner_level": 80},
                {"camera_name": "cam_ing", "owner_level": 50},
            ],
        ):
            response = await web_app.handle_devices(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["camera_name"] for item in payload], ["cam_admin", "cam_ing"])

    async def test_handle_cameras_registry_filters_results_for_engineer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer", "nivel_orden": 50}
                )
            }
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 1, "codigo": "developer", "nombre": "Developer", "nivel_orden": 100},
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        camera_repo = mock.Mock()
        camera_repo.list_cameras.return_value = [
            {
                "id": 1,
                "nombre": "cam_dev",
                "propietario_usuario": "pedro_dev",
                "propietario_rol_codigo": "developer",
                "propietario_rol_nombre": "Developer",
                "propietario_nivel_orden": 100,
            },
            {
                "id": 2,
                "nombre": "cam_ing",
                "propietario_usuario": "ing_1",
                "propietario_rol_codigo": "engineer",
                "propietario_rol_nombre": "Ingeniero",
                "propietario_nivel_orden": 50,
            },
            {
                "id": 3,
                "nombre": "cam_cliente",
                "propietario_usuario": "cliente_1",
                "propietario_rol_codigo": "client",
                "propietario_rol_nombre": "Cliente",
                "propietario_nivel_orden": 10,
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "CameraRepository", return_value=camera_repo
        ):
            response = await web_app.handle_cameras_registry(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["nombre"] for item in payload], ["cam_ing", "cam_cliente"])

    async def test_handle_camera_inference_update_updates_manageable_camera(self):
        request = DummyRequest(
            payload={"hacer_inferencia": True},
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer", "nivel_orden": 50}
                )
            },
            match_info={"camera_id": "7"},
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 1, "codigo": "developer", "nombre": "Developer", "nivel_orden": 100},
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        existing_camera = {
            "id": 7,
            "nombre": "cam_ing",
            "propietario_usuario": "ing_1",
            "propietario_nivel_orden": 50,
            "hacer_inferencia": False,
        }
        updated_camera = {
            **existing_camera,
            "hacer_inferencia": True,
        }
        camera_repo = mock.Mock()
        camera_repo.get_camera_by_id.return_value = existing_camera
        camera_repo.set_camera_inference_enabled.return_value = updated_camera

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "CameraRepository", return_value=camera_repo
        ), mock.patch.object(
            web_app.APP_CONTEXT, "reload_runtime_state"
        ), mock.patch.object(
            web_app.APP_CONTEXT.event_store, "record"
        ):
            response = await web_app.handle_camera_inference_update(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["camera"]["hacer_inferencia"])
        camera_repo.set_camera_inference_enabled.assert_called_once_with(7, inference_enabled=True)

    async def test_handle_camera_inference_update_blocks_camera_out_of_scope(self):
        request = DummyRequest(
            payload={"hacer_inferencia": False},
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer", "nivel_orden": 50}
                )
            },
            match_info={"camera_id": "9"},
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 1, "codigo": "developer", "nombre": "Developer", "nivel_orden": 100},
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        camera_repo = mock.Mock()
        camera_repo.get_camera_by_id.return_value = {
            "id": 9,
            "nombre": "cam_dev",
            "propietario_usuario": "pedro_dev",
            "propietario_nivel_orden": 100,
            "hacer_inferencia": True,
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "CameraRepository", return_value=camera_repo
        ):
            response = await web_app.handle_camera_inference_update(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "camera_scope_forbidden")
        camera_repo.set_camera_inference_enabled.assert_not_called()

    async def test_handle_users_forbids_non_privileged_api_access(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 9, "usuario": "supervisor", "rol": "operador"}
                )
            }
        )

        response = await web_app.handle_users(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "forbidden")

    async def test_handle_organizations_forbids_non_privileged_api_access(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 9, "usuario": "supervisor", "rol": "operador"}
                )
            }
        )

        response = await web_app.handle_organizations(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "forbidden")

    async def test_handle_user_roles_forbids_admin(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )
        response = await web_app.handle_user_roles(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "forbidden")

    async def test_handle_user_roles_forbids_engineer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )
        response = await web_app.handle_user_roles(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "forbidden")

    async def test_handle_user_role_options_returns_serialized_roles_for_admin(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 2,
                "codigo": "admin_principal",
                "nombre": "Administrador Principal",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            }
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_role_options(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload[0]["codigo"], "admin_principal")
        self.assertNotIn("developer", [item["codigo"] for item in payload])

    async def test_handle_user_roles_returns_serialized_roles_for_developer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            }
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            }
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_roles(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload[0]["codigo"], "developer")
        self.assertEqual(payload[0]["usuarios_asignados"], 1)

    async def test_handle_user_role_options_returns_serialized_roles_for_engineer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 2,
                "codigo": "admin",
                "nombre": "Administrador",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 2,
            },
            {
                "id": 4,
                "codigo": "client",
                "nombre": "Cliente",
                "nivel_orden": 10,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_role_options(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["codigo"] for item in payload], ["engineer", "client"])

    async def test_handle_role_create_forbids_admin(self):
        request = DummyRequest(
            payload={
                "codigo": "operador_campo",
                "nombre": "Operador de Campo",
                "nivel_orden": 25,
                "es_sistema": False,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            },
        )

        response = await web_app.handle_role_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "forbidden")

    async def test_handle_users_returns_serialized_users_for_developer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            }
        )
        repo = mock.Mock()
        repo.get_user_all.return_value = [
            {
                "id": 15,
                "usuario": "nuevo",
                "email": "nuevo@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Usuario",
                "telefono": "0999999999",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "engineer",
                "rol_nombre": "Ingeniero",
            }
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_users(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload[0]["usuario"], "nuevo")
        self.assertEqual(payload[0]["rol"], "engineer")
        self.assertEqual(payload[0]["rol_label"], "Ingeniero")
        self.assertNotIn("password_hash", payload[0])

    async def test_handle_users_returns_serialized_users_for_admin(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 2,
                "codigo": "admin_principal",
                "nombre": "Administrador Principal",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]
        repo.get_user_all.return_value = [
            {
                "id": 1,
                "usuario": "pedro_dev",
                "email": "dev@robiotec.com",
                "nombre": "Pedro",
                "apellido": "Dev",
                "telefono": "0990000001",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "developer",
                "rol_nombre": "Developer",
                "nivel_orden": 100,
            },
            {
                "id": 15,
                "usuario": "nuevo",
                "email": "nuevo@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Usuario",
                "telefono": "0999999999",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "engineer",
                "rol_nombre": "Ingeniero",
                "nivel_orden": 50,
            }
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_users(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["usuario"] for item in payload], ["nuevo"])
        self.assertEqual(payload[0]["rol"], "engineer")

    async def test_handle_users_returns_serialized_users_for_engineer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 2,
                "codigo": "admin",
                "nombre": "Administrador",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 2,
            },
            {
                "id": 4,
                "codigo": "client",
                "nombre": "Cliente",
                "nivel_orden": 10,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]
        repo.get_user_all.return_value = [
            {
                "id": 1,
                "usuario": "pedro_dev",
                "email": "dev@robiotec.com",
                "nombre": "Pedro",
                "apellido": "Dev",
                "telefono": "0990000001",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "developer",
                "rol_nombre": "Developer",
                "nivel_orden": 100,
            },
            {
                "id": 2,
                "usuario": "admin1",
                "email": "admin@robiotec.com",
                "nombre": "Admin",
                "apellido": "Principal",
                "telefono": "0990000002",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "admin",
                "rol_nombre": "Administrador",
                "nivel_orden": 80,
            },
            {
                "id": 3,
                "usuario": "ing_2",
                "email": "ing2@robiotec.com",
                "nombre": "Ing",
                "apellido": "Dos",
                "telefono": "0990000003",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "engineer",
                "rol_nombre": "Ingeniero",
                "nivel_orden": 50,
            },
            {
                "id": 4,
                "usuario": "cliente_1",
                "email": "cliente@robiotec.com",
                "nombre": "Cliente",
                "apellido": "Uno",
                "telefono": "0990000004",
                "activo": True,
                "cambiar_password": False,
                "rol_codigo": "client",
                "rol_nombre": "Cliente",
                "nivel_orden": 10,
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_users(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["usuario"] for item in payload], ["ing_2", "cliente_1"])
        self.assertEqual([item["rol"] for item in payload], ["engineer", "client"])

    async def test_handle_organizations_returns_filtered_organizations_for_admin(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            }
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 1, "codigo": "developer", "nombre": "Developer", "nivel_orden": 100},
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        organization_repo = mock.Mock()
        organization_repo.list_organizations.return_value = [
            {
                "id": 1,
                "nombre": "Org Dev",
                "descripcion": "Solo developer",
                "activa": True,
                "propietario_usuario_id": 1,
                "propietario_usuario": "pedro_dev",
                "propietario_email": "dev@robiotec.com",
                "propietario_nombre": "Pedro",
                "propietario_apellido": "Dev",
                "propietario_rol_codigo": "developer",
                "propietario_rol_nombre": "Developer",
                "propietario_nivel_orden": 100,
                "creado_por_usuario_id": 1,
                "creado_por_usuario": "pedro_dev",
            },
            {
                "id": 2,
                "nombre": "Org Admin",
                "descripcion": "Admin",
                "activa": True,
                "propietario_usuario_id": 2,
                "propietario_usuario": "admin1",
                "propietario_email": "admin@robiotec.com",
                "propietario_nombre": "Admin",
                "propietario_apellido": "Principal",
                "propietario_rol_codigo": "admin",
                "propietario_rol_nombre": "Administrador",
                "propietario_nivel_orden": 80,
                "creado_por_usuario_id": 1,
                "creado_por_usuario": "pedro_dev",
            },
            {
                "id": 3,
                "nombre": "Org Ing",
                "descripcion": "Ingenieria",
                "activa": True,
                "propietario_usuario_id": 3,
                "propietario_usuario": "ing_1",
                "propietario_email": "ing@robiotec.com",
                "propietario_nombre": "Ing",
                "propietario_apellido": "Uno",
                "propietario_rol_codigo": "engineer",
                "propietario_rol_nombre": "Ingeniero",
                "propietario_nivel_orden": 50,
                "creado_por_usuario_id": 2,
                "creado_por_usuario": "admin1",
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "OrganizationRepository", return_value=organization_repo
        ):
            response = await web_app.handle_organizations(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["nombre"] for item in payload], ["Org Admin", "Org Ing"])
        self.assertNotIn("Org Dev", [item["nombre"] for item in payload])

    async def test_handle_organizations_returns_filtered_organizations_for_engineer(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            }
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 1, "codigo": "developer", "nombre": "Developer", "nivel_orden": 100},
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        organization_repo = mock.Mock()
        organization_repo.list_organizations.return_value = [
            {
                "id": 1,
                "nombre": "Org Admin",
                "descripcion": "Admin",
                "activa": True,
                "propietario_usuario_id": 2,
                "propietario_usuario": "admin1",
                "propietario_email": "admin@robiotec.com",
                "propietario_nombre": "Admin",
                "propietario_apellido": "Principal",
                "propietario_rol_codigo": "admin",
                "propietario_rol_nombre": "Administrador",
                "propietario_nivel_orden": 80,
                "creado_por_usuario_id": 1,
                "creado_por_usuario": "pedro_dev",
            },
            {
                "id": 2,
                "nombre": "Org Ing",
                "descripcion": "Ingenieria",
                "activa": True,
                "propietario_usuario_id": 3,
                "propietario_usuario": "ing_1",
                "propietario_email": "ing@robiotec.com",
                "propietario_nombre": "Ing",
                "propietario_apellido": "Uno",
                "propietario_rol_codigo": "engineer",
                "propietario_rol_nombre": "Ingeniero",
                "propietario_nivel_orden": 50,
                "creado_por_usuario_id": 2,
                "creado_por_usuario": "admin1",
            },
            {
                "id": 3,
                "nombre": "Org Cliente",
                "descripcion": "Cliente",
                "activa": True,
                "propietario_usuario_id": 4,
                "propietario_usuario": "cliente_1",
                "propietario_email": "cliente@robiotec.com",
                "propietario_nombre": "Cliente",
                "propietario_apellido": "Uno",
                "propietario_rol_codigo": "client",
                "propietario_rol_nombre": "Cliente",
                "propietario_nivel_orden": 10,
                "creado_por_usuario_id": 3,
                "creado_por_usuario": "ing_1",
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "OrganizationRepository", return_value=organization_repo
        ):
            response = await web_app.handle_organizations(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual([item["nombre"] for item in payload], ["Org Ing", "Org Cliente"])
        self.assertNotIn("Org Admin", [item["nombre"] for item in payload])

    async def test_handle_role_create_creates_role_for_developer(self):
        request = DummyRequest(
            payload={
                "codigo": "operador_campo",
                "nombre": "Operador de Campo",
                "nivel_orden": 25,
                "es_sistema": False,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            },
        )
        repo = mock.Mock()
        repo.create_role.return_value = {
            "id": 6,
            "codigo": "operador_campo",
            "nombre": "Operador de Campo",
            "nivel_orden": 25,
            "es_sistema": False,
            "usuarios_asignados": 0,
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_role_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["role"]["codigo"], "operador_campo")
        repo.create_role.assert_called_once_with(
            code="operador_campo",
            name="Operador de Campo",
            level=25,
            is_system=False,
        )

    async def test_handle_user_create_creates_user_for_developer(self):
        request = DummyRequest(
            payload={
                "usuario": "nuevo",
                "email": "nuevo@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Usuario",
                "telefono": "0999999999",
                "password": "clave123",
                "rol": "engineer",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            },
        )
        repo = mock.Mock()
        repo.create_user.return_value = {
            "id": 15,
            "usuario": "nuevo",
            "email": "nuevo@robiotec.com",
            "nombre": "Nuevo",
            "apellido": "Usuario",
            "telefono": "0999999999",
            "activo": True,
            "cambiar_password": False,
            "rol_codigo": "engineer",
            "rol_nombre": "Ingeniero",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["user"]["usuario"], "nuevo")
        self.assertEqual(payload["user"]["rol"], "engineer")
        repo.create_user.assert_called_once_with(
            username="nuevo",
            email="nuevo@robiotec.com",
            password="clave123",
            name="Nuevo",
            role="engineer",
            last_name="Usuario",
            phone="0999999999",
            active=True,
            created_by_user_id=7,
            parent_user_id=7,
        )

    async def test_handle_user_create_creates_user_for_admin(self):
        request = DummyRequest(
            payload={
                "usuario": "nuevo_admin",
                "email": "nuevo_admin@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Admin",
                "telefono": "0999999999",
                "password": "clave123",
                "rol": "engineer",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            },
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 2,
                "codigo": "admin_principal",
                "nombre": "Administrador Principal",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]
        repo.create_user.return_value = {
            "id": 18,
            "usuario": "nuevo_admin",
            "email": "nuevo_admin@robiotec.com",
            "nombre": "Nuevo",
            "apellido": "Admin",
            "telefono": "0999999999",
            "activo": True,
            "cambiar_password": False,
            "rol_codigo": "engineer",
            "rol_nombre": "Ingeniero",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["user"]["usuario"], "nuevo_admin")
        repo.create_user.assert_called_once_with(
            username="nuevo_admin",
            email="nuevo_admin@robiotec.com",
            password="clave123",
            name="Nuevo",
            role="engineer",
            last_name="Admin",
            phone="0999999999",
            active=True,
            created_by_user_id=4,
            parent_user_id=4,
        )

    async def test_handle_user_create_creates_user_for_engineer(self):
        request = DummyRequest(
            payload={
                "usuario": "nuevo_ing",
                "email": "nuevo_ing@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Ingeniero",
                "telefono": "0999999999",
                "password": "clave123",
                "rol": "engineer",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            },
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 2,
            },
            {
                "id": 4,
                "codigo": "client",
                "nombre": "Cliente",
                "nivel_orden": 10,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]
        repo.create_user.return_value = {
            "id": 22,
            "usuario": "nuevo_ing",
            "email": "nuevo_ing@robiotec.com",
            "nombre": "Nuevo",
            "apellido": "Ingeniero",
            "telefono": "0999999999",
            "activo": True,
            "cambiar_password": False,
            "rol_codigo": "engineer",
            "rol_nombre": "Ingeniero",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["user"]["usuario"], "nuevo_ing")
        self.assertEqual(payload["user"]["rol"], "engineer")
        repo.create_user.assert_called_once_with(
            username="nuevo_ing",
            email="nuevo_ing@robiotec.com",
            password="clave123",
            name="Nuevo",
            role="engineer",
            last_name="Ingeniero",
            phone="0999999999",
            active=True,
            created_by_user_id=5,
            parent_user_id=5,
        )

    async def test_handle_organization_create_creates_organization_for_engineer(self):
        request = DummyRequest(
            payload={
                "nombre": "Org Ingenieria Sur",
                "descripcion": "Operacion regional",
                "propietario_usuario_id": 5,
                "activa": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            },
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        user_repo.get_user_by_id.return_value = {
            "id": 5,
            "usuario": "ing_1",
            "email": "ing@robiotec.com",
            "nombre": "Ing",
            "apellido": "Uno",
            "rol_codigo": "engineer",
            "rol_nombre": "Ingeniero",
            "nivel_orden": 50,
        }
        organization_repo = mock.Mock()
        organization_repo.create_organization.return_value = {
            "id": 8,
            "nombre": "Org Ingenieria Sur",
            "descripcion": "Operacion regional",
            "activa": True,
            "propietario_usuario_id": 5,
            "propietario_usuario": "ing_1",
            "propietario_email": "ing@robiotec.com",
            "propietario_nombre": "Ing",
            "propietario_apellido": "Uno",
            "propietario_rol_codigo": "engineer",
            "propietario_rol_nombre": "Ingeniero",
            "propietario_nivel_orden": 50,
            "creado_por_usuario_id": 5,
            "creado_por_usuario": "ing_1",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "OrganizationRepository", return_value=organization_repo
        ):
            response = await web_app.handle_organization_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 201)
        self.assertEqual(payload["organization"]["nombre"], "Org Ingenieria Sur")
        organization_repo.create_organization.assert_called_once_with(
            name="Org Ingenieria Sur",
            description="Operacion regional",
            owner_user_id=5,
            created_by_user_id=5,
            active=True,
        )

    async def test_handle_user_create_forbids_admin_assigning_developer_role(self):
        request = DummyRequest(
            payload={
                "usuario": "nuevo_dev",
                "email": "nuevo_dev@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Developer",
                "telefono": "0999999999",
                "password": "clave123",
                "rol": "developer",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            },
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 1,
                "codigo": "developer",
                "nombre": "Developer",
                "nivel_orden": 100,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 2,
                "codigo": "admin_principal",
                "nombre": "Administrador Principal",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "role_scope_forbidden")
        repo.create_user.assert_not_called()

    async def test_handle_user_create_forbids_engineer_assigning_admin_role(self):
        request = DummyRequest(
            payload={
                "usuario": "nuevo_admin_desde_ing",
                "email": "nuevo_admin_desde_ing@robiotec.com",
                "nombre": "Nuevo",
                "apellido": "Admin",
                "telefono": "0999999999",
                "password": "clave123",
                "rol": "admin",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            },
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 2,
                "codigo": "admin",
                "nombre": "Administrador",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 2,
            },
            {
                "id": 4,
                "codigo": "client",
                "nombre": "Cliente",
                "nivel_orden": 10,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "role_scope_forbidden")
        repo.create_user.assert_not_called()

    async def test_handle_organization_create_forbids_engineer_assigning_admin_owner(self):
        request = DummyRequest(
            payload={
                "nombre": "Org Admin Bloqueada",
                "descripcion": "No deberia permitir",
                "propietario_usuario_id": 4,
                "activa": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 5, "usuario": "ing_1", "rol": "engineer"}
                )
            },
        )
        user_repo = mock.Mock()
        user_repo.list_roles.return_value = [
            {"id": 2, "codigo": "admin", "nombre": "Administrador", "nivel_orden": 80},
            {"id": 3, "codigo": "engineer", "nombre": "Ingeniero", "nivel_orden": 50},
            {"id": 4, "codigo": "client", "nombre": "Cliente", "nivel_orden": 10},
        ]
        user_repo.get_user_by_id.return_value = {
            "id": 4,
            "usuario": "admin1",
            "email": "admin@robiotec.com",
            "nombre": "Admin",
            "apellido": "Principal",
            "rol_codigo": "admin",
            "rol_nombre": "Administrador",
            "nivel_orden": 80,
        }
        organization_repo = mock.Mock()

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app, "UserRepository", return_value=user_repo
        ), mock.patch.object(
            web_app, "OrganizationRepository", return_value=organization_repo
        ):
            response = await web_app.handle_organization_create(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 403)
        self.assertEqual(payload["error"], "organization_scope_forbidden")
        organization_repo.create_organization.assert_not_called()

    async def test_handle_user_update_allows_admin_updating_own_profile_without_role_change(self):
        request = DummyRequest(
            payload={
                "usuario": "admin1",
                "email": "admin@robiotec.com",
                "nombre": "Admin",
                "apellido": "Principal",
                "telefono": "0999999999",
                "password": "",
                "rol": "admin",
                "activo": True,
            },
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 4, "usuario": "admin1", "rol": "admin"}
                )
            },
            match_info={"user_id": "4"},
        )
        repo = mock.Mock()
        repo.list_roles.return_value = [
            {
                "id": 2,
                "codigo": "admin",
                "nombre": "Administrador",
                "nivel_orden": 80,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
            {
                "id": 3,
                "codigo": "engineer",
                "nombre": "Ingeniero",
                "nivel_orden": 50,
                "es_sistema": True,
                "usuarios_asignados": 1,
            },
        ]
        repo.get_user_by_id.return_value = {
            "id": 4,
            "usuario": "admin1",
            "email": "admin@robiotec.com",
            "nombre": "Admin",
            "apellido": "Principal",
            "telefono": "0999999999",
            "activo": True,
            "cambiar_password": False,
            "rol_codigo": "admin",
            "rol_nombre": "Administrador",
            "nivel_orden": 80,
        }
        repo.update_user.return_value = {
            "id": 4,
            "usuario": "admin1",
            "email": "admin@robiotec.com",
            "nombre": "Admin",
            "apellido": "Principal",
            "telefono": "0999999999",
            "activo": True,
            "cambiar_password": False,
            "rol_codigo": "admin",
            "rol_nombre": "Administrador",
        }

        with mock.patch.object(web_app, "_ensure_database_ready"), mock.patch.object(
            web_app,
            "UserRepository",
            return_value=repo,
        ):
            response = await web_app.handle_user_update(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 200)
        self.assertEqual(payload["user"]["usuario"], "admin1")
        self.assertEqual(payload["user"]["rol"], "admin")
        repo.update_user.assert_called_once_with(
            4,
            username="admin1",
            email="admin@robiotec.com",
            name="Admin",
            password="",
            role="admin",
            last_name="Principal",
            phone="0999999999",
            active=True,
        )

    async def test_handle_user_delete_blocks_current_session_user(self):
        request = DummyRequest(
            cookies={
                web_app.SESSION_COOKIE_NAME: web_app._encode_session(
                    {"id": 7, "usuario": "pedro_c", "rol": "desarrollador"}
                )
            },
            match_info={"user_id": "7"},
        )

        response = await web_app.handle_user_delete(request)

        payload = json.loads(response.text)
        self.assertEqual(response.status, 400)
        self.assertEqual(payload["error"], "cannot_delete_current_user")

if __name__ == "__main__":
    unittest.main()
