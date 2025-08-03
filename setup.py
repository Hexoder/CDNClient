from setuptools import setup, find_packages

setup(
    name="cdn_package",
    version="1.0.25",
    packages=find_packages(),
    install_requires=[
        "grpcio",
        "grpcio-tools",
        "djangorestframework",
        "markdown",
        "django-filter"
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
