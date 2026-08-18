G01 Decision Protocol | 1.0
Request Hash | sha256:551299f911e7851deb71fe0446c571729632bdc2f0e75468454961ce266eb60a
Decision | approved
Overall Reason | QA Owner 已按冻结需求逐项确认测试口径；实现与证据缺口保留为必测风险。本决定仅用于 pilot_test_design_only，不授予生产发布权限。
Test Rules | {"compatibility":{"failure_response_shape":"unchanged_except_approved_codes_messages_and_parameters","historical_charts_and_tables":"evaluate_in_place_without_migration","non_target_error_codes":"unchanged","success_response":"unchanged"},"custom_dimension":{"covered_locations":["dimension","data_range","drill_field"],"error_key":"CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED","preserve_existing_detection_order":true},"dynamic_relation":{"error_key":"DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED","scope":"query_actual_what_and_what_list_object_and_field_scope_when_building_test_data"},"entry_consistency":{"assertions":["same_backend_reason","same_error_code","same_locale_message","same_metric_parameters"],"joined_table_copy":"same_copy_as_chart","mobile_equivalence":"query_runtime_route_and_compare_api_and_parameters_first","required_entries":["web_chart","web_joined_table","mobile_chart","mobile_joined_table"]},"localization":{"errors":[{"code":"s307011534","en":"Custom dimension fields are used in the dimension or data range. Details view is not supported.","key":"CUSTOM_DIMENSION_DETAIL_REASON_UNSUPPORTED","parameters":[],"zh_CN":"维度或数据范围中使用了自定义维度字段，暂不支持查看明细"},{"code":"s307011535","en":"The chart data range uses Metric Name with result set filtering. Details view is not supported.","key":"RESULT_SET_FILTER_DETAIL_UNSUPPORTED","parameters":["all_metric_display_names"],"zh_CN":"统计图数据范围中设置了「指标名称」按结果集筛选，不支持查看明细"},{"code":"s307011536","en":"Metrics created based on multiple relationships do not support Details view.","key":"MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED","parameters":[],"zh_CN":"基于多关联关系创建的统计指标，暂不支持查看明细"},{"code":"s307011537","en":"Metrics created based on dynamic relationships do not support Details view.","key":"DYNAMIC_RELATION_METRIC_DETAIL_UNSUPPORTED","parameters":[],"zh_CN":"基于动态关联关系创建的统计指标，不支持查看明细"}],"locale_source":"request_current_locale","parameter_transport":"actual_business_contract"},"metric_name":{"multiple_metrics":"display_all_metric_names","resolution_order":["Filter.fieldName","field_metadata_by_fieldId","current_locale_dynamic_display_name"],"unresolved_name":"preserve_actual_business_response"},"multi_relation":{"error_key":"MULTI_RELATION_METRIC_DETAIL_UNSUPPORTED","successful_existing_relation_resolution":"must_remain_successful"},"multiple_reasons":{"concatenate":false,"fixed_business_reason_priority":false,"message_count":1,"permission_errors":"preserve_existing_behavior","selection":"any_one_of_the_actually_matched_specialized_messages"},"permission":{"behavior":"preserve_actual_business_behavior","metric_name_visibility":"must_not_bypass_existing_permissions"}}
Issue ID | Disposition | Rationale | Owner
--- | --- | --- | ---
A02:AMB-001 | confirmed | 多原因同时命中时只展示任一条实际命中的专用提示，不拼接。 | muqj11262
A02:AMB-002 | confirmed | 多个受限指标展示全部实际指标名称。 | muqj11262
A02:AMB-003 | confirmed | 展示载体沿用现有端行为，本需求验证错误码、文案与阻止进入明细。 | muqj11262
A02:AMB-004 | confirmed | 本需求只新增四类专用提示，其他场景保持原行为。 | muqj11262
A02:AMB-005 | confirmed | 权限逻辑保持原行为，不得绕过既有权限。 | muqj11262
A02:AMB-006 | confirmed | 按结构化 Test Rules 冻结中英文文案。 | muqj11262
A02:AMB-007 | confirmed | 指标名称按实时业务响应验证，禁止测试伪造替代值。 | muqj11262
A02:AMB-008 | confirmed | what 和 what-list 范围在构造数据时实时查询并保留证据。 | muqj11262
A03:BI-001 | confirmed | 自定义维度覆盖维度、数据范围及实际下钻字段判定。 | muqj11262
A03:BI-002 | confirmed | 统计图与拼表沿用同一后端原因、错误码和 locale 文案。 | muqj11262
A03:BI-003 | resolved_upstream | 代码已登记四个独立错误码；平台模板仍须通过执行证据验证。 | muqj11262
A03:BI-004 | confirmed | 占位符和参数顺序作为契约与执行测试义务，不在 Gate 中假定通过。 | muqj11262
A03:BI-005 | confirmed | 稳定标识必须来自目标环境实时元数据，缺失时测试不得伪造。 | muqj11262
A03:BI-006 | confirmed | 不冻结内部优先级，只要求返回一条实际命中的完整专用提示。 | muqj11262
A06:FND-001 | confirmed | 最终中英文渲染列为执行期必测风险。 | muqj11262
A06:FND-002 | confirmed | 实现覆盖下钻字段，测试必须单独覆盖并记录实际文案。 | muqj11262
A06:FND-003 | confirmed | 名称解析、空值和 locale 参数列为契约负向测试。 | muqj11262
A06:FND-004 | confirmed | 大于三节点实现偏差列为高风险边界测试，不视为已符合需求。 | muqj11262
A06:FND-005 | confirmed | what/what-list 判定范围列为高风险正反向测试。 | muqj11262
A06:FND-006 | confirmed | 统计图、拼表、Web、移动一致性作为必测入口矩阵。 | muqj11262
A06:FND-007 | confirmed | 非目标错误码和消息必须保持不变，列为回归测试。 | muqj11262
A06:FND-008 | confirmed | 多原因只要求一条实际命中的专用提示，不假定业务优先级。 | muqj11262
A06:FND-009 | confirmed | 中文与英文均按冻结模板执行。 | muqj11262
A06:FND-010 | confirmed | 自定义维度与结果集筛选缺失覆盖由本次新增 Case 补齐。 | muqj11262
A06:FND-011 | confirmed | 多指标、空值、不可见、超长和特殊字符均纳入名称矩阵。 | muqj11262
