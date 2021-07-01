# -*- coding: utf-8 -*-

try:
    from setuptools import setup, Extension
except ImportError:
    from distutils.core import setup

import os.path

from setuptools import dist
dist.Distribution().fetch_build_eggs(['Cython>=0.15.1', 'numpy>=1.10', 'six>=1.15'])

readme = ''
here = os.path.abspath(os.path.dirname(__file__))
readme_path = os.path.join(here, 'README.md')
if os.path.exists(readme_path):
    with open(readme_path, 'rb') as stream:
        readme = stream.read().decode('utf8')

setup(
    long_description=readme,
    name='kipet',
    version='1.0.1',
    description='An all-in-one tool for fitting kinetic models using spectral and other state data',
    python_requires='==3.*,>=3.8.0',
    project_urls={
        "repository": "https://github.com/salvadorgarciamunoz/kipet"},
    author='Kevin McBride, Christina Schenk, Michael Short, Jose Santiago Rodriguez, David M. Thierry, Salvador Garcia-Munoz, Lorenz T. Biegler',
    author_email='kevin.w.mcbride.86@gmail.com',
    maintainer='Kevin McBride',
    license='GPL-3.0-or-later',
    keywords='optimization scientific parameter reaction spectral',
    packages=[
        'kipet', 'kipet.calculation_tools', 'kipet.estimability_tools', 'kipet.estimator_tools',
        'kipet.general_settings', 'kipet.input_output', 'kipet.main_modules', 'kipet.mixins',
	'kipet.model_components', 'kipet.model_tools', 'kipet.variance_methods',
        'kipet.visuals'
    ],
    package_dir={"": "."},
    package_data={
        "kipet": ["*.yml"],
    },
    install_requires=[
        'attrs==20.*,>=20.3.0', 'matplotlib==3.*,>=3.3.4',
        'numpy==1.*,>=1.20.1', 'pandas==1.*,>=1.2.2', 'pint==0.*,>=0.16.1',
        'plotly==4.*,>=4.14.3', 'pyomo==5.*,>=5.7.3', 'pyyaml==5.*,>=5.4.1',
        'scipy==1.*,>=1.6.0', 'kaleido==0.2.1', 'jinja2==3.0.1', 'pytexit==0.3.4',
    ],
    extras_require={"dev": ["pytest==5.*,>=5.2.0", "isort==5.*,>=5.8.0", "mypy>=0.812", "sphinx-rtd-theme==0.5.2"]},

)
