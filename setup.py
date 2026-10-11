import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="yliveticker",
    version="0.5.6",
    author="Alex Paramonov",
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
    install_requires=['protobuf>=3.20.3,<8', 'websocket-client>=1.6.0', 'tzdata'],
    package_data={'yliveticker': ['dashboard_template.json', 'yaticker.proto']},
    extras_require={
        'pandas': ['pandas'],
        'cli': ['rich', 'prompt_toolkit'],
        'influxdb': ['influxdb-client'],
        'timescaledb': ['psycopg2-binary'],
        'clickhouse': ['clickhouse-connect'],
        'questdb': ['questdb'],
        'timestream': ['boto3'],
        'all': [
            'pandas', 'rich', 'prompt_toolkit', 'influxdb-client',
            'psycopg2-binary', 'clickhouse-connect', 'questdb', 'boto3'
        ],
    },
    entry_points={
        'console_scripts': [
            'yliveticker=yliveticker.cli:main',
        ],
    },
    python_requires='>=3.10'
)
