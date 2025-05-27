from pathlib import Path

import grpc

from .decorators import cdn_cache
from .proto import cdn_pb2, cdn_pb2_grpc
from threading import Lock
from google.protobuf.json_format import MessageToDict
from django.conf import settings
import tempfile
from django.core.cache import caches

SERVICE_NAME = getattr(settings, "SERVICE_NAME")
SUB_SERVICE_NAME = getattr(settings, "SUB_SERVICE_NAME")


def get_secure_channel(server_domain):
    cert_path = 'cdnservice.pem'

    # Load server certificate
    with open(cert_path, "rb") as f:
        trusted_certs = f.read()

    # Create SSL/TLS credentials
    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

    # Create a secure channel
    return grpc.secure_channel(f"{server_domain}:50051", credentials)


def try_except(func):
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            return result

        except grpc.RpcError as e:
            error_message = f"Error: {e.code()} - {e.details()}"
            print(error_message)

        except Exception as err:
            print(err)

    return wrapper


class CDNClient:
    _instance = None
    _lock = Lock()
    _service_name = None
    _sub_service_name = None
    _conn_address = None
    _cdn_cache = None
    _cache_timeout = 60 * 60 * 24  # 24 hours default cache timeout

    def __new__(cls):
        server_address = getattr(settings, "CDN_GRPC_ADDRESS", "localhost")
        service_name = getattr(settings, "SERVICE_NAME", None)
        sub_service_name = getattr(settings, "SUB_SERVICE_NAME", None)

        if not service_name:
            raise Exception("Define SERVICE_NAME in django settings")
        if not sub_service_name:
            raise Exception("Define SUB_SERVICE_NAME in django settings")
        if not server_address:
            raise Exception("set CDN_GRPC_ADDRESS in django settings")

        cls._service_name = service_name
        cls._sub_service_name = sub_service_name
        cls._conn_address = f"{server_address}:50051"

        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CDNClient, cls).__new__(cls)

                try:
                    cdn_cache = caches['cdn']
                    cls._cdn_cache = cdn_cache
                except KeyError:
                    raise Exception("setup new redis cache named cdn [with desired redis db] ")

                cls._instance.channel = get_secure_channel(server_address)
                # cls._instance.channel = grpc.insecure_channel(cls._conn_address)

                cls._instance.stub = cdn_pb2_grpc.CDNServiceStub(cls._instance.channel)

        return cls._instance

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.channel.close()

    def _make_key(self, image_id: str) -> str:
        """Make a namespaced cache key."""
        return f"cdn:{image_id}"

    def _get_metadata(self, image_id: str) -> dict | None:
        """Get metadata for an image_id."""
        key = self._make_key(image_id)
        return self._cdn_cache.get(key)

    def _set_metadata(self, image_id: str, metadata: dict) -> None:
        """Set or overwrite metadata for an image_id."""
        key = self._make_key(image_id)
        self._cdn_cache.set(key, metadata, timeout=self._cache_timeout)

    def _get_last_temp(self, image_id: str) -> str | None:
        """Get downloaded path for an image_id."""
        key = self._make_key(image_id)
        result = self._cdn_cache.get(key)
        if result:
            path = result.get('temp_path', None)
            if path:
                return path

    def _update_temp_path(self, image_id: str, temp_path: str) -> None:
        """Update only temp_path field for an existing metadata."""
        key = self._make_key(image_id)
        metadata = self._cdn_cache.get(key)

        if metadata is None:
            # If no metadata exists, create a new one
            metadata = {}

        metadata['temp_path'] = temp_path
        self._cdn_cache.set(key, metadata, timeout=self._cache_timeout)

    @cdn_cache(_get_metadata, _set_metadata)
    def get_file_metadata(self, uuid: str) -> dict:
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.GetFileMetadata(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    @cdn_cache(_get_last_temp, _update_temp_path)
    def download_file(self, uuid: str, output_file_path: str = None, file_name: str = None) -> str:
        request = cdn_pb2.FileRequest(uuid=uuid)

        if not output_file_path:
            with tempfile.NamedTemporaryFile(delete=False, suffix=f"_{file_name}") as temp_file:

                temp_file_path = temp_file.name

                try:
                    # Write chunks to the temporary file
                    for chunk in self.stub.GetFileContent(request):
                        temp_file.write(chunk.file_content)

                    print(f"File downloaded to temporary file: {temp_file_path}")
                    return temp_file_path  # Return the temp file path
                except Exception as e:
                    print(f"Error during file download: {e}")
                    raise

        else:
            with open(output_file_path, 'wb') as f:

                for chunk in self.stub.GetFileContent(request):
                    f.write(chunk.file_content)
            print(f"File downloaded to {output_file_path}")
            return output_file_path

    def check_file_status(self, uuid: str) -> dict:
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.GetFileStatus(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def assign_to_instance(self, uuid: str, content_type_id: int, object_id: int, local_id: int | None = None) -> dict:
        request = cdn_pb2.AssignUnassignRequest(
            uuid=uuid,
            service_name=SERVICE_NAME,
            sub_service_name=SUB_SERVICE_NAME,
            content_type_id=content_type_id,
            object_id=object_id,
            local_id=local_id)
        result = self.stub.AssignToInstance(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def unassign_from_instance(self, uuid: str, content_type_id: int, object_id: int,
                               local_id: int | None = None) -> dict:
        request = cdn_pb2.AssignUnassignRequest(
            uuid=uuid,
            service_name=SERVICE_NAME,
            sub_service_name=SUB_SERVICE_NAME,
            content_type_id=content_type_id,
            object_id=object_id,
            local_id=local_id)
        result = self.stub.UnassignFromInstance(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def upload_file(self, file: bytes, file_name: str, service_name: str, app_name: str, model_name: str) -> dict:

        request = cdn_pb2.File(file=file, file_name=file_name, service_name=service_name, app_name=app_name,
                               model_name=model_name)
        result = self.stub.UploadFile(request)
        return MessageToDict(result)

    def filter_file(self, service_name: str = None, sub_service_name: str = None, user_id: int = None,
                    uuid_list: list[str] = None):
        request = cdn_pb2.FilterFileRequest(
            service_name=service_name,
            sub_service_name=sub_service_name,
            user_id=user_id,
            uuid_list=uuid_list
        )
        result = self.stub.FilterFile(request)
        return MessageToDict(result)

    @property
    def service_name(self):
        return self._service_name

    @property
    def sub_service_name(self):
        return self._sub_service_name
