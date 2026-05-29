from pathlib import Path
import re

import setuptools

ROOT = Path(__file__).parent

with open(ROOT / "README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

init_text = (ROOT / "avea" / "__init__.py").read_text(encoding="utf-8")
version_match = re.search(
    r'^__version__\s*=\s*[\'"]([^\'"]+)[\'"]\s*$',
    init_text,
    re.MULTILINE,
)
if version_match is None:
    raise RuntimeError("Unable to find __version__ in avea/__init__.py")
version = version_match.group(1)

setuptools.setup(
    name="avea",
    version=version,
    author="k0rventen",
    description="Control an Elgato Avea bulb using python3",
    long_description=long_description,
    long_description_content_type="text/markdown",
    license="MIT",
    url="https://github.com/k0rventen/avea",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    install_requires=[
        "bleak>=1.0.0",
        "bleak-retry-connector>=4.0.0",
    ],
    extras_require={
        "dev": [
            "black>=26,<27",
            "pytest",
        ],
    },
    python_requires=">=3.10,<4",
)
