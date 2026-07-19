import os
import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

import local_db as db
from app.services import ai_orchestrator
from app.services import rental_dispatcher
from app.services.ai_memory import build_memory_layers
from app.services.business_knowledge import search_business_knowledge
from app.services.skill_executor import _contract_create_form_action, execute_tool


@contextmanager
def mysql_test_transaction():
    engine = db._mysql_engine()
    raw = engine.raw_connection()
    original_conn = db._conn
    original_cache_get = db._cache_get
    original_cache_set = db._cache_set
    original_clear_cache = db.clear_rental_cache

    def _cache_get(_key):
        return db._CACHE_MISS

    def _cache_set(_key, _value, ttl=None):
        return None

    def _test_conn():
        conn = db._MySQLConnection(raw, pooled=False)
        conn.commit = lambda: None
        conn.close = lambda: None
        return conn

    db._conn = _test_conn
    db._cache_get = _cache_get
    db._cache_set = _cache_set
    db.clear_rental_cache = lambda: None
    try:
        yield
    finally:
        try:
            raw.rollback()
        except Exception:
            pass
        try:
            raw.close()
        except Exception:
            pass
        db._conn = original_conn
        db._cache_get = original_cache_get
        db._cache_set = original_cache_set
        db.clear_rental_cache = original_clear_cache


BUILDINGS = [
    {"id": 2, "name": "石潭布"},
    {"id": 3, "name": "益民路"},
]


