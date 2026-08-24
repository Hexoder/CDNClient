from setuptools import setup, find_packages

setup(
    name="cdn_package",
    version="1.3.0.3",
    packages=find_packages(),
    install_requires=[
        "grpcio==1.83.0",
        "grpcio-tools==1.83.0",
        "djangorestframework",
        "markdown",
        "django-filter",
        "aio_pika"
    ],
    description="A gRPC-based CDN package for microservices",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Armin Fekri",
    author_email="armiin.fekri1@gmail.com",
    url="https://github.com/Hexoder/CDNClient",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires=">=3.10",  # Specify Python version compatibility
)
