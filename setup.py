from setuptools import setup, find_packages

# also change in version.py
VERSION = "2.0.0"
DESCRIPTION = "A multi-asset algorithmic trading platform for forex, commodities, and more"
with open("requirements.txt", "r", encoding="utf-8") as f:
    REQUIRED_PACKAGES = f.read().splitlines()

with open("README.md", "r", encoding="utf-8") as f:
    LONG_DESCRIPTION = f.read()

setup(
    name='qengine',
    version=VERSION,
    author="Naresh Jhawar",
    packages=find_packages(),
    description=DESCRIPTION,
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    install_requires=REQUIRED_PACKAGES,
    entry_points='''
        [console_scripts]
        qengine=qengine.__init__:cli
    ''',
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.10',
    include_package_data=True,
    package_data={
        '': ['*.dll', '*.dylib', '*.so', '*.json'],
    },
)
