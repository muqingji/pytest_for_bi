"""Generated aggregate entry point for fs-bi HTTP APIs."""

from framework.api.catalog import HttpApiCatalog
from framework.api.http_api import HttpApiInvoker
from framework.clients.http import HttpClient
from .fs_bi_stat_api import StatApi

class FsBiApi:
    def __init__(self, http_client: HttpClient, catalog: HttpApiCatalog) -> None:
        invoker = HttpApiInvoker(http_client, catalog)
        self.stat = StatApi(invoker)
