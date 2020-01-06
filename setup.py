
import os
import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

packages = setuptools.find_packages()
entry_points={
    'console_scripts': [
        'daedalus=daedalus.__main__:main',
    ],
}

#resources = {'res': []}
#for name in os.listdir('./res'):
#    path=os.path.join('res', name)
#    print(path)
#    resources['res'].append(path)

resources = []
for dirpath, dirnames, filenames in os.walk('./res'):
    paths = []
    for filename in filenames:
        path = os.path.join(dirpath, filename)
        paths.append(path)
        print(path)

    item = (dirpath, paths)
    resources.append(item)

setuptools.setup(
    name="daedalus",
    version="0.1.0",
    author="Nick Setzer",
    author_email="nicksetzer@github.com",
    description="unopinionated javascript compiler",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/nsetzer/daedalus",
    packages=packages,
    entry_points=entry_points,
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
    data_files=resources
    #package_data=resources
)