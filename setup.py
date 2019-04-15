import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="avea",
    version="1.2.6",
    author="corentin",
    description="Control an Elgato Avea bulb using python",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/k0rventen/avea",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: POSIX :: Linux",
    ],
    install_requires=[
        'bluepy',
    ],
)
