import tempfile
from pathlib import Path
from threading import Lock

import grpc
from django.conf import settings
from django.core.cache import caches
from google.protobuf.json_format import MessageToDict

from .decorators import cdn_cache
from .proto import cdn_pb2, cdn_pb2_grpc

APP_NAME = getattr(settings, "APP_NAME", "cdn")


def get_secure_channel(server_domain):
    cert_path = f'cdnservice_{APP_NAME}.pem'

    # Load server certificate
    with open(cert_path, "rb") as f:
        trusted_certs = f.read()

    # Create SSL/TLS credentials
    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

    # Create a secure channel
    return grpc.secure_channel(server_domain, credentials)


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
    _conn_address = None
    _cdn_cache = None
    _cache_timeout = 60 * 60 * 24  # 24 hours default cache timeout

    def __new__(cls):
        server_address = getattr(settings, "CDN_GRPC_ADDRESS")

        if not server_address:
            raise Exception("set CDN_GRPC_ADDRESS in django settings (CDN_GRPC_ADDRESS='localhost:50051')")

        cls._conn_address = server_address

        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CDNClient, cls).__new__(cls)

                try:
                    cache = caches['cdn']
                    cls._cdn_cache = cache
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

    @staticmethod
    def _make_key(file_id: str) -> str:
        """Make a namespaced cache key."""
        return f"cdn:{file_id}"

    def _get_metadata(self, file_id: str) -> dict | None:
        """Get metadata for an image_id."""
        key = self._make_key(file_id)
        return self._cdn_cache.get(key)

    def _set_metadata(self, file_id: str, metadata: dict) -> None:
        """Set or overwrite metadata for an image_id."""
        key = self._make_key(file_id)
        self._cdn_cache.set(key, metadata, timeout=self._cache_timeout)

    def _get_last_temp(self, file_id: str) -> str | None:
        """Get downloaded path for an image_id."""
        key = self._make_key(file_id)
        result = self._cdn_cache.get(key)
        if result:
            path = result.get('temp_path', None)
            if path and Path(path).exists():
                return path
            return None
        return None

    def _update_temp_path(self, file_id: str, temp_path: str) -> None:
        """Update only temp_path field for an existing metadata."""
        key = self._make_key(file_id)
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
    def download_file(self, uuid: str, output_dir: str = None) -> str:
        request = cdn_pb2.FileRequest(uuid=uuid)
        file_data = self.get_file_metadata(uuid)
        file_name = file_data.get('file_name')

        if not output_dir:
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
            path = Path(output_dir) / file_name
            if path.exists():
                print(f"File already exists: {path} , replacing...")
            with open(path, 'wb') as f:

                for chunk in self.stub.GetFileContent(request):
                    f.write(chunk.file_content)
            print(f"File downloaded to {path}")
            return path

    def check_file_status(self, uuid: str) -> dict:
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.GetFileStatus(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def assign_to_instance(self, uuid: str,
                           content_type_id: int,
                           object_id: int,
                           requested_user_id: int | None = None,
                           local_key: int | None = None) -> dict:

        request = cdn_pb2.AssignUnassignRequest(
            uuid=uuid,
            content_type_id=content_type_id,
            object_id=object_id,
            local_key=local_key,
            requested_user_id=requested_user_id)

        result = self.stub.AssignToInstance(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def unassign_from_instance(self, uuid: str,
                               content_type_id: int,
                               object_id: int,
                               requested_user_id: int | None = None,
                               local_key: int | None = None) -> dict:

        request = cdn_pb2.AssignUnassignRequest(
            uuid=uuid,
            content_type_id=content_type_id,
            object_id=object_id,
            local_key=local_key,
            requested_user_id=requested_user_id)

        result = self.stub.UnassignFromInstance(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def upload_file(self, file: bytes,
                    file_name: str,
                    metadata={"alt": ""},
                    is_public: bool = False,
                    accessed_users=None,
                    requested_user_id=0,
                    chunk_size: int = 1024 * 1024) -> dict:

        if accessed_users is None:
            accessed_users = []

        def chunk_generator():
            # Send metadata in the first chunk
            first = True
            for i in range(0, len(file), chunk_size):
                chunk = file[i:i + chunk_size]
                if first:
                    yield cdn_pb2.FileChunk(data=chunk,
                                            file_name=file_name,
                                            metadata=metadata,
                                            is_public=is_public,
                                            accessed_users=accessed_users,
                                            user_id=requested_user_id)
                    first = False
                else:
                    yield cdn_pb2.FileChunk(data=chunk)

        result = self.stub.UploadFile(chunk_generator())
        return MessageToDict(result)

    def filter_file(self, user_id: int = None,
                    uuid_list: list[str] = None, is_public: bool | None = None):
        request = cdn_pb2.FilterFileRequest(
            user_id=user_id,
            uuid_list=uuid_list
        )
        if is_public is not None:
            request.is_public = is_public

        result = self.stub.FilterFile(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def hls_status(self, uuid):
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.HLSStatus(request)
        return MessageToDict(result, preserving_proto_field_name=True)

    def hls_url(self, uuid):
        key = self._make_key(f"stream:{uuid}")
        result = self._cdn_cache.get(key)
        if result is None:
            result = self.hls_status(uuid).get('stream_url', None)
            self._cdn_cache.set(key, result, timeout=self._cache_timeout)

        return result

    def prepare_hls(self, uuid):
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.PrepareHLS(request)
        return MessageToDict(result, preserving_proto_field_name=True)
