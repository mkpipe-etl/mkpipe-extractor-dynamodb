from typing import Optional

from mkpipe.spark.base import BaseExtractor
from mkpipe.models import ConnectionConfig, ExtractResult, TableConfig
from mkpipe.utils import get_logger

logger = get_logger(__name__)


class DynamoDBExtractor(BaseExtractor, variant='dynamodb'):
    def __init__(self, connection: ConnectionConfig):
        self.connection = connection
        self.region = connection.region or 'us-east-1'
        self.aws_access_key = connection.aws_access_key
        self.aws_secret_key = connection.aws_secret_key

    def extract(self, table: TableConfig, spark, last_point: Optional[str] = None) -> ExtractResult:
        logger.info({
            'table': table.target_name,
            'status': 'extracting',
            'replication_method': table.replication_method.value,
        })

        import boto3
        import pandas as pd

        session = boto3.Session(
            aws_access_key_id=self.aws_access_key,
            aws_secret_access_key=self.aws_secret_key,
            region_name=self.region,
        )
        dynamodb = session.resource('dynamodb')
        ddb_table = dynamodb.Table(table.name)

        scan_kwargs = {}
        if table.replication_method.value == 'incremental' and last_point and table.iterate_column:
            from boto3.dynamodb.conditions import Attr
            scan_kwargs['FilterExpression'] = Attr(table.iterate_column).gt(last_point)
            write_mode = 'append'
        else:
            write_mode = 'overwrite'

        items = []
        while True:
            response = ddb_table.scan(**scan_kwargs)
            items.extend(response.get('Items', []))
            if 'LastEvaluatedKey' not in response:
                break
            scan_kwargs['ExclusiveStartKey'] = response['LastEvaluatedKey']

        if not items:
            logger.info({'table': table.target_name, 'status': 'extracted', 'rows': 0})
            return ExtractResult(df=None, write_mode=write_mode)

        pdf = pd.DataFrame(items)
        df = spark.createDataFrame(pdf)

        last_point_value = None
        if table.replication_method.value == 'incremental' and table.iterate_column:
            from pyspark.sql import functions as F
            row = df.agg(F.max(table.iterate_column).alias('max_val')).first()
            if row and row['max_val'] is not None:
                last_point_value = str(row['max_val'])

        logger.info({
            'table': table.target_name,
            'status': 'extracted',
            'write_mode': write_mode,
            'rows': len(items),
        })

        return ExtractResult(df=df, write_mode=write_mode, last_point_value=last_point_value)
