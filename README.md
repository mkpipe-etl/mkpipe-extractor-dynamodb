# mkpipe-extractor-dynamodb

DynamoDB extractor plugin for [MkPipe](https://github.com/mkpipe-etl/mkpipe). Reads DynamoDB tables using `boto3` and converts to Spark DataFrames.

## Documentation

For more detailed documentation, please visit the [GitHub repository](https://github.com/mkpipe-etl/mkpipe).

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

---

## Connection Configuration

```yaml
connections:
  dynamodb_source:
    variant: dynamodb
    region: us-east-1
    aws_access_key: AKIAIOSFODNN7EXAMPLE
    aws_secret_key: wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
```

---

## Table Configuration

```yaml
pipelines:
  - name: dynamodb_to_pg
    source: dynamodb_source
    destination: pg_target
    tables:
      - name: MyTable
        target_name: stg_my_table
        replication_method: full
```

### Incremental Replication

Filtering uses a DynamoDB `FilterExpression` (scans the full table but filters results):

```yaml
      - name: MyTable
        target_name: stg_my_table
        replication_method: incremental
        iterate_column: updated_at
```

---

## Read Parallelism (Parallel Scan)

By default DynamoDB is scanned sequentially (single segment). Setting `partitions_count > 1` enables **DynamoDB Parallel Scan**, which divides the table into N segments scanned concurrently via a `ThreadPoolExecutor`:

```yaml
      - name: MyTable
        target_name: stg_my_table
        replication_method: full
        partitions_count: 4     # scan 4 segments in parallel
```

### How it works

- DynamoDB's `Scan` API accepts `TotalSegments` and `Segment` parameters
- Each segment is an independent scan covering a non-overlapping portion of the table
- All segments run concurrently in a `ThreadPoolExecutor(max_workers=partitions_count)`
- Results are merged and converted to a single Spark DataFrame

### Performance Notes

- **Small tables (<100K items):** single segment is fast enough.
- **Large tables (>1M items):** `partitions_count: 4–8` gives significant speed-up.
- DynamoDB parallel scan consumes more read capacity units (RCUs) proportionally — ensure your table has sufficient provisioned or on-demand capacity.
- Maximum `TotalSegments` allowed by DynamoDB: 1,000,000 (practical limit is much lower).
- `FilterExpression` (incremental) is applied per segment — parallelism still works with incremental replication.

---

## All Table Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `name` | string | required | DynamoDB table name |
| `target_name` | string | required | Destination table name |
| `replication_method` | `full` / `incremental` | `full` | Replication strategy |
| `iterate_column` | string | — | Attribute used for incremental `FilterExpression` |
| `partitions_count` | int | `1` | Number of parallel scan segments |
| `tags` | list | `[]` | Tags for selective pipeline execution |
| `pass_on_error` | bool | `false` | Skip table on error instead of failing |
