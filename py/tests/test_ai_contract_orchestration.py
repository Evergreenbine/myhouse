import os
import json
import tempfile
import unittest
from unittest.mock import patch

import local_db as db
from app.services import ai_orchestrator
from app.services import rental_dispatcher
from app.services.skill_executor import _contract_create_form_action, execute_tool


BUILDINGS = [
    {"id": 2, "name": "石潭布"},
    {"id": 3, "name": "益民路"},
]


class ContractOrchestrationTests(unittest.TestCase):
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


class ContractPersistenceTests(unittest.TestCase):
    def test_ai_thread_state_and_trace_persist_in_local_db(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = db.DB_PATH
            db.DB_PATH = os.path.join(temp_dir, "local.db")
            try:
                db.init()
                db.save_ai_thread_state("thread-test", {"session_context": {"active_workflow": "contract_create"}})
                db.append_ai_trace("thread-test", "route", {"next": "contract_form"})

                state = db.load_ai_thread_state("thread-test")
                traces = db.load_ai_trace("thread-test")
            finally:
                db.DB_PATH = original_path

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
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = db.DB_PATH
            db.DB_PATH = os.path.join(temp_dir, "local.db")
            try:
                db.init()
                building_id = db.add_building("测试楼栋")
                room_id = db.add_room(building_id, "201")
                tenant_id = db.add_tenant("测试租客", building_id=building_id, room_id=str(room_id))
                db.add_contract(tenant_id, room_id, "2026-07-01", monthly_rent=800)
                self.assertEqual(db.get_room(room_id)["status"], "rented")
            finally:
                db.DB_PATH = original_path

    def test_contract_other_fees_default_into_bill_draft(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            original_path = db.DB_PATH
            db.DB_PATH = os.path.join(temp_dir, "local.db")
            try:
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
            finally:
                db.DB_PATH = original_path

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


if __name__ == "__main__":
    unittest.main()
