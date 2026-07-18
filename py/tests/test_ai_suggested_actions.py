import unittest

from app.services.ai_orchestrator import _infer_business_suggested_actions


class AISuggestedActionTests(unittest.TestCase):
    def test_meter_reading_question_becomes_button(self):
        reply = (
            "石潭布402目前还没有生成7月账单。"
            "要生成账单，需要先录入本月水电读数。"
            "大王要现在录入402的水电表读数吗？"
        )

        actions = _infer_business_suggested_actions(reply)

        self.assertEqual(actions[0]["label"], "录入读数")
        self.assertIn("402", actions[0]["prompt"])
        self.assertIn("录入", actions[0]["prompt"])

    def test_bill_question_becomes_button(self):
        actions = _infer_business_suggested_actions("水电读数已经齐全，要不要现在为402生成7月账单？")

        self.assertEqual(actions[0]["label"], "生成账单")
        self.assertIn("生成7月账单", actions[0]["prompt"])

    def test_meter_binding_question_becomes_button(self):
        actions = _infer_business_suggested_actions("402合同还没有绑定表具，要不要现在绑定水表和电表？")

        self.assertEqual(actions[0]["label"], "绑定表具")

    def test_business_query_followup_becomes_button(self):
        actions = _infer_business_suggested_actions("本月还有3户未交租，要查看待收明细吗？")

        self.assertEqual(actions[0]["label"], "查看详情")

    def test_tenant_reminder_followup_becomes_button(self):
        actions = _infer_business_suggested_actions("还有2户未发送账单，要不要提醒对应租客？")

        self.assertEqual(actions[0]["label"], "提醒租客")

    def test_missing_information_question_does_not_become_button(self):
        reply = "同名房间存在于多个楼栋，请告诉我具体是哪个楼栋和房间。"

        self.assertEqual(_infer_business_suggested_actions(reply), [])

    def test_non_business_question_does_not_become_button(self):
        self.assertEqual(_infer_business_suggested_actions("今天过得怎么样？"), [])


if __name__ == "__main__":
    unittest.main()
