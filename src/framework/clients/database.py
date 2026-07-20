"""Lazy database clients for MySQL and ClickHouse."""

from __future__ import annotations

from typing import Any


class DatabaseClient:
    def __init__(self, databases: dict[str, dict[str, Any]]) -> None:
        self.databases = databases

    def query(self, name: str, sql: str, parameters: Any = None) -> list[dict[str, Any]]:
        config = self._config(name)
        engine = config["engine"].lower()
        if engine == "mysql":
            return self._mysql_query(config, sql, parameters)
        if engine in {"clickhouse", "ch"}:
            return self._clickhouse_query(config, sql, parameters)
        raise ValueError(f"Unsupported database engine: {engine}")

    def execute(self, name: str, sql: str, parameters: Any = None) -> int:
        config = self._config(name)
        if config["engine"].lower() != "mysql":
            raise ValueError("execute is currently intended for MySQL; use query for ClickHouse")
        import pymysql

        options = {key: value for key, value in config.items() if key not in {"engine", "name"}}
        if isinstance(options.get("port"), str) and options["port"].isdigit():
            options["port"] = int(options["port"])
        with pymysql.connect(**options) as connection:
            with connection.cursor() as cursor:
                affected = cursor.execute(sql, parameters)
            connection.commit()
        return affected

    def _config(self, name: str) -> dict[str, Any]:
        if name not in self.databases:
            raise KeyError(f"Database '{name}' is not configured")
        return self.databases[name]

    @staticmethod
    def _mysql_query(config: dict[str, Any], sql: str, parameters: Any) -> list[dict[str, Any]]:
        import pymysql

        options = {key: value for key, value in config.items() if key not in {"engine", "name"}}
        if isinstance(options.get("port"), str) and options["port"].isdigit():
            options["port"] = int(options["port"])
        options.setdefault("cursorclass", pymysql.cursors.DictCursor)
        with pymysql.connect(**options) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, parameters)
                return list(cursor.fetchall())

    @staticmethod
    def _clickhouse_query(config: dict[str, Any], sql: str, parameters: Any) -> list[dict[str, Any]]:
        import clickhouse_connect

        options = {key: value for key, value in config.items() if key not in {"engine", "name"}}
        if isinstance(options.get("port"), str) and options["port"].isdigit():
            options["port"] = int(options["port"])
        client = clickhouse_connect.get_client(**options)
        try:
            result = client.query(sql, parameters=parameters)
            return [dict(zip(result.column_names, row)) for row in result.result_rows]
        finally:
            client.close()
