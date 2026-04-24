from dataclasses import dataclass
from typing import Optional


RTSP_BRAND_PRESETS = (
    {
        "code": "hikvision",
        "label": "Hikvision",
        "description": "Usa canales numerados y permite elegir stream principal o substream.",
        "default_port": 554,
        "supports_channel": True,
        "supports_substream": True,
        "requires_custom_path": False,
    },
    {
        "code": "dahua",
        "label": "Dahua",
        "description": "Genera la ruta realmonitor con canal y subtipo.",
        "default_port": 554,
        "supports_channel": True,
        "supports_substream": True,
        "requires_custom_path": False,
    },
    {
        "code": "axis",
        "label": "Axis",
        "description": "Usa la ruta estándar axis-media/media.amp.",
        "default_port": 554,
        "supports_channel": False,
        "supports_substream": False,
        "requires_custom_path": False,
    },
    {
        "code": "uniview",
        "label": "Uniview",
        "description": "Permite alternar entre video1 y video2.",
        "default_port": 554,
        "supports_channel": False,
        "supports_substream": True,
        "requires_custom_path": False,
    },
    {
        "code": "generic",
        "label": "Genérica / ONVIF",
        "description": "Genera una ruta simple tipo stream1 o stream2.",
        "default_port": 554,
        "supports_channel": False,
        "supports_substream": True,
        "requires_custom_path": False,
    },
    {
        "code": "custom_path",
        "label": "Ruta personalizada",
        "description": "Permite escribir manualmente la ruta RTSP completa después del host.",
        "default_port": 554,
        "supports_channel": False,
        "supports_substream": False,
        "requires_custom_path": True,
    },
)

RTSP_BRAND_ALIASES = {
    "hikvision": "hikvision",
    "hik": "hikvision",
    "dahua": "dahua",
    "dawa": "dahua",
    "axis": "axis",
    "uniview": "uniview",
    "unv": "uniview",
    "generic": "generic",
    "generica": "generic",
    "genérica": "generic",
    "onvif": "generic",
    "custom": "custom_path",
    "custom_path": "custom_path",
    "personalizada": "custom_path",
    "ruta_personalizada": "custom_path",
}


@dataclass
class CameraRTSPConfig:
    marca: str
    ip: str
    usuario: str
    password: str
    puerto: int = 554
    canal: int = 1
    substream: bool = False
    ruta_personalizada: Optional[str] = None


class RTSPGeneratorError(Exception):
    pass


class RTSPGenerator:
    @staticmethod
    def _authority(config: CameraRTSPConfig) -> str:
        usuario = str(config.usuario or "").strip()
        password = str(config.password or "").strip()
        if not usuario and not password:
            return f"{config.ip}:{config.puerto}"
        return f"{usuario}:{password}@{config.ip}:{config.puerto}"

    @staticmethod
    def generar(config: CameraRTSPConfig) -> str:
        marca = normalize_rtsp_brand(config.marca)

        if config.ruta_personalizada:
            ruta = config.ruta_personalizada.lstrip("/")
            return (
                f"rtsp://{RTSPGenerator._authority(config)}/{ruta}"
            )

        if marca == "hikvision":
            return RTSPGenerator._hikvision(config)

        if marca == "dahua":
            return RTSPGenerator._dahua(config)

        if marca == "axis":
            return RTSPGenerator._axis(config)

        if marca == "uniview":
            return RTSPGenerator._uniview(config)

        if marca == "generic":
            return RTSPGenerator._generic(config)

        if marca == "custom_path":
            raise RTSPGeneratorError("La ruta personalizada es obligatoria para esta marca.")

        raise RTSPGeneratorError(f"Marca no soportada: {config.marca}")

    @staticmethod
    def _hikvision(config):
        sufijo = "02" if config.substream else "01"
        stream_id = f"{config.canal}{sufijo}"
        return (
            f"rtsp://{RTSPGenerator._authority(config)}/Streaming/Channels/{stream_id}"
        )

    @staticmethod
    def _dahua(config):
        subtype = 1 if config.substream else 0
        return (
            f"rtsp://{RTSPGenerator._authority(config)}"
            f"/cam/realmonitor?channel={config.canal}&subtype={subtype}"
        )

    @staticmethod
    def _axis(config):
        return (
            f"rtsp://{RTSPGenerator._authority(config)}/axis-media/media.amp"
        )

    @staticmethod
    def _uniview(config):
        stream = "video2" if config.substream else "video1"
        return (
            f"rtsp://{RTSPGenerator._authority(config)}/media/{stream}"
        )

    @staticmethod
    def _generic(config):
        stream = "stream2" if config.substream else "stream1"
        return (
            f"rtsp://{RTSPGenerator._authority(config)}/{stream}"
        )


def mostrar_menu():
    print("\n" + "=" * 50)
    print(" GENERADOR DE RTSP PARA CÁMARAS IP ")
    print("=" * 50)
    print("1. Hikvision")
    print("2. Dahua")
    print("3. Axis")
    print("4. Uniview")
    print("5. Generic / ONVIF")
    print("6. Ruta personalizada")
    print("0. Salir")
    print("=" * 50)


def normalize_rtsp_brand(value: str) -> str:
    normalized = str(value or "").strip().lower()
    return RTSP_BRAND_ALIASES.get(normalized, normalized)


def get_rtsp_brand_presets() -> list[dict[str, object]]:
    return [dict(item) for item in RTSP_BRAND_PRESETS]


def obtener_marca(opcion: str):
    marcas = {
        "1": "hikvision",
        "2": "dahua",
        "3": "axis",
        "4": "uniview",
        "5": "generic",
        "6": "custom_path",
    }
    return marcas.get(opcion)


def main():
    while True:
        mostrar_menu()
        opcion = input("Seleccione una opción: ").strip()

        if opcion == "0":
            print("Saliendo...")
            break

        marca = obtener_marca(opcion)
        if not marca:
            print("Opción inválida")
            continue

        ip = input("IP cámara: ").strip()
        usuario = input("Usuario: ").strip()
        password = input("Password: ").strip()
        puerto = input("Puerto RTSP [554]: ").strip()
        puerto = int(puerto) if puerto else 554

        canal = 1
        substream = False
        ruta_personalizada = None

        if opcion != "6":
            canal_in = input("Canal [1]: ").strip()
            canal = int(canal_in) if canal_in else 1

            sub = input("¿Substream? (s/n): ").strip().lower()
            substream = sub == "s"
        else:
            ruta_personalizada = input("Ruta personalizada: ").strip()

        config = CameraRTSPConfig(
            marca=marca,
            ip=ip,
            usuario=usuario,
            password=password,
            puerto=puerto,
            canal=canal,
            substream=substream,
            ruta_personalizada=ruta_personalizada
        )

        try:
            url = RTSPGenerator.generar(config)
            print("\nURL RTSP generada:")
            print(url)
        except Exception as e:
            print(f"Error: {e}")


if __name__ == "__main__":
    main()
    
