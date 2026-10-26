"""
mmWave Firmware CI/CD Framework
Automated testing framework and CI/CD pipeline for TI mmWave radar sensor firmware.
"""
from setuptools import setup, find_packages

setup(
    name="mmwave-firmware-ci-framework",
    version="1.6.0",
    description="Automated testing framework for TI mmWave radar firmware validation",
    long_description=open("README.md").read(),
    long_description_content_type="text/markdown",
    author="Firmware Validation Team",
    python_requires=">=3.9",
    packages=find_packages(),
    install_requires=[
        "pytest>=7.2.0",
        "pyserial>=3.5",
        "pyvisa>=1.13.0",
        "pyvisa-py>=0.7.0",
        "pyyaml>=6.0",
        "jinja2>=3.1.0",
        "numpy>=1.21.0",
        "colorama>=0.4.6",
        "xmltodict>=0.13.0",
    ],
    extras_require={
        "dev": ["pytest-cov", "flake8", "mypy", "black"],
    },
    entry_points={
        "console_scripts": [
            "fw-test=framework.core.test_runner:main",
            "fw-flash=framework.targets.flash_programmer:main",
            "fw-report=framework.core.report_engine:main",
        ],
    },
)
