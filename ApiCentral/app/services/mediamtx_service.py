import requests
from app.core.config import settings

class MediaMTXService:
    def __init__(self):
        self.base_url = settings.MEDIAMTX_API_URL
        self.auth = (settings.MEDIAMTX_API_USERNAME, settings.MEDIAMTX_API_PASSWORD) if settings.MEDIAMTX_API_USERNAME else None

    def create_path(self, path: str, read_jwt_secret: str = None, publish_jwt_secret: str = None):
        url = f"{self.base_url}/v1/config/paths/add/{path}"
        data = {}
        if read_jwt_secret:
            data["readUser"] = "jwt"
            data["readPass"] = read_jwt_secret
        if publish_jwt_secret:
            data["publishUser"] = "jwt"
            data["publishPass"] = publish_jwt_secret
        response = requests.post(url, json=data, auth=self.auth)
        return response.status_code == 200

    def delete_path(self, path: str):
        url = f"{self.base_url}/v1/config/paths/remove/{path}"
        response = requests.post(url, auth=self.auth)
        return response.status_code == 200

    def list_paths(self):
        url = f"{self.base_url}/v3/paths/list"
        response = requests.get(url, auth=self.auth)
        if response.status_code == 200:
            return response.json()
        return {"items": [], "itemCount": 0}

    def get_path_info(self, path: str):
        url = f"{self.base_url}/v3/paths/get/{path}"
        response = requests.get(url, auth=self.auth)
        if response.status_code == 200:
            return response.json()
        return None

mediamtx_service = MediaMTXService()