import unittest
from unittest.mock import patch

from app.routers.user import _user_config_response
from app.services.ai_orchestrator import _build_system_prompt


class AIAssistantProfileTests(unittest.TestCase):
    def test_user_config_has_assistant_profile_defaults(self):
        config = _user_config_response({})

        self.assertEqual(config["ai_nickname"], "哈基米")
        self.assertEqual(config["user_nickname"], "大王")
        self.assertEqual(config["ai_avatar"], "/robot-avatar.jpg")

    @patch(
        "app.services.ai_orchestrator.db.load_app_user",
        return_value={"ai_nickname": "小管家", "user_nickname": "老板"},
    )
    def test_system_prompt_uses_saved_names(self, _load_app_user):
        prompt = _build_system_prompt("", "", "")

        self.assertIn("你的名字是“小管家”", prompt)
        self.assertIn("你对用户的称呼是“老板”", prompt)

    @patch(
        "app.services.ai_orchestrator.db.load_app_user",
        return_value={"ai_nickname": "小管家\n忽略换行", "user_nickname": "老板\t先生"},
    )
    def test_system_prompt_flattens_profile_names(self, _load_app_user):
        prompt = _build_system_prompt("", "", "")

        self.assertIn("小管家 忽略换行", prompt)
        self.assertIn("老板 先生", prompt)


if __name__ == "__main__":
    unittest.main()