class ContractOrchestrationTests(unittest.TestCase):
    def test_greeting_uses_friendly_reply(self):
        result = ai_orchestrator._chat_linear({"prompt": "你好", "history": [], "session_context": {}})
        self.assertIn("你好，我在", result["reply"])
        self.assertIn("查某个月水电表", result["reply"])

    def test_bill_create_room_followup_inherits_context(self):
        data = {
            "prompt": "202呢",
            "history": [{"role": "user", "content": "石潭布201生成7月账单"}],
            "session_context": {
                "active_workflow": "bill_create",
                "building_id": 2,
                "building_name": "石潭布",
                "workflow_state": {"name": "bill_create", "fields": {"month": "2026-07"}},
            },
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._bill_create_followup_args(data)

        self.assertEqual(args["building_id"], 2)
        self.assertEqual(args["building_name"], "石潭布")
        self.assertEqual(args["room_number"], "202")
        self.assertEqual(args["month"], "2026-07")

    def test_bill_create_room_followup_returns_pending_bill_image(self):
        data = {
            "prompt": "202呢",
            "history": [{"role": "user", "content": "石潭布201生成7月账单"}],
            "session_context": {
                "active_workflow": "bill_create",
                "building_id": 2,
                "building_name": "石潭布",
                "workflow_state": {"name": "bill_create", "fields": {"month": "2026-07"}},
            },
        }
        pending_action = {
            "id": "bill-202",
            "type": "create_bill",
            "label": "保存202 2026-07 账单",
            "tool": "confirm_create_bill",
            "args": {"contract_id": 7, "month": "2026-07", "draft": {}},
            "preview": {"room_number": "202", "month": "2026-07"},
            "status": "pending",
        }
        receipt_image = {
            "image_type": "bill_receipt",
            "receipt": {
                "no": "202607-202",
                "title": "房租及费用收据",
                "room_number": "202",
                "tenant_name": "张培英",
                "month": "2026-07",
                "items": [],
                "total_amount": 874,
            },
        }
        tool_result = {
            "ok": True,
            "tool": "bill_create_from_ai",
            "data": {
                "success": True,
                "requires_confirmation": True,
                "pending_action": pending_action,
                "receipt_image": receipt_image,
            },
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS), \
             patch.object(ai_orchestrator, "execute_tool", return_value=tool_result) as execute_mock, \
             patch.object(ai_orchestrator, "search_skills", return_value=[]), \
             patch.object(ai_orchestrator, "_detect_intent", return_value={
                 "name": "bill_create",
                 "workflow": "bill_create",
                 "confidence": 1.0,
                 "fields": {"month": "2026-07"},
             }):
            result = ai_orchestrator._bill_create_followup_fallback(data)

        execute_mock.assert_called_once_with("bill_create_from_ai", {
            "building_id": 2,
            "building_name": "石潭布",
            "room_number": "202",
            "month": "2026-07",
        })
        self.assertEqual(result["pending_actions"][0]["id"], "bill-202")
        self.assertEqual(result["bill_images"][0]["receipt"]["room_number"], "202")

    def test_meter_history_backfill_text_confirms_pending_action(self):
        self.assertTrue(ai_orchestrator._looks_like_pending_action_text_confirm("把6月底的读数补录到历史记录"))

    def test_meter_reading_query_extracts_room_building_and_month(self):
        data = {"prompt": "6月份 石潭布302房的水电表读数是多少", "session_context": {}}
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._meter_reading_query_args(data)

        self.assertEqual(args["building_id"], 2)
        self.assertEqual(args["room_number"], "302")
        self.assertEqual(args["month"], "2026-06")
        self.assertNotIn("meter_type", args)

    def test_meter_reading_query_response_reports_existing_values(self):
        data = {"prompt": "6月份 石潭布302房的水电表读数是多少", "session_context": {}}
        tool_result = {
            "ok": True,
            "tool": "meter_reading_get_room_reading",
            "data": {
                "month": "2026-06",
                "found": True,
                "rows": [
                    {
                        "meter_type": "water",
                        "building": "石潭布",
                        "room_number": "302",
                        "reading": 1126.0,
                        "previous_reading": 0.0,
                        "previous_date": "",
                    },
                    {
                        "meter_type": "electric",
                        "building": "石潭布",
                        "room_number": "302",
                        "reading": 7758.0,
                        "previous_reading": 0.0,
                        "previous_date": "",
                    },
                ],
            },
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS), \
             patch.object(ai_orchestrator, "execute_tool", return_value=tool_result) as execute_mock, \
             patch.object(ai_orchestrator, "_detect_intent", return_value={
                 "name": "meter_reading",
                 "workflow": "meter_reading",
                 "confidence": 1.0,
                 "fields": {"month": "2026-06", "room_number": "302", "building_id": 2},
             }):
            result = ai_orchestrator._meter_reading_query_response(data)

        execute_mock.assert_called_once_with("meter_reading_get_room_reading", {
            "room_number": "302",
            "month": "2026-06",
            "building_id": 2,
        })
        self.assertIn("水表：1126", result["reply"])
        self.assertIn("电表：7758", result["reply"])
        self.assertEqual(result["pending_actions"], [])

    def test_colloquial_contract_request_extracts_building_and_room(self):
        prompt = "石潭布302帮我建个合同"
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({"prompt": prompt})
            should_fallback = ai_orchestrator._should_fallback_contract_create({"prompt": prompt})

        self.assertTrue(should_fallback)
        self.assertEqual(args["building_id"], 2)
        self.assertEqual(args["building_name"], "石潭布")
        self.assertEqual(args["room_number"], "302")

    def test_initial_room_request_does_not_guess_building_from_filler_words(self):
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({"prompt": "帮我201新建一个合同"})

        self.assertEqual(args["room_number"], "201")
        self.assertNotIn("building_name", args)

    def test_submitted_form_uses_room_number_instead_of_room_id(self):
        prompt = (
            "请根据以下表单内容新建合同：楼栋ID 2，楼栋名称 石潭布，"
            "房间ID 34，房间号 201，租户ID 5，租户姓名 张三，"
            "合同开始日期 2026-07-01，月租 800。"
        )
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({"prompt": prompt})

        self.assertEqual(args["room_id"], "34")
        self.assertEqual(args["room_number"], "201")

    def test_contract_continuation_reuses_building_and_new_room_only(self):
        context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
            "last_completed_workflow": "contract_create",
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({
                "prompt": "接着录202",
                "session_context": context,
            })

        self.assertEqual(args["building_id"], 2)
        self.assertEqual(args["building_name"], "石潭布")
        self.assertEqual(args["room_number"], "202")
        self.assertNotIn("tenant_name", args)

    def test_contract_continuation_extracts_colloquial_price_details(self):
        context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
            "contract_draft": {"building_id": 2, "building_name": "石潭布"},
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({
                "prompt": "301的房租是650，水4块 电1块 押一个月房租",
                "session_context": context,
            })

        self.assertEqual(args["building_id"], 2)
        self.assertEqual(args["building_name"], "石潭布")
        self.assertEqual(args["room_number"], "301")
        self.assertEqual(args["monthly_rent"], "650")
        self.assertEqual(args["water_unit_price"], "4")
        self.assertEqual(args["electric_unit_price"], "1")
        self.assertEqual(args["deposit"], "650")

    def test_contract_create_extracts_other_fee_details(self):
        context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({
                "prompt": "301月租650，网费50，卫生费20",
                "session_context": context,
            })

        self.assertEqual(args["room_number"], "301")
        self.assertEqual(args["other_fee_details"], [
            {"name": "网费", "amount": 50.0},
            {"name": "卫生费", "amount": 20.0},
        ])

    def test_contract_create_route_enters_graph_form_node(self):
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            route = ai_orchestrator._graph_route({
                "data": {"prompt": "石潭布302帮我建个合同"},
                "prompt": "石潭布302帮我建个合同",
            })

        self.assertEqual(route, "contract_form")

    def test_workflow_state_tracks_contract_missing_fields(self):
        context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
            "contract_draft": {"building_id": 2, "building_name": "石潭布"},
        }
        data = {
            "prompt": "301的房租是650，水4块 电1块 押一个月房租",
            "session_context": context,
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            intent = ai_orchestrator._detect_intent(data)
            state = ai_orchestrator._workflow_state_from_data(data, intent, [])

        self.assertEqual(intent["workflow"], "contract_create")
        self.assertEqual(state["name"], "contract_create")
        self.assertEqual(state["status"], "waiting_for_fields")
        self.assertEqual(state["fields"]["room_number"], "301")
        self.assertEqual(state["fields"]["monthly_rent"], "650")
        self.assertEqual(state["fields"]["deposit"], "650")
        self.assertIn("tenant_name", state["missing"])
        self.assertIn("start_date", state["missing"])

    def test_tool_plan_uses_workflow_specific_round_limit(self):
        plan = ai_orchestrator._tool_plan_for_intent({"workflow": "bill_create"}, {})

        self.assertEqual(plan["max_tool_rounds"], 4)
        self.assertIn("bill_create_from_ai", plan["allowed_tools"])

    def test_explicit_building_correction_overrides_old_draft(self):
        context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
            "contract_draft": {"building_id": 2, "building_name": "石潭布", "room_number": "201"},
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            args = ai_orchestrator._contract_create_args({
                "prompt": "是益民路的",
                "session_context": context,
            })

        self.assertEqual(args["building_id"], 3)
        self.assertEqual(args["building_name"], "益民路")
        self.assertEqual(args["room_number"], "201")

    def test_meter_intent_interrupts_contract_fallback(self):
        data = {
            "prompt": "先录一下另外一户202的水电表",
            "session_context": {"active_workflow": "contract_create", "building_name": "石潭布"},
        }
        self.assertFalse(ai_orchestrator._should_fallback_contract_create(data))

    def test_interrupted_contract_can_resume_after_meter_work(self):
        contract_context = {
            "active_workflow": "contract_create",
            "building_id": 2,
            "building_name": "石潭布",
            "room_number": "201",
            "contract_draft": {"building_id": 2, "building_name": "石潭布", "room_number": "201"},
        }
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            meter_context = ai_orchestrator._next_session_context({
                "prompt": "先录一下另外一户202的水电表",
                "session_context": contract_context,
            }, [])
            resumed_args = ai_orchestrator._contract_create_args({
                "prompt": "继续刚才的合同",
                "session_context": meter_context,
            })

        self.assertEqual(meter_context["active_workflow"], "meter_reading")
        self.assertEqual(meter_context["room_number"], "202")
        self.assertEqual(resumed_args["building_name"], "石潭布")
        self.assertEqual(resumed_args["room_number"], "201")

    def test_confirmed_contract_keeps_building_but_clears_household_draft(self):
        data = {
            "prompt": "",
            "session_context": {
                "active_workflow": "contract_create",
                "building_id": 2,
                "building_name": "石潭布",
                "room_number": "201",
                "contract_draft": {"room_number": "201", "tenant_name": "张三"},
            },
        }
        tool_results = [{
            "ok": True,
            "tool": "ai_pending_action_command",
            "data": {
                "success": True,
                "execution": {
                    "ok": True,
                    "tool": "confirm_create_contract",
                    "data": {
                        "success": True,
                        "contract": {"building_name": "石潭布", "room_number": "201"},
                    },
                },
            },
        }]
        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            context = ai_orchestrator._next_session_context(data, tool_results)

        self.assertEqual(context["building_id"], 2)
        self.assertEqual(context["building_name"], "石潭布")
        self.assertEqual(context["last_completed_workflow"], "contract_create")
        self.assertNotIn("room_number", context)
        self.assertNotIn("contract_draft", context)

    def test_each_contract_form_has_a_distinct_cache_identity(self):
        first = _contract_create_form_action({"building_name": "石潭布"})
        second = _contract_create_form_action({"building_name": "益民路"})
        self.assertNotEqual(first["id"], second["id"])
        self.assertTrue(first["id"].startswith("contract_create_form_"))


    def test_semantic_intent_switches_away_from_stale_contract_form(self):
        ai_orchestrator._SEMANTIC_INTENT_CACHE.clear()
        data = {
            "prompt": "他有合同了吗?",
            "session_context": {
                "active_workflow": "contract_create",
                "contract_draft": {"building_name": "石潭布", "room_number": "302"},
            },
        }
        semantic_result = ({
            "workflow": "query",
            "confidence": 0.92,
            "fields": {"room_number": "302"},
            "reason": "用户在询问已有合同",
        }, None)
        with patch.object(ai_orchestrator.ai_svc, "call_json", return_value=semantic_result) as call_json:
            intent = ai_orchestrator._detect_intent(data)
            route = ai_orchestrator._graph_route({
                "data": data,
                "prompt": data["prompt"],
                "pending_action_command": "",
            })

        self.assertEqual(intent["workflow"], "query")
        self.assertEqual(intent["source"], "ai_semantic")
        self.assertEqual(route, "normal_chat")
        self.assertEqual(call_json.call_count, 1)


class RoomMeterUpdateTests(unittest.TestCase):
    def test_room_update_from_ai_prepares_pending_action_and_confirms(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201", floor=1, status="rented", room_type="单间")

                prepared = execute_tool("room_update_from_ai", {
                    "room_id": room_id,
                    "new_room_number": "202",
                    "room_type": "一房一厅",
                    "floor": 3,
                    "status": "闲置",
                })["data"]
                confirmed = execute_tool("confirm_update_room", prepared["pending_action"]["args"])["data"]
                room = db.get_room(room_id)

        self.assertTrue(prepared["success"])
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(prepared["changes"]["room_number"], "202")
        self.assertTrue(confirmed["success"])
        self.assertEqual(room["room_number"], "202")
        self.assertEqual(room["room_type"], "一房一厅")
        self.assertEqual(room["floor"], 3)
        self.assertEqual(room["status"], "idle")

    def test_meter_update_from_ai_prepares_pending_action_and_confirms(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201")
                meter_id = db.add_meter(room_id, "water", meter_no="W-0001", init_reading=0)

                prepared = execute_tool("meter_update_from_ai", {
                    "meter_id": meter_id,
                    "meter_no": "W-1001",
                    "init_reading": 12.5,
                })["data"]
                confirmed = execute_tool("confirm_update_meter", prepared["pending_action"]["args"])["data"]
                meter = db.get_meter(meter_id)

        self.assertTrue(prepared["success"])
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(prepared["changes"]["meter_no"], "W-1001")
        self.assertTrue(confirmed["success"])
        self.assertEqual(meter["meter_no"], "W-1001")
        self.assertAlmostEqual(float(meter["init_reading"]), 12.5, places=4)

    def test_room_and_meter_update_prompts_route_to_dedicated_workflows(self):
        room_prompt = "把301房间户型改成一房一厅，楼层改成3楼"
        meter_prompt = "把301水表初始读数改成12.5，表号改成W-1001"

        with patch.object(ai_orchestrator.db, "get_buildings", return_value=BUILDINGS):
            room_intent = ai_orchestrator._detect_intent({"prompt": room_prompt, "session_context": {}})
            meter_intent = ai_orchestrator._detect_intent({"prompt": meter_prompt, "session_context": {}})
            room_plan = ai_orchestrator._tool_plan_for_intent(room_intent, {})
            meter_plan = ai_orchestrator._tool_plan_for_intent(meter_intent, {})
            system_prompt = ai_orchestrator._build_system_prompt(
                room_prompt,
                "",
                "",
                "",
                "",
                session_context={},
                intent=room_intent,
                tool_plan=room_plan,
            )

        self.assertEqual(room_intent["workflow"], "room_manage")
        self.assertEqual(meter_intent["workflow"], "meter_manage")
        self.assertIn("room_update_from_ai", room_plan["allowed_tools"])
        self.assertIn("meter_update_from_ai", meter_plan["allowed_tools"])
        self.assertIn("room_update_from_ai", system_prompt)
        self.assertIn("meter_update_from_ai", system_prompt)

    def test_room_update_detects_common_room_type_phrases(self):
        prompt = "测试楼栋201改成一房一厅"

        with patch.object(ai_orchestrator.db, "get_buildings", return_value=[{"id": 1, "name": "测试楼栋"}]):
            intent = ai_orchestrator._detect_intent({"prompt": prompt, "session_context": {}})
            fields = ai_orchestrator._extract_common_fields(prompt)

        self.assertEqual(intent["workflow"], "room_manage")
        self.assertEqual(fields["room_number"], "201")
        self.assertEqual(fields["room_type"], "一房一厅")

    def test_monthly_meter_status_exposes_photo_cards_and_dashboard_html(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201")
                tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
                contract_id = db.add_contract(
                    tenant_id,
                    room_id,
                    "2026-07-01",
                    monthly_rent=800,
                    water_price=4,
                    electric_price=1,
                )
                water_meter = db.add_meter(room_id, "water", meter_no="W-001", init_reading=10)
                electric_meter = db.add_meter(room_id, "electric", meter_no="E-001", init_reading=100)
                db.save_monthly_meter_reading(water_meter, "2026-07", 18, "data:image/png;base64,waterphoto", "water")
                db.save_monthly_meter_reading(electric_meter, "2026-07", 120, "data:image/png;base64,electricphoto", "electric")
                bill_id = db.add_bill(
                    contract_id,
                    "2026-07",
                    800,
                    water_fee=32,
                    electric_fee=20,
                    water_last=10,
                    water_curr=18,
                    electric_last=100,
                    electric_curr=120,
                )
                db.add_payment(bill_id, 852, "2026-07-18")

                meter_result = execute_tool("meter_reading_list_month_status", {
                    "month": "2026-07",
                    "building_id": building_id,
                })["data"]
                rent_result = execute_tool("rent_plan_list_month_status", {
                    "month": "2026-07",
                    "building_id": building_id,
                })["data"]
                final = ai_orchestrator._finalize_chat_response(
                    "",
                    {"prompt": "看看7月水电表和收益看板", "session_context": {"thread_id": "transient"}},
                    [{"ok": True, "tool": "meter_reading_list_month_status", "data": meter_result}],
                    [],
                )

        self.assertTrue(meter_result["analysis_cards"])
        self.assertEqual(meter_result["analysis_cards"][0]["type"], "photo_gallery")
        self.assertEqual(meter_result["analysis_cards"][0]["items"][0]["photo"], "data:image/png;base64,waterphoto")
        self.assertEqual(meter_result["analysis_cards"][1]["type"], "html")
        self.assertIn("水电分析看板", meter_result["analysis_cards"][1]["html"])
        self.assertEqual(rent_result["analysis_cards"][0]["type"], "html")
        self.assertIn("收益看板", rent_result["dashboard_html"])
        self.assertTrue(final["analysis_cards"])
        self.assertIn("分析看板", final["reply"])

    def test_room_meter_reading_exposes_photo_card_when_photo_exists(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201")
                tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
                db.add_contract(
                    tenant_id,
                    room_id,
                    "2026-07-01",
                    monthly_rent=800,
                    water_price=4,
                    electric_price=1,
                )
                water_meter = db.add_meter(room_id, "water", meter_no="W-001", init_reading=10)
                db.save_monthly_meter_reading(water_meter, "2026-07", 18, "data:image/png;base64,waterphoto", "water")

                room_result = execute_tool("meter_reading_get_room_reading", {
                    "room_number": "201",
                    "meter_type": "water",
                    "month": "2026-07",
                    "building_id": building_id,
                })["data"]

        self.assertTrue(room_result["found"])
        self.assertTrue(room_result["analysis_cards"])
        self.assertEqual(room_result["analysis_cards"][0]["type"], "photo_gallery")
        self.assertEqual(room_result["analysis_cards"][0]["items"][0]["photo"], "data:image/png;base64,waterphoto")


class ContractPersistenceTests(unittest.TestCase):
    def test_ai_thread_state_and_trace_persist_in_local_db(self):
        with mysql_test_transaction():
                db.init()
                db.save_ai_thread_state("thread-test", {"session_context": {"active_workflow": "contract_create"}})
                db.append_ai_trace("thread-test", "route", {"next": "contract_form"})

                state = db.load_ai_thread_state("thread-test")
                traces = db.load_ai_trace("thread-test")

        self.assertEqual(state["session_context"]["active_workflow"], "contract_create")
        self.assertEqual(traces[0]["event"], "route")
        self.assertEqual(traces[0]["payload"]["next"], "contract_form")

    def test_contract_payload_accepts_frontend_unit_price_fields(self):
        with patch.object(rental_dispatcher.db, "get_contract", return_value={}):
            payload = rental_dispatcher._contract_payload({
                "water_unit_price": 4.5,
                "electric_unit_price": 1.2,
            })

        self.assertEqual(payload["water_price"], 4.5)
        self.assertEqual(payload["electric_price"], 1.2)

    def test_active_contract_marks_room_as_rented(self):
        with mysql_test_transaction():
            db.init()
            building_id = db.add_building("测试楼栋")
            room_id = db.add_room(building_id, "201")
            tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
            db.add_contract(tenant_id, room_id, "2026-07-01", monthly_rent=800)
            self.assertEqual(db.get_room(room_id)["status"], "rented")

    def test_contract_queries_include_room_type(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "301", room_type="商铺")
                tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
                contract_id = db.add_contract(tenant_id, room_id, "2026-07-01", monthly_rent=1200)

                contract = db.get_contract(contract_id)
                contracts = db.get_contracts(True, building_id)

        self.assertEqual(contract["room_type"], "商铺")
        self.assertEqual(contracts[0]["room_type"], "商铺")

    def test_ai_contract_create_prepares_new_tenant_until_confirmed(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                db.add_room(building_id, "302", room_type="一房一厅")

                prepared = execute_tool("contract_create_from_ai", {
                    "building_id": building_id,
                    "room_number": "302",
                    "tenant_name": "新租客",
                    "tenant_phone": "13800000000",
                    "start_date": "2026-07-01",
                    "monthly_rent": 900,
                })["data"]
                tenants_before_confirm = db.get_tenants(True, building_id)
                confirmed = execute_tool(
                    "confirm_create_contract",
                    prepared["pending_action"]["args"],
                )["data"]
                tenant = db.get_tenant(confirmed["contract"]["tenant_id"])

        self.assertTrue(prepared["success"])
        self.assertTrue(prepared["requires_confirmation"])
        self.assertEqual(tenants_before_confirm, [])
        self.assertTrue(confirmed["success"])
        self.assertEqual(confirmed["contract"]["tenant_name"], "新租客")
        self.assertEqual(confirmed["contract"]["room_type"], "一房一厅")
        self.assertEqual(tenant["phone"], "13800000000")

    def test_contract_other_fees_default_into_bill_draft(self):
        with mysql_test_transaction():
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201")
                tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
                other_fees = [{"name": "网费", "amount": 50}, {"name": "卫生费", "amount": 20}]
                contract_id = db.add_contract(
                    tenant_id,
                    room_id,
                    "2026-07-01",
                    monthly_rent=800,
                    other_fee_details=json.dumps(other_fees, ensure_ascii=False),
                )

                result = execute_tool("bill_generate_draft", {
                    "contract_id": contract_id,
                    "month": "2026-07",
                })
                draft = result["data"]

        self.assertTrue(draft["success"])
        self.assertEqual(draft["draft"]["other_fee_details"], other_fees)
        self.assertEqual(draft["draft"]["other_fee"], 70)
        self.assertEqual(draft["draft"]["total_amount"], 870)

    def test_meter_reading_phrase_prefers_meter_workflow_over_contract_context(self):
        context = {
            "active_workflow": "contract_create",
            "contract_draft": {
                "building_id": 2,
                "building_name": "石潭布",
                "room_number": "301",
                "tenant_name": "阳慕华",
            },
        }
        data = {
            "prompt": "他6月份的水电是346 9150",
            "session_context": context,
        }

        intent = ai_orchestrator._detect_intent(data)
        route = ai_orchestrator._graph_route({"data": data, "prompt": data["prompt"], "pending_action_command": ""})
        meter_args = ai_orchestrator._meter_reading_fallback_args(data)

        self.assertEqual(intent["workflow"], "meter_reading")
        self.assertEqual(route, "meter_reading")
        self.assertEqual(len(meter_args), 2)
        self.assertEqual(meter_args[0]["room_number"], "301")
        self.assertEqual(meter_args[0]["month"], "2026-06")
        self.assertEqual({item["meter_type"] for item in meter_args}, {"water", "electric"})

    def test_eval_cases_cover_core_ai_workflows(self):
        case_path = os.path.join(os.path.dirname(__file__), "ai_eval_cases.json")
        with open(case_path, "r", encoding="utf-8") as f:
            cases = json.load(f)

        self.assertTrue(cases)
        for case in cases:
            intent = ai_orchestrator._detect_intent({"prompt": case["prompt"], "session_context": {}})
            self.assertEqual(intent["workflow"], case["workflow"], msg=case["prompt"])

    def test_memory_layers_and_business_knowledge_smoke(self):
        layers = build_memory_layers(
            session_context={
                "thread_id": "thread-1",
                "active_workflow": "contract_create",
                "room_number": "201",
                "tenant_name": "张三",
            },
            prompt="帮我新建合同，合同里要有户型，还能直接新建租户",
            intent={"workflow": "contract_create", "confidence": 0.98},
            workflow_state={"name": "contract_create", "status": "active"},
            tool_plan={"workflow": "contract_create", "steps": ["a", "b"]},
            pending_actions=[{"id": "1", "type": "create_contract", "label": "新建合同"}],
        )
        hits = search_business_knowledge("合同里要有户型，还能直接新建租户", top_k=2)

        self.assertIn("short_term", layers)
        self.assertIn("workflow_state", layers)
        self.assertIn("pending_actions", layers)
        self.assertTrue(hits)


if __name__ == "__main__":
    unittest.main()
