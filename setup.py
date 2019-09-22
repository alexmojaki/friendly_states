import os
import re
from io import open

from setuptools import setup

package = 'friendly_states'
dirname = os.path.dirname(__file__)


def file_to_string(*path):
    with open(os.path.join(dirname, *path), encoding='utf8') as f:
        return f.read()


# __version__ is defined inside the package, but we can't import
# it because it imports dependencies which may not be installed yet,
# so we extract it manually
contents = file_to_string(package, '__init__.py')
__version__ = re.search(r"__version__ = '([.\d]+)'", contents).group(1)

install_requires = [
]

tests_require = [
    'pytest',
    'pytest-pythonpath',
    'pytest-django',
    'django',
    'jupyter',
    'nbconvert',
    'matplotlib',
    'networkx',
]

setup(
    name=package,
    version=__version__,
    description="Declarative, explicit, tool-friendly finite state machines in Python",
    long_description=file_to_string('README.md'),
    long_description_content_type='text/markdown',
    url='http://github.com/alexmojaki/' + package,
    author='Alex Hall',
    author_email='alex.mojaki@gmail.com',
    license='MIT',
    packages=[package],
    install_requires=install_requires,
    tests_require=tests_require,
    extras_require={
        'tests': tests_require,
    },
    classifiers=[
        'Intended Audience :: Developers',
        'Programming Language :: Python :: 3.7',
        'License :: OSI Approved :: MIT License',
        'Operating System :: OS Independent',
    ],
)
