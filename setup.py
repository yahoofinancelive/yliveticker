import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="yliveticker",
    version="0.2.7",
    author="Alexey Paramonov",
    author_email="yliveticker@gmail.com",
    description="Live market data from Yahoo! Finance websocket",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yahoofinancelive/yliveticker",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    install_requires=['protobuf>=3.11.0', 'websocket-client>=0.57.0'],
    python_requires='>=2.7, !=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*, !=3.4.*'
)
