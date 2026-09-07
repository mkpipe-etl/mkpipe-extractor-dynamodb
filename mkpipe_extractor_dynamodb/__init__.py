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
        has_static_bounds = table.filter_lower_bound is not None or table.filter_upper_bound is not None
        columns = table.iterate_columns
        is_multi = table.is_multi_iterate_column

        if table.replication_method.value == 'incremental' and table.iterate_column and has_static_bounds:
            from boto3.dynamodb.conditions import Attr
            combined = None
            for col in columns:
                col_expr = None
                if table.filter_lower_bound is not None:
                    col_expr = Attr(col).gte(table.filter_lower_bound)
                if table.filter_upper_bound is not None:
                    upper = Attr(col).lt(table.filter_upper_bound)
                    col_expr = col_expr & upper if col_expr else upper
                combined = col_expr if combined is None else (combined | col_expr)
            scan_kwargs['FilterExpression'] = combined
            write_mode = 'append'
        elif table.replication_method.value == 'incremental' and last_point and table.iterate_column:
            from boto3.dynamodb.conditions import Attr
            if is_multi:
                combined = None
                for col in columns:
                    cond = Attr(col).gte(last_point)
                    combined = cond if combined is None else (combined | cond)
                scan_kwargs['FilterExpression'] = combined
            else:
                scan_kwargs['FilterExpression'] = Attr(columns[0]).gte(last_point)
            write_mode = 'append'
        else:
            write_mode = 'overwrite'

        items = []
        total_segments = table.partitions_count if table.partitions_count > 1 else 1

        if total_segments > 1:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            def scan_segment(segment: int) -> list:
                seg_kwargs = {**scan_kwargs, 'TotalSegments': total_segments, 'Segment': segment}
                seg_items = []
                while True:
                    resp = ddb_table.scan(**seg_kwargs)
                    seg_items.extend(resp.get('Items', []))
                    if 'LastEvaluatedKey' not in resp:
                        break
                    seg_kwargs['ExclusiveStartKey'] = resp['LastEvaluatedKey']
                return seg_items

            with ThreadPoolExecutor(max_workers=total_segments) as executor:
                futures = [executor.submit(scan_segment, seg) for seg in range(total_segments)]
                for future in as_completed(futures):
                    items.extend(future.result())
        else:
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
            values = [pdf[c].max() for c in columns]
            values = [v for v in values if v is not None and not pd.isna(v)]
            if values:
                last_point_value = str(max(values))

        logger.info({
            'table': table.target_name,
            'status': 'extracted',
            'write_mode': write_mode,
            'rows': len(items),
        })

        return ExtractResult(df=df, write_mode=write_mode, last_point_value=last_point_value)
