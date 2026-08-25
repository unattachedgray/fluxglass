import sys,unittest
sys.path.insert(0,"src")
from fluxglass.i18n import get_language,set_language,state_text,t

class I18nTests(unittest.TestCase):
    def tearDown(self):set_language("ko")
    def test_korean_default_and_english_switch(self):
        set_language("ko"); self.assertEqual(t("quit"),"종료"); self.assertEqual(state_text("GPU-LED"),"GPU 중심")
        set_language("en"); self.assertEqual(t("quit"),"Quit"); self.assertEqual(state_text("GPU-LED"),"GPU-LED")
    def test_unknown_language_falls_back_to_korean(self):
        set_language("xx"); self.assertEqual(get_language(),"ko")
