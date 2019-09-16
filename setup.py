import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="drf-optional-fields",
    version="0.0.1",
    author="zzhhss",
    author_email="clayhaw@163.com",
    description="A django-restframework extension to dynamically specify the returned field.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/zzhhss/drf-optional-fields",
    packages=setuptools.find_packages(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
