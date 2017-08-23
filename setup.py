#!/usr/bin/env python
from setuptools import setup, find_packages

tests_require = ['nose', 'mock', 'unittest2']

setup(
    name="katsdpsigproc",
    description="Karoo Array Telescope accelerated signal processing tools",
    author_email="spt@ska.ac.za",
    packages=find_packages(),
    package_data={'': ['*.mako']},
    scripts=["scripts/rfiflagtest.py"],
    url="https://github.com/ska-sa/katsdpsigproc",
    setup_requires=["katversion"],
    install_requires=[
        "numpy>=1.10", "scipy", "pandas", "numba", "futures",
        "decorator", "mako", "appdirs", "futures", "trollius", "six"
    ],
    extras_require={
        "CUDA": ["pycuda>=2015.1.3"],
        "OpenCL": ["pyopencl"],
        "test": tests_require,
        "doc": ["sphinx>=1.3"]
    },
    tests_require=tests_require,
    zip_safe=False,
    use_katversion=True
)
