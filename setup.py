#!/usr/bin/env python
from setuptools import setup, find_packages


tests_require = ['nose']

setup(
    name="katsdpsigproc",
    description="Karoo Array Telescope accelerated signal processing tools",
    author="SKA SA Science Processing Team",
    author_email="spt@ska.ac.za",
    packages=find_packages(),
    package_data={'': ['*.mako']},
    scripts=["scripts/rfiflagtest.py"],
    url="https://github.com/ska-sa/katsdpsigproc",
    setup_requires=["katversion"],
    install_requires=[
        "numpy>=1.10",
        "scipy",
        "pandas",
        "numba>=0.36.1",   # Older versions have bugs in median functions
        "decorator",
        "mako",
        "appdirs"
    ],
    extras_require={
        "CUDA": ["pycuda>=2015.1.3"],
        "OpenCL": ["pyopencl>=2017.2.1"],
        "test": tests_require,
        "doc": ["sphinx>=1.3"]
    },
    python_requires=">=3.5",
    tests_require=tests_require,
    zip_safe=False,
    use_katversion=True
)
