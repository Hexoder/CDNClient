from pathlib import Path

import grpc
from .proto import cdn_pb2, cdn_pb2_grpc
from threading import Lock
from google.protobuf.json_format import MessageToDict
from django.conf import settings
import tempfile


def get_secure_channel(server_domain):
    cert_path = Path(__file__).parent / "cert" / "fullchain.pem"
    # Load server certificate
    with open(cert_path, "rb") as f:
        trusted_certs = f.read()

    # Create SSL/TLS credentials
    credentials = grpc.ssl_channel_credentials(root_certificates=trusted_certs)

    # Create a secure channel
    return grpc.secure_channel(f"{server_domain}:50051", credentials)


class CDNClient:
    _instance = None
    _lock = Lock()

    def __new__(cls):
        server_address = getattr(settings, "CDN_SERVER_ADDRESS", None)
        if not server_address:
            raise Exception("set GRPC_SERVER_ADDRESS in django settings")
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(CDNClient, cls).__new__(cls)

                cls._instance.channel = get_secure_channel(server_address)
                cls._instance.stub = cdn_pb2_grpc.CDNServiceStub(cls._instance.channel)

                # cls._instance.channel = grpc.insecure_channel(server_address)
                # cls._instance.stub = cdn_pb2_grpc.CDNServiceStub(cls._instance.channel)

        return cls._instance

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.channel.close()

    def get_file_metadata(self, uuid: str):
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.GetFileMetadata(request)
        return MessageToDict(result)

    def download_file(self, uuid: str, output_file_path: str = None, file_name: str = None):
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

    def check_file_status(self, uuid: str):
        request = cdn_pb2.FileRequest(uuid=uuid)
        result = self.stub.GetFileStatus(request)
        return MessageToDict(result)

    def set_to_path(self, uuid: str, path: str, service_name: str, app_name: str, model_name: str):
        request = cdn_pb2.SetToPathRequest(uuid=uuid, path=path, service_name=service_name,
                                           app_name=app_name, model_name=model_name)
        result = self.stub.SetToPath(request)
        return MessageToDict(result)

    def delete_file(self, uuid: str, hard_delete: bool = True):
        request = cdn_pb2.FileDeleteRequest(uuid=uuid, hard_delete=hard_delete)
        result = self.stub.DeleteFile(request)
        return MessageToDict(result)
