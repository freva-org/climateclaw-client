import versioneer
from setuptools import find_packages, setup

setup(
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    packages=find_packages(where="src"),
    package_dir={"": "src"},
    package_data={"climateclaw_client": ["py.typed"]},
    zip_safe=False,
)
