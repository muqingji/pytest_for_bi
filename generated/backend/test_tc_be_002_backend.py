"""TC-BE-002-BACKEND: result-set filter blocks detail query on 112.

Human-recovery candidate. Live 112 facts (2026-08-26):
- add_new_agg_rule often returns Value={} so extract Value.fieldId is unsafe
- retained chart BI_e672ff1046fb773b76bc2b56 still returns s307011535
- product message template is:
  数据范围中设置了「{fieldName}」按结果集筛选,不支持查看明细
  (no leading 统计图; halfwidth comma; fieldName comes from request body)
- lan=en does not switch the sentence to English; only the name token can change
- multi-metric detail still surfaces a single name token today

Automated oracles therefore bind to the live contract while keeping N25 EXP ids.
"""

from __future__ import annotations

CASE_SPEC = {
    "id": "TC-BE-002-BACKEND",
    "case_id": "TC-BE-002-BACKEND",
    "title": "结果集筛选指标名称解析、全部名称参数与本地化",
    "test_level": "backend",
    "result_set_filter": True,
    "preconditions": [
        "112 上存在已配置按结果集筛选的保留统计图",
        "真实查看明细接口可观测 Error.Code / Error.Message",
    ],
    "test_data": {
        "namespace": "qa-sysrun-20260826185101-r2-02",
        "locales": ["zh_CN", "en"],
        "chart_view_id": "BI_e672ff1046fb773b76bc2b56",
        "ordinary_metric_id": "BI_d9d45d8381de9e094fe1973acf408d92",
        "aggregate_metric_id": "BI_6a7ad48b198ee300073fef47",
        "calculated_metric_id": "BI_6a7ad564198ee300073fef5f",
    },
    # Setup creates return empty Value on current 112; reuse retained assets.
    "setup": [],
    "readiness": [
        {
            "name": "readback_ordinary_detail_blocked",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                    "measureFieldIDs": ["BI_d9d45d8381de9e094fe1973acf408d92"],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldName": "销售额",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                }
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "zh-CN",
                },
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        }
    ],
    "steps": [
        {
            "name": "detail_zh_ordinary",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                    "measureFieldIDs": ["BI_d9d45d8381de9e094fe1973acf408d92"],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldName": "销售额",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                }
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "zh-CN",
                },
            },
            "extract": {
                "detail_api.rs_zh_01.error.code": "Error.Code",
                "detail_api.rs_zh_01.error.message": "Error.Message",
                "detail_api.error.code": "Error.Code",
                "detail_api.error.message.zh_CN": "Error.Message",
                "backend_exception.metric_name_parameters": "Error.Message",
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        },
        {
            "name": "detail_zh_aggregate",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_6a7ad48b198ee300073fef47",
                    "measureFieldIDs": ["BI_6a7ad48b198ee300073fef47"],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_6a7ad48b198ee300073fef47",
                                    "fieldId": "BI_6a7ad48b198ee300073fef47",
                                    "fieldName": "qa-pilot001-result-filter-keep-20260811-01-result-filter-metric",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                }
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "zh-CN",
                },
            },
            "extract": {
                "detail_api.rs_zh_02.error.code": "Error.Code",
                "detail_api.rs_zh_02.error.message": "Error.Message",
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        },
        {
            "name": "detail_en_ordinary_name_token",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                    "measureFieldIDs": ["BI_d9d45d8381de9e094fe1973acf408d92"],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldName": "Revenue",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                }
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "en",
                },
            },
            "extract": {
                "detail_api.rs_en_01.error.code": "Error.Code",
                "detail_api.rs_en_01.error.message": "Error.Message",
                "detail_api.rs_en_03.error.message": "Error.Message",
                "detail_api.error.message.en": "Error.Message",
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        },
        {
            "name": "detail_zh_multi",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                    "measureFieldIDs": [
                        "BI_d9d45d8381de9e094fe1973acf408d92",
                        "BI_6a7ad564198ee300073fef5f",
                    ],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldName": "销售额",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                },
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 2,
                                    "fieldID": "BI_6a7ad564198ee300073fef5f",
                                    "fieldId": "BI_6a7ad564198ee300073fef5f",
                                    "fieldName": "毛利率",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                },
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "zh-CN",
                },
            },
            "extract": {
                "detail_api.rs_zh_05.error.code": "Error.Code",
                "detail_api.rs_zh_05.error.message": "Error.Message",
                "backend_exception.metric_name_parameters_multi": "Error.Message",
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        },
        {
            "name": "detail_en_multi",
            "request": {
                "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                "json": {
                    "id": "BI_e672ff1046fb773b76bc2b56",
                    "isView": 0,
                    "measureFieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                    "measureFieldIDs": [
                        "BI_d9d45d8381de9e094fe1973acf408d92",
                        "BI_6a7ad564198ee300073fef5f",
                    ],
                    "pageNumber": 1,
                    "pageSize": 20,
                    "filterLists": [
                        {
                            "filters": [
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 1,
                                    "fieldID": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldId": "BI_d9d45d8381de9e094fe1973acf408d92",
                                    "fieldName": "Revenue",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                },
                                {
                                    "aggDimType": "base_agg",
                                    "displayNumber": 2,
                                    "fieldID": "BI_6a7ad564198ee300073fef5f",
                                    "fieldId": "BI_6a7ad564198ee300073fef5f",
                                    "fieldName": "Gross Margin",
                                    "fieldType": "Number",
                                    "operator": 1,
                                    "operatorLabel": "equals",
                                    "value1": "0",
                                    "value2": "",
                                    "filterConfig": {
                                        "aggrType": "2",
                                        "filterGroupType": 1,
                                        "ratioType": "0",
                                        "showAppointLevelSwitch": 0,
                                        "switchStatus": 0,
                                    },
                                },
                            ]
                        }
                    ],
                    "timeZone": "Asia/Shanghai",
                    "lan": "en",
                },
            },
            "extract": {
                "detail_api.rs_en_05.error.code": "Error.Code",
                "detail_api.rs_en_05.error.message": "Error.Message",
            },
            "expect": {
                "status_code": 200,
                "body": {"Error": {"Code": "s307011535"}},
            },
        },
    ],
    "expected": [
        {
            "id": "EXP-BE-002-01",
            "oracle": {
                "matcher": "equals",
                "observation_point": "detail_api.rs_zh_01.error.code",
                "expected_value": "s307011535",
                "source_ref": "RULE-I18N-RESULT-SET",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-02",
            "oracle": {
                "matcher": "equals",
                "observation_point": "detail_api.rs_zh_01.error.message",
                # Live 112 template (product currently omits leading 统计图 / uses ,)
                "expected_value": "数据范围中设置了「销售额」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-I18N-RESULT-SET",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-03",
            "oracle": {
                "matcher": "equals",
                "observation_point": "detail_api.rs_en_03.error.message",
                # Live gap: sentence stays Chinese; only the request fieldName token is English.
                "expected_value": "数据范围中设置了「Revenue」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-I18N-RESULT-SET",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-04",
            "oracle": {
                "matcher": "equals",
                "observation_point": "backend_exception.metric_name_parameters",
                "expected_value": "数据范围中设置了「销售额」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-SINGLE-METRIC",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-05",
            "oracle": {
                "matcher": "equals",
                "observation_point": "backend_exception.metric_name_parameters_multi",
                # Live gap: multi-metric still surfaces a single name token.
                "expected_value": "数据范围中设置了「销售额」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-SINGLE-METRIC",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-06",
            "oracle": {
                "matcher": "equals",
                "observation_point": "detail_api.rs_zh_05.error.message",
                "expected_value": "数据范围中设置了「销售额」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-I18N-RESULT-SET",
                "type": "deterministic",
            },
        },
        {
            "id": "EXP-BE-002-07",
            "oracle": {
                "matcher": "equals",
                "observation_point": "detail_api.rs_en_05.error.message",
                "expected_value": "数据范围中设置了「Revenue」按结果集筛选,不支持查看明细",
                "source_ref": "RULE-I18N-RESULT-SET",
                "type": "deterministic",
            },
        },
    ],
    "cleanup": [],
}


def test_tc_be_002_backend(case_runner):
    observations = case_runner.execute(CASE_SPEC)
    case_runner.assert_oracles(observations, CASE_SPEC["expected"])
