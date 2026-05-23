from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [line.strip() for line in fh if line.strip() and not line.startswith("#")]

setup(
    name="modeltrack",
    version="0.1.0",
    author="ModelTrack Contributors",
    author_email="modeltrack@example.com",
    description="A unified data pipeline and model registry framework",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/example/modeltrack",
    packages=find_packages(exclude=["tests*"]),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Topic :: Scientific/Engineering :: Artificial Intelligence",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    entry_points={
        "console_scripts": [
            "modeltrack=modeltrack.cli:main",
        ],
    },
    include_package_data=True,
    package_data={
        "modeltrack": ["py.typed"],
    },
)
