"""Generated from fs-bi Java HTTP declarations. Do not edit."""

from __future__ import annotations

from typing import Any

from framework.api.http_api import HttpApiInvoker
from framework.clients.models import ApiResponse

class StatApi:
    def __init__(self, invoker: HttpApiInvoker) -> None:
        self._invoker = invoker

    def agg_data_diff_agg_data_diff(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: AggDataDiffController.aggDataDiff
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggData/diff
        Request body: CheckDiffArg (required)
        Response: String
        Operation ID: fs_bi_stat.agg_data_diff.agg_data_diff
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_data_diff.agg_data_diff",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_add_new_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标规则
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/newAggRule/add
        Request body: AddAggRuleArg (required)
        Response: AddNewAggRuleResult
        Operation ID: fs_bi_stat.agg_rule.add_new_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.add_new_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_batch_enable_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 批量开启指标
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleList/batchEnableAggRule
        Request body: BatchAggRuleFieldArg (required)
        Response: UpdateAggRuleStatusResult
        Operation ID: fs_bi_stat.agg_rule.batch_enable_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.batch_enable_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_batch_modify_agg_time_zone(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 批量修改指标时区
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleList/batchModifyAggTimeZone
        Request body: BatchAggRuleFieldArg (required)
        Response: UpdateAggRuleStatusResult
        Operation ID: fs_bi_stat.agg_rule.batch_modify_agg_time_zone
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.batch_modify_agg_time_zone",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_batch_stop_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: AggRuleController.batchStopAggRule
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleList/batchStopAggRule
        Request body: BatchAggRuleFieldArg (required)
        Response: UpdateAggRuleStatusResult
        Operation ID: fs_bi_stat.agg_rule.batch_stop_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.batch_stop_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_copy_detail_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标规则
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/newAggRule/detail/copy
        Request body: AddAggRuleArg (required)
        Response: AddNewAggRuleResult
        Operation ID: fs_bi_stat.agg_rule.copy_detail_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.copy_detail_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_copy_list_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标规则
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/newAggRule/list/copy
        Request body: AddAggRuleArg (required)
        Response: AddNewAggRuleResult
        Operation ID: fs_bi_stat.agg_rule.copy_list_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.copy_list_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_delete_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: AggRuleController.deleteAggRule
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRule/delete
        Request body: AggRuleArg (required)
        Response: DeleteAggRuleResult
        Operation ID: fs_bi_stat.agg_rule.delete_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.delete_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_get_permission(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: AggRuleController.getPermission
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/getPermission
        Request body: object (optional)
        Response: Permission
        Operation ID: fs_bi_stat.agg_rule.get_permission
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.get_permission",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_get_status(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: AggRuleController.getStatus
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRule/getStatus
        Request body: QueryDetailGoalRuleStatusArg (required)
        Response: QueryDetailGoalRuleStatusResult
        Operation ID: fs_bi_stat.agg_rule.get_status
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.get_status",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_agg_conditions_by_agg_object(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 通过选定的指标对象查询聚合字段、时间标尺列表、筛选条件字段
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggConditionsByAggObject/query
        Request body: AggRuleArg (required)
        Response: QueryAggConditionsResult
        Operation ID: fs_bi_stat.agg_rule.query_agg_conditions_by_agg_object
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_agg_conditions_by_agg_object",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_agg_object_list_by_schema_object_name(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggObjectListBySchemaObjectName/query
        Request body: AggRuleArg (required)
        Response: QueryAggObjectListResult
        Operation ID: fs_bi_stat.agg_rule.query_agg_object_list_by_schema_object_name
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_agg_object_list_by_schema_object_name",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_agg_rule_by_field_id(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 聚合指标规则详情页面和编辑页面查询聚合指标规则详情
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleByFieldId/query
        Request body: AggRuleArg (required)
        Response: AggRuleArg
        Operation ID: fs_bi_stat.agg_rule.query_agg_rule_by_field_id
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_agg_rule_by_field_id",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_agg_rule_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 列表页面根据条件查询聚合指标
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleList/query
        Request body: QueryAggRuleArg (required)
        Response: QueryAggRuleListResult
        Operation ID: fs_bi_stat.agg_rule.query_agg_rule_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_agg_rule_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_all_object_describe_api_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询该主题的规则的所属对象列表（在指标列表上面的对象列表处使用）
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/allObjectDescribeApiList/query
        Request body: AggRuleArg (required)
        Response: QueryAllObjectDescribeApiListResult
        Operation ID: fs_bi_stat.agg_rule.query_all_object_describe_api_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_all_object_describe_api_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_query_unused_field_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询没有被使用过的agg指标
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleList/unusedQuery
        Request body: AggRuleArg (required)
        Response: DefaultQueryAggListResult<UnusedStatFieldBO>
        Operation ID: fs_bi_stat.agg_rule.query_unused_field_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.query_unused_field_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_update_agg_data(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 预设指标
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/updateAggData
        Request body: UpdateAggDataArg (required)
        Response: Status
        Operation ID: fs_bi_stat.agg_rule.update_agg_data
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.update_agg_data",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_update_agg_rule(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 更新聚合指标规则
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRule/update
        Request body: AddAggRuleArg (required)
        Response: UpdateAggRuleResult
        Operation ID: fs_bi_stat.agg_rule.update_agg_rule
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.update_agg_rule",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_update_agg_rule_status(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 更新聚合指标规则的状态
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleStatus/update
        Request body: AggRuleArg (required)
        Response: UpdateAggRuleStatusResult
        Operation ID: fs_bi_stat.agg_rule.update_agg_rule_status
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.update_agg_rule_status",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def agg_rule_verify_agg_rule_limit_count(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 校验该主题下的聚合指标数是否超过限制数
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/aggRule/aggRuleLimitCount/verify
        Request body: AggRuleArg (required)
        Response: VerifyAggRuleCountResult
        Operation ID: fs_bi_stat.agg_rule.verify_agg_rule_limit_count
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.agg_rule.verify_agg_rule_limit_count",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def bill_board_query_bill_board_detail(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询排行榜数据详情
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/billBoard/detail/query
        Request body: QueryBillBoardDetailArg (required)
        Response: QueryReportResult
        Operation ID: fs_bi_stat.bill_board.query_bill_board_detail
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.bill_board.query_bill_board_detail",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def bill_board_query_bill_measure_data(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询排行榜指标数据
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/billBoard/measureData/query
        Request body: QueryBillMeasureDataArg (required)
        Response: QueryBillMeasureDataResult
        Operation ID: fs_bi_stat.bill_board.query_bill_measure_data
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.bill_board.query_bill_measure_data",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def biz_config_get_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取配置
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/config/getConfig
        Request body: QueryBizConfigArg (required)
        Response: QueryBizConfigResult
        Operation ID: fs_bi_stat.biz_config.get_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.biz_config.get_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def biz_config_get_user_auth(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取当前用户权限配置
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/config/getUserAuth
        Request body: UserDataAuthArg (required)
        Response: UserDataAuthResult
        Operation ID: fs_bi_stat.biz_config.get_user_auth
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.biz_config.get_user_auth",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def biz_config_save_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 保存配置
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/config/saveConfig
        Request body: SaveBizConfigArg (required)
        Response: Boolean
        Operation ID: fs_bi_stat.biz_config.save_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.biz_config.save_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_copy_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 创建副本
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/copy
        Request body: object (required)
        Response: CopyCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.copy_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.copy_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_create_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 创建维度
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/create
        Request body: object (required)
        Response: CreateCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.create_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.create_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_delete_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 删除维度
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/delete
        Request body: object (required)
        Response: DeleteCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.delete_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.delete_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_disable_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 停用维度
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/disable
        Request body: object (required)
        Response: DisableCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.disable_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.disable_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_enable_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 启用维度
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/enable
        Request body: object (required)
        Response: EnableCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.enable_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.enable_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_find_all_custom_dimension_objects(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取维度涉及对象
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/objects
        Request body: object (required)
        Response: FindCustomDimensionDescribeApiNamesResult
        Operation ID: fs_bi_stat.custom_dimension.find_all_custom_dimension_objects
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.find_all_custom_dimension_objects",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_find_custom_dimensions(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取维度列表-管理端
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions
        Request body: object (required)
        Response: FindCustomDimensionsResult
        Operation ID: fs_bi_stat.custom_dimension.find_custom_dimensions
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.find_custom_dimensions",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_get_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取维度详情
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/getById
        Request body: object (required)
        Response: GetCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.get_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.get_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def custom_dimension_update_custom_dimension(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 更新维度
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schema/dimensions/update
        Request body: object (required)
        Response: UpdateCustomDimensionResult
        Operation ID: fs_bi_stat.custom_dimension.update_custom_dimension
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.custom_dimension.update_custom_dimension",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def describe_query_detail(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: DescribeQueryController.detail
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/describes/detail
        Request body: object (required)
        Response: BiMtDescribe
        Operation ID: fs_bi_stat.describe_query.detail
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.describe_query.detail",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def describe_query_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: DescribeQueryController.list
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/describes/list
        Request body: object (required)
        Response: QueryDescribesResult
        Operation ID: fs_bi_stat.describe_query.list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.describe_query.list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def describe_query_relations(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: DescribeQueryController.relations
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/describes/relations
        Request body: object (required)
        Response: QueryDescribeRelationsResult
        Operation ID: fs_bi_stat.describe_query.relations
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.describe_query.relations",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_get_week_day(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: GoalRuleController.getWeekDay
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/getWeekDay
        Request body: QueryWeekDayArg (required)
        Response: QueryWeekDayResult
        Operation ID: fs_bi_stat.goal_rule.get_week_day
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.get_week_day",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_query_agg_conditions_by_agg_object(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表 改类为sfa提供 项目迁移后应该标准化接口 对象名称需要返回CRMName
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/aggConditionsByAggObject/query
        Request body: GoalRuleArg (required)
        Response: QueryGoalRuleFieldResult
        Operation ID: fs_bi_stat.goal_rule.query_agg_conditions_by_agg_object
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.query_agg_conditions_by_agg_object",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_query_area(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取地区信息
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/areaInfo/query
        Request body: QueryAreaArg (required)
        Response: QueryAreaResult
        Operation ID: fs_bi_stat.goal_rule.query_area
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.query_area",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_query_dept_relation(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取部门关系
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/deptRelation/query
        Request body: GoalRuleArg (required)
        Response: QueryGoalRuleDeptFieldResult
        Operation ID: fs_bi_stat.goal_rule.query_dept_relation
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.query_dept_relation",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_query_goal_object_list_by_schema_object_name(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表 改类为sfa提供 项目迁移后应该标准化接口 对象名称需要返回CRMName
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/goalObjectListBySchemaObjectName/query
        Request body: GoalRuleArg (required)
        Response: QueryAggObjectListResult
        Operation ID: fs_bi_stat.goal_rule.query_goal_object_list_by_schema_object_name
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.query_goal_object_list_by_schema_object_name",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def goal_rule_query_level_fields_by_check_object_name(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 目标规则获取层级字段
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/goalRule/checkLevel/query
        Request body: GoalRuleArg (required)
        Response: QueryGoalRuleLevelFieldResult
        Operation ID: fs_bi_stat.goal_rule.query_level_fields_by_check_object_name
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.goal_rule.query_level_fields_by_check_object_name",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def index_index(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: Created by liuq on 2016/10/24.
        Route: GET /FHH/EM1HBISTAT/fs-bi-stat
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.index.index
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.index.index",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def index_ws_test(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: IndexController.wsTest
        Route: GET /FHH/EM1HBISTAT/fs-bi-stat/ws
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.index.ws_test
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.index.ws_test",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def license_service_query_tenant_license(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: LicenseServiceController.queryTenantLicense
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/license/query
        Request body: QueryTenantLicenseDto.Arg (required)
        Response: QueryTenantLicenseDto.Result
        Operation ID: fs_bi_stat.license_service.query_tenant_license
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.license_service.query_tenant_license",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def metric_ai_visibility_update(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MetricAiVisibilityController.update
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/metricAiVisibility/update
        Request body: MetricAiVisibilityUpdateArg (required)
        Response: MetricAiVisibilityUpdateResult
        Operation ID: fs_bi_stat.metric_ai_visibility.update
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.metric_ai_visibility.update",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def metric_lifecycle_batch_disable(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MetricLifecycleController.batchDisable
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/metricLifecycle/batchDisable
        Request body: MetricLifecycleBatchArg (required)
        Response: MetricLifecycleBatchResult
        Operation ID: fs_bi_stat.metric_lifecycle.batch_disable
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.metric_lifecycle.batch_disable",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def metric_lifecycle_batch_enable(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MetricLifecycleController.batchEnable
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/metricLifecycle/batchEnable
        Request body: MetricLifecycleBatchArg (required)
        Response: MetricLifecycleBatchResult
        Operation ID: fs_bi_stat.metric_lifecycle.batch_enable
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.metric_lifecycle.batch_enable",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_currency_query_get_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MultiCurrencyQueryController.getConfig
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/multiCurrency/config/get
        Request body: UserInfo (required)
        Response: CurrencyConfig
        Operation ID: fs_bi_stat.multi_currency_query.get_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_currency_query.get_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_currency_query_get_multi_currency_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MultiCurrencyQueryController.getMultiCurrencyList
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/multiCurrency/getMultiCurrencyList
        Request body: UserInfo (required)
        Response: MultiCurrencyListResult
        Operation ID: fs_bi_stat.multi_currency_query.get_multi_currency_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_currency_query.get_multi_currency_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_currency_query_save_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MultiCurrencyQueryController.saveConfig
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/multiCurrency/config/save
        Request body: object (required)
        Response: void
        Operation ID: fs_bi_stat.multi_currency_query.save_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_currency_query.save_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_get_udf_describe(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询元数据
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/getUdfDescribe
        Request body: GetUdfDescribeArg (required)
        Response: GetUdfDescribeResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.get_udf_describe
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.get_udf_describe",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_get_week_day(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: MultiDimGoalRuleController.getWeekDay
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/getWeekDay
        Request body: QueryWeekDayArg (required)
        Response: QueryWeekDayResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.get_week_day
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.get_week_day",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_agg_conditions_by_agg_object(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表 改类为sfa提供 项目迁移后应该标准化接口 对象名称需要返回CRMName
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/aggConditionsByAggObject/query
        Request body: MultiDimGoalRuleArg (required)
        Response: QueryMultiDimGoalFieldListResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_agg_conditions_by_agg_object
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_agg_conditions_by_agg_object",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_area(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取地区信息
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/areaInfo/query
        Request body: QueryAreaArg (required)
        Response: QueryAreaResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_area
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_area",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_dept_relation(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取部门关系
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/deptRelation/query
        Request body: GoalRuleArg (required)
        Response: QueryGoalRuleDeptFieldResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_dept_relation
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_dept_relation",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_dim_conditions_by_agg_object(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表 改类为sfa提供 项目迁移后应该标准化接口 对象名称需要返回CRMName
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/dimObject/query
        Request body: MultiDimGoalRuleArg (required)
        Response: QueryAggObjectListResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_dim_conditions_by_agg_object
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_dim_conditions_by_agg_object",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_dim_fields(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 目标规则获取层级字段
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/dimField/query
        Request body: MultiDimGoalRuleArg (required)
        Response: QueryGoalDimFieldResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_dim_fields
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_dim_fields",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def multi_dim_goal_rule_query_goal_object_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新建聚合指标时查询所属对象列表 改类为sfa提供 项目迁移后应该标准化接口 对象名称需要返回CRMName
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/multiDim/goalRule/aggObject/query
        Request body: MultiDimGoalRuleArg (required)
        Response: QueryMultiDimGoalObjectListResult
        Operation ID: fs_bi_stat.multi_dim_goal_rule.query_goal_object_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.multi_dim_goal_rule.query_goal_object_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def rpt_query_get_reconciliation_sql(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: RptQueryController.getReconciliationSql
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/rpt/reconciliation/createSql
        Request body: QueryReportDataArg (required)
        Response: ReconciliationSqlResult
        Operation ID: fs_bi_stat.rpt_query.get_reconciliation_sql
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.rpt_query.get_reconciliation_sql",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def rpt_query_query_filter_ch_sql(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: RptQueryController.queryFilterChSql
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/rpt/filter/queryFilterChSql
        Request body: QueryReportDataArg (required)
        Response: String
        Operation ID: fs_bi_stat.rpt_query.query_filter_ch_sql
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.rpt_query.query_filter_ch_sql",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def rpt_query_query_report_data(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: RptQueryController.queryReportData
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/rpt/data/query
        Request body: QueryReportDataArg (required)
        Response: QueryReportResult
        Operation ID: fs_bi_stat.rpt_query.query_report_data
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.rpt_query.query_report_data",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def rpt_query_query_report_data_byte_array(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: RptQueryController.queryReportDataByteArray
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/rpt/data/queryWithKryo
        Request body: QueryReportDataArg (required)
        Response: KryoResult
        Operation ID: fs_bi_stat.rpt_query.query_report_data_byte_array
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.rpt_query.query_report_data_byte_array",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def schema_query_detail(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SchemaQueryController.detail
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schemas/detail
        Request body: object (required)
        Response: Schema
        Operation ID: fs_bi_stat.schema_query.detail
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.schema_query.detail",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def schema_query_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SchemaQueryController.list
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/schemas/list
        Request body: object (required)
        Response: List<Schema>
        Operation ID: fs_bi_stat.schema_query.list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.schema_query.list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def search_query_info_easy_stat_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询入口
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/searchQueryInfo/query
        Request body: SearchQueryInfoRequest (required)
        Response: JoinQueryResult
        Operation ID: fs_bi_stat.search_query_info_easy_stat.query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.search_query_info_easy_stat.query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_area_query_region_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询区域结果
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/area/region/query
        Request body: QueryAreaRegionArg (required)
        Response: QueryAreaRegionResult
        Operation ID: fs_bi_stat.stat_area.query_region_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_area.query_region_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_data_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法说明: 查询统计图的数据
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/detail/data/query
        Request body: AsyncQueryStatDetailInfoArg (required)
        Response: AsyncQueryStatSendResult
        Operation ID: fs_bi_stat.stat_async.data_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.data_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_load_query_detail_report_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatAsyncController.loadQueryDetailReportResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/detail/loadQueryStatResult
        Request body: LoadQueryStatResultArg (required)
        Response: AsyncQueryDetailResult
        Operation ID: fs_bi_stat.stat_async.load_query_detail_report_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.load_query_detail_report_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_load_query_report_merge_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatAsyncController.loadQueryReportMergeResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/loadQueryStatMergeResult
        Request body: LoadQueryStatResultArg (required)
        Response: AsyncQueryStatMergeResult
        Operation ID: fs_bi_stat.stat_async.load_query_report_merge_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.load_query_report_merge_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_load_query_report_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatAsyncController.loadQueryReportResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/loadQueryStatResult
        Request body: LoadQueryStatResultArg (required)
        Response: AsyncQueryStatResult
        Operation ID: fs_bi_stat.stat_async.load_query_report_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.load_query_report_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_send_query_stat_merge_request(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图合并查询
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/sendQueryStatMergeRequest
        Request body: AsyncQueryStatChartArg (required)
        Response: AsyncQueryStatSendResult
        Operation ID: fs_bi_stat.stat_async.send_query_stat_merge_request
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.send_query_stat_merge_request",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_async_send_query_stat_request(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatAsyncController.sendQueryStatRequest
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/async/sendQueryStatRequest
        Request body: AsyncQueryStatChartDataArg (required)
        Response: AsyncQueryStatSendResult
        Operation ID: fs_bi_stat.stat_async.send_query_stat_request
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_async.send_query_stat_request",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_backstage_data_query_and_upload(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图查询明细并上传文件服务,转后台用
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/queryAndUpload
        Request body: QueryStatDetailInfoArg (required)
        Response: FileModel
        Operation ID: fs_bi_stat.stat_base.backstage_data_query_and_upload
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.backstage_data_query_and_upload",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_chart_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.chartQuery
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/chart/query
        Request body: QueryChartFullArg (required)
        Response: QueryChartResult
        Operation ID: fs_bi_stat.stat_base.chart_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.chart_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_data_batch_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.dataBatchQuery
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/batchQuery
        Request body: List<QueryChartDataArg> (required)
        Response: List<QueryChartDataResult>
        Operation ID: fs_bi_stat.stat_base.data_batch_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.data_batch_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_data_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.dataQuery
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/query
        Request body: QueryChartDataArg (required)
        Response: QueryChartDataResult
        Operation ID: fs_bi_stat.stat_base.data_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.data_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_data_query_by_paging(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图导出分页查询数据
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/dataQueryByPaging
        Request body: QueryChartDataArg (required)
        Response: HttpEntity
        Operation ID: fs_bi_stat.stat_base.data_query_by_paging
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.data_query_by_paging",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_data_query_da655ba1(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.dataQuery
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/query
        Request body: QueryStatDetailInfoArg (required)
        Response: QueryReportResult
        Operation ID: fs_bi_stat.stat_base.data_query_da655ba1
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.data_query_da655ba1",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_delete_personal_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 删除个人级统计图查看明细列表字段配置
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/personalConfig/delete
        Request body: DeletePersonalConfigArg (required)
        Response: void
        Operation ID: fs_bi_stat.stat_base.delete_personal_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.delete_personal_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_detail_data_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图明细查询数据(导出时查询)
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/detailDataQuery
        Request body: QueryStatDetailInfoArg (required)
        Response: HttpEntity
        Operation ID: fs_bi_stat.stat_base.detail_data_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.detail_data_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_detail_simple_report_data_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图明细简易报表数据查询(分页导出使用)
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/detailSimpleReportDataQuery
        Request body: QueryStatDetailInfoArg (required)
        Response: HttpEntity
        Operation ID: fs_bi_stat.stat_base.detail_simple_report_data_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.detail_simple_report_data_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_get_appoint_level_data_info(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 根据指定的层级获取该层级下的所有部门信息
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/getAppointLevelDataInfo
        Request body: QueryAppointLevelDataInfoArg (required)
        Response: QueryAppointLevelDataResult
        Operation ID: fs_bi_stat.stat_base.get_appoint_level_data_info
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.get_appoint_level_data_info",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_get_calc_agg_sub_fields(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 获取计算指标的子指标列表
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/calcagg/subfields
        Request body: CalcAggSubFieldsArg (required)
        Response: CalcAggSubFieldsResult
        Operation ID: fs_bi_stat.stat_base.get_calc_agg_sub_fields
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.get_calc_agg_sub_fields",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_get_schema_drill_fields_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法描述: 获取主题可下钻相关信息
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schemaDrillFields/query
        Request body: GetSchemaDrillFieldsArg (required)
        Response: SchemaDillFieldsResult
        Operation ID: fs_bi_stat.stat_base.get_schema_drill_fields_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.get_schema_drill_fields_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_preview_schema_drill_fields_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法描述: 获取主题可下钻相关信息
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/previewSchemaDrillFields/query
        Request body: PreviewSchemaDrillFieldsArg (required)
        Response: SchemaDillFieldsResult
        Operation ID: fs_bi_stat.stat_base.preview_schema_drill_fields_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.preview_schema_drill_fields_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_query_metadata_feature(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.queryMetadataFeature
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/queryMetadataFeature
        Request body: object (optional)
        Response: MetadataFeatureResult
        Operation ID: fs_bi_stat.stat_base.query_metadata_feature
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.query_metadata_feature",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_query_stat_data_and_upload_by_page(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 统计图订阅分页查询接口
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/data/queryAndUploadByPage
        Request body: QueryChartDataArg (required)
        Response: FileModelExt
        Operation ID: fs_bi_stat.stat_base.query_stat_data_and_upload_by_page
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.query_stat_data_and_upload_by_page",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_query_user_segment(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.queryUserSegment
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/userSegment/get
        Request body: QueryUserSegmentArg (required)
        Response: UserSegmentResult
        Operation ID: fs_bi_stat.stat_base.query_user_segment
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.query_user_segment",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_query_view_restructure_feature(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.queryViewRestructureFeature
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/queryViewRestructureFeature
        Request body: QueryViewRestructureFeatureArg (required)
        Response: QueryViewRestructureFeatureResult
        Operation ID: fs_bi_stat.stat_base.query_view_restructure_feature
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.query_view_restructure_feature",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_save_detail_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 保存统计图查看明细页面全局配置(个人级)
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/saveDetailConfig
        Request body: SaveQueryArg (required)
        Response: void
        Operation ID: fs_bi_stat.stat_base.save_detail_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.save_detail_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_save_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法描述: 保存统计图查看明细列表字段配置
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/detail/data/saveQuery
        Request body: SaveQueryArg (required)
        Response: void
        Operation ID: fs_bi_stat.stat_base.save_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.save_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_save_user_segment(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.saveUserSegment
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/userSegment/save
        Request body: QueryStatDetailInfoArg (required)
        Response: BiUserSegmentResult
        Operation ID: fs_bi_stat.stat_base.save_user_segment
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.save_user_segment",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_base_update_user_segment(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBaseController.updateUserSegment
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/userSegment/update
        Request body: UpdateUserSegmentArg (required)
        Response: UserSegmentResult
        Operation ID: fs_bi_stat.stat_base.update_user_segment
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_base.update_user_segment",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_business_view_data_query_report_data(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatBusinessViewDataController.queryReportData
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/business/data/query
        Request body: QueryChartDataArg (required)
        Response: QueryChartData.Result
        Operation ID: fs_bi_stat.stat_business_view_data.query_report_data
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_business_view_data.query_report_data",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_calc_field_delete_calc_field(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 物理删除计算字段
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/calcField/delete
        Request body: DelCalcFieldArg (required)
        Response: DelCalcFieldResult
        Operation ID: fs_bi_stat.stat_calc_field.delete_calc_field
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_calc_field.delete_calc_field",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_calc_field_grammar_check(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 计算字段语法校验
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/calcField/grammarCheck
        Request body: GrammarCheckArg (required)
        Response: GrammarCheckResult
        Operation ID: fs_bi_stat.stat_calc_field.grammar_check
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_calc_field.grammar_check",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_calc_field_save_calc_field(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新增或者更新计算字段
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/calcField/save
        Request body: SaveCalcFieldArg (required)
        Response: SaveCalcFieldResult
        Operation ID: fs_bi_stat.stat_calc_field.save_calc_field
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_calc_field.save_calc_field",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_batch_get_filters_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 上边的单个方法简单包了一层给crm调用
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/filters/batchGetFiltersResult
        Request body: BatchStatFilterArg (required)
        Response: BatchStatFilterResult
        Operation ID: fs_bi_stat.stat_edit.batch_get_filters_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.batch_get_filters_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_creat_stat_view(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.creatStatView
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/creatStatView
        Request body: CreateStatViewArg (required)
        Response: CreateStatViewResult
        Operation ID: fs_bi_stat.stat_edit.creat_stat_view
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.creat_stat_view",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_all_dim_list_by_id_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getAllDimListByIdResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/allDimListById/query
        Request body: QueryChartDataArg (required)
        Response: ObjectRelationResult
        Operation ID: fs_bi_stat.stat_edit.get_all_dim_list_by_id_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_all_dim_list_by_id_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_chart_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getChartConfig
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/chartConfig/query
        Request body: StatChartConfArg (required)
        Response: StatChartConfResult
        Operation ID: fs_bi_stat.stat_edit.get_chart_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_chart_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_filters_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getFiltersResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/filters/getFiltersResult
        Request body: StatFilterArg (required)
        Response: StatFilterResult
        Operation ID: fs_bi_stat.stat_edit.get_filters_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_filters_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_insight_filter_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getInsightFilterList
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/filters/getInsightFilterList
        Request body: InsightFilterArg (required)
        Response: InsightFilterResult
        Operation ID: fs_bi_stat.stat_edit.get_insight_filter_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_insight_filter_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_local_filter(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getLocalFilter
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/filters/getLocalFilter
        Request body: StatLocalFilterArg (required)
        Response: StatLocalFilterResult
        Operation ID: fs_bi_stat.stat_edit.get_local_filter
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_local_filter",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_obj_relation_by_obj_name_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getObjRelationByObjNameResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/objRelationByObjName/query
        Request body: QueryChartDataArg (required)
        Response: ObjectRelationByObjNameResult
        Operation ID: fs_bi_stat.stat_edit.get_obj_relation_by_obj_name_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_obj_relation_by_obj_name_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_get_obj_relation_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.getObjRelationResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/objRelation/query
        Request body: QueryChartDataArg (required)
        Response: ObjectRelationResult
        Operation ID: fs_bi_stat.stat_edit.get_obj_relation_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.get_obj_relation_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_simple_data_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditSimpleController.dataQuery
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/simple/data/query
        Request body: QueryStatDataSimpleArg (required)
        Response: List<QueryChartDataResult>
        Operation ID: fs_bi_stat.stat_edit_simple.data_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit_simple.data_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_simple_data_query_account_level(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditSimpleController.dataQueryAccountLevel
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/simple/query/accountlevel
        Request body: QueryStatDataSimpleArg (required)
        Response: List<QueryChartDataResult>
        Operation ID: fs_bi_stat.stat_edit_simple.data_query_account_level
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit_simple.data_query_account_level",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_simple_get_all_dim_list_by_id_result(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditSimpleController.getAllDimListByIdResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/simple/getAllAgg/query
        Request body: QueryChartDataArg (required)
        Response: ObjectRelationResult
        Operation ID: fs_bi_stat.stat_edit_simple.get_all_dim_list_by_id_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit_simple.get_all_dim_list_by_id_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_update_all_dim_hide_status(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.updateAllDimHideStatus
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/allDimHideStatus/update
        Request body: UpdateAllDimHideStatusArg (required)
        Response: UpdateAllDimHideStatusResult
        Operation ID: fs_bi_stat.stat_edit.update_all_dim_hide_status
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.update_all_dim_hide_status",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_edit_update_stat_view(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatEditController.updateStatView
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/updateStatView
        Request body: UpdateStatViewArg (required)
        Response: UpdateStatViewResult
        Operation ID: fs_bi_stat.stat_edit.update_stat_view
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_edit.update_stat_view",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_metadata_query_test_query_test(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatMetadataQueryTestController.queryTest
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/query/test
        Request body: StatMetadataQueryTestArg (required)
        Response: StatMetadataQueryResult
        Operation ID: fs_bi_stat.stat_metadata_query_test.query_test
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_metadata_query_test.query_test",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_ratio_confirmation_ratio_date(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法描述: 获取可使用的同环比方法
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/ratio/confirmationDate/query
        Request body: ConfirmationRatioDateArg (required)
        Response: ConfirmationRatioDateResult
        Operation ID: fs_bi_stat.stat_ratio.confirmation_ratio_date
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_ratio.confirmation_ratio_date",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_ratio_query_ratio_filter_type(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 方法描述: 获取可使用的同环比方法
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/ratio/ratioFilterType/query
        Request body: QueryRatioFilterTypeArg (required)
        Response: QueryRatioFilterTypeResult
        Operation ID: fs_bi_stat.stat_ratio.query_ratio_filter_type
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_ratio.query_ratio_filter_type",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_add_new_schema(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 选择主题对象，新建主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/newSchema/add
        Request body: StatSchemaBO (required)
        Response: AddNewSchemaResult
        Operation ID: fs_bi_stat.stat_schema.add_new_schema
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.add_new_schema",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_add_new_schema_sql(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatSchemaController.addNewSchemaSql
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/newSchema/sql
        Request body: List<StatSchemaBO> (required)
        Response: String
        Operation ID: fs_bi_stat.stat_schema.add_new_schema_sql
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.add_new_schema_sql",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_batch_update_schema_status(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 批量开启/停用/删除/停用并删除 主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schemaStatus/batchUpdate
        Request body: BatchStatSchemaArg (required)
        Response: UpdateSchemaStatusResult
        Operation ID: fs_bi_stat.stat_schema.batch_update_schema_status
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.batch_update_schema_status",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_delete_schema(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 删除主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schema/delete
        Request body: StatSchemaArg (required)
        Response: DeleteSchemaResult
        Operation ID: fs_bi_stat.stat_schema.delete_schema
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.delete_schema",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_get_all_schema(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询全部主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/allSchema/query
        Request body: object (optional)
        Response: List<StatSchemaDO>
        Operation ID: fs_bi_stat.stat_schema.get_all_schema
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.get_all_schema",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_get_fields_by_schema_id(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询主题字段（维度 基础指标 聚合指标）
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/fieldsBySchemaId/query
        Request body: StatSchemaArg (required)
        Response: QueryStatFieldsResult
        Operation ID: fs_bi_stat.stat_schema.get_fields_by_schema_id
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.get_fields_by_schema_id",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_get_insight_lookup_relation_field_list(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 指标字段说明
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/insight/query
        Request body: object (optional)
        Response: PaasLookup.Result
        Operation ID: fs_bi_stat.stat_schema.get_insight_lookup_relation_field_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.get_insight_lookup_relation_field_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_all_object_list(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询所有的对象（在主题列表上面的对象列表处使用）
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/allObjectList/query
        Request body: object (optional)
        Response: QueryAllObjectListResult
        Operation ID: fs_bi_stat.stat_schema.query_all_object_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_all_object_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_field_detail(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 指标字段说明
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/fieldDetail/query
        Request body: AggRuleIdArg (required)
        Response: List<AggRuleArg>
        Operation ID: fs_bi_stat.stat_schema.query_field_detail
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_field_detail",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_field_topology(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 指标字段图
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/fieldTopology/query
        Request body: AggRuleIdArg (required)
        Response: ResponseResult
        Operation ID: fs_bi_stat.stat_schema.query_field_topology
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_field_topology",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_goal_rule_type(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 根据// 0 模板 1 视图 2 空模板 id判断对应主题是否需要选规则
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/goalType/query
        Request body: QueryGoalRuleTypeArg (required)
        Response: GoalRuleTypeResult
        Operation ID: fs_bi_stat.stat_schema.query_goal_rule_type
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_goal_rule_type",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_object_list(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 查询没有开启统计分析的对象列表（新建主题页面的对象列表处使用）
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/objectList/query
        Request body: object (optional)
        Response: QueryObjectListResult
        Operation ID: fs_bi_stat.stat_schema.query_object_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_object_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_query_schema_list(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 主题列表页面根据条件查询主题列表
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schemaList/query
        Request body: QueryStatSchemaArg (required)
        Response: QuerySchemaListResult
        Operation ID: fs_bi_stat.stat_schema.query_schema_list
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.query_schema_list",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_sync_entry(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 指标字段说明
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/syncEntry
        Request body: object (optional)
        Response: void
        Operation ID: fs_bi_stat.stat_schema.sync_entry
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.sync_entry",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_update_schema(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatSchemaController.updateSchema
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schema/update
        Request body: StatSchemaArg (required)
        Response: UpdateSchemaResult
        Operation ID: fs_bi_stat.stat_schema.update_schema
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.update_schema",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_update_schema_status(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 开启/停用 主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schemaStatus/update
        Request body: StatSchemaArg (required)
        Response: UpdateSchemaStatusResult
        Operation ID: fs_bi_stat.stat_schema.update_schema_status
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.update_schema_status",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_validate_view(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 校验对象
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/validateView
        Request body: ValidateViewArg (required)
        Response: ValidateViewResult
        Operation ID: fs_bi_stat.stat_schema.validate_view
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.validate_view",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_schema_verify_schema_limit_count(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 启用主题分析时判断当前已开启分析的主题数是否超过限制
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/schema/schemaLimitCount/verify
        Request body: object (optional)
        Response: VerifySchemaListCountResult
        Operation ID: fs_bi_stat.stat_schema.verify_schema_limit_count
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_schema.verify_schema_limit_count",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_template_get_obj_relation_result(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatTemplateController.getObjRelationResult
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/template/getDomainTemplateResult
        Request body: object (optional)
        Response: DomainTemplateResult
        Operation ID: fs_bi_stat.stat_template.get_obj_relation_result
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_template.get_obj_relation_result",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def stat_template_view_to_template(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: StatTemplateController.viewToTemplate
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/template/viewToTemplate
        Request body: ViewToTemplateArg (required)
        Response: String
        Operation ID: fs_bi_stat.stat_template.view_to_template
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.stat_template.view_to_template",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_add_pre_schemas(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 新增系统库的预置主题
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/PreSchema/add
        Request body: AddPreSchemaArg (required)
        Response: int
        Operation ID: fs_bi_stat.sync_pre_schema.add_pre_schemas
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.add_pre_schemas",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_brush_customer_schema74203(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SyncPreSchemaController.brushCustomerSchema74203
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/bi/pg/brushCustomerSchema74203/brush
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.sync_pre_schema.brush_customer_schema74203
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.brush_customer_schema74203",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_brush_customer_schema_for_area(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SyncPreSchemaController.brushCustomerSchemaForArea
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/bi/pg/customerschemaforarea/brush
        Request body: ExecuteSqlArg (required)
        Response: String
        Operation ID: fs_bi_stat.sync_pre_schema.brush_customer_schema_for_area
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.brush_customer_schema_for_area",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_execute_bi_pg(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SyncPreSchemaController.executeBiPg
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/bi/pg/sql/execute
        Request body: ExecuteSqlArg (required)
        Response: String
        Operation ID: fs_bi_stat.sync_pre_schema.execute_bi_pg
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.execute_bi_pg",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_execute_bi_system_pg(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: SyncPreSchemaController.executeBiSystemPg
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/bisystem/sql/execute
        Request body: ExecuteSqlArg (required)
        Response: String
        Operation ID: fs_bi_stat.sync_pre_schema.execute_bi_system_pg
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.execute_bi_system_pg",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def sync_pre_schema_sync_pre_schemas(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 主题列表页面根据条件查询主题列表
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/stat/preschema/sync
        Request body: SyncPreSchemaArg (required)
        Response: RestBaseResult
        Operation ID: fs_bi_stat.sync_pre_schema.sync_pre_schemas
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.sync_pre_schema.sync_pre_schemas",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_clear_all_view_cache(self, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.clearAllViewCache
        Route: GET /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/clearAllViewCache
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.view_data_query_api.clear_all_view_cache
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.clear_all_view_cache",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_clear_view_cache_by_key(self, ei: Any, viewId: Any, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.clearViewCacheByKey
        Route: GET /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/clearCache/{ei}/{viewId}
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.view_data_query_api.clear_view_cache_by_key
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.clear_view_cache_by_key",
            body=body,
            path_params={"ei": ei, "viewId": viewId},
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_get_chart_config(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.getChartConfig
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/chartConfig/query
        Request body: ChartConfigArg (required)
        Response: ApiResult<StatChartConfResult>
        Operation ID: fs_bi_stat.view_data_query_api.get_chart_config
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.get_chart_config",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_get_perm(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.getPerm
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/perm/query
        Request body: PermArg (required)
        Response: ApiResult<Permission>
        Operation ID: fs_bi_stat.view_data_query_api.get_perm
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.get_perm",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_notice_change(self, ei: Any, viewId: Any, *, body: Any = None, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.noticeChange
        Route: GET /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/noticeChange/{ei}/{viewId}
        Request body: object (optional)
        Response: String
        Operation ID: fs_bi_stat.view_data_query_api.notice_change
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.notice_change",
            body=body,
            path_params={"ei": ei, "viewId": viewId},
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: ViewDataQueryApiController.query
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/data/query
        Request body: ViewDataQueryArg (required)
        Response: ApiResult<QueryChartDataResult>
        Operation ID: fs_bi_stat.view_data_query_api.query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )

    def view_data_query_api_sync_chart_query(self, body: Any, *, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> ApiResponse:
        """
        Purpose: 给agent 驾驶舱解读 提供的接口
        Route: POST /FHH/EM1HBISTAT/fs-bi-stat/api/v1/stat/chart/query
        Request body: QueryChartFullArg (required)
        Response: ApiResult<QueryChartResult>
        Operation ID: fs_bi_stat.view_data_query_api.sync_chart_query
        """
        _params = dict(params or {})
        return self._invoker.call(
            "fs_bi_stat.view_data_query_api.sync_chart_query",
            body=body,
            path_params=None,
            params=_params or None,
            headers=headers,
        )
