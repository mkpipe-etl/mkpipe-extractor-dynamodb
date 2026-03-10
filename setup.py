from setuptools import setup, find_packages

setup(
    name='mkpipe-extractor-dynamodb',
    version='0.1.1',
    license='Apache License 2.0',
    packages=find_packages(),
    install_requires=['mkpipe', 'boto3'],
    include_package_data=True,
    entry_points={
        'mkpipe.extractors': [
            'dynamodb = mkpipe_extractor_dynamodb:DynamoDBExtractor',
        ],
    },
    description='DynamoDB extractor for mkpipe.',
    author='Metin Karakus',
    author_email='metin_karakus@yahoo.com',
    python_requires='>=3.9',
)
