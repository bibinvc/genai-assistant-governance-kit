import json
import tempfile
import unittest
from pathlib import Path

from kit import guardrails
from kit.agent import Agent, Tools
from kit.ai_act import UseCase, screen
from kit.assistant import NOT_FOUND, Assistant
from kit.audit import AuditLog
from kit.providers import OfflineProvider, ScriptedProvider
from kit.workflow import EmailWorkflow, security_alerts

ROOT = Path(__file__).resolve().parent.parent
PROCS = ROOT / "data" / "procedures"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.out = Path(self.tmp.name)
        self.audit = AuditLog(self.out / "audit.jsonl")

    def tearDown(self):
        self.tmp.cleanup()


class GuardrailTests(Base):
    def test_masks_email_phone_iban_secret_and_restores(self):
        text = ("Contact claire@ex.fr ou 06 12 34 56 78, IBAN FR76 3000 6000 0112 3456 7890 189, "
                "clé sk-abcdefghijklmnopqrstuvwx")
        red = guardrails.redact(text)
        for value in ("claire@ex.fr", "06 12 34 56 78", "FR76 3000", "sk-abcdef"):
            self.assertNotIn(value, red.text)
        self.assertEqual(red.kinds(), {"EMAIL": 1, "TEL": 1, "IBAN": 1, "SECRET": 1})
        self.assertEqual(guardrails.restore(red.text, red.mapping), text)

    def test_same_value_gets_same_placeholder(self):
        red = guardrails.redact("a@b.fr puis encore a@b.fr")
        self.assertEqual(red.text, "[EMAIL_1] puis encore [EMAIL_1]")

    def test_card_numbers_need_a_valid_luhn_checksum(self):
        self.assertEqual(guardrails.redact("carte 4111 1111 1111 1111").kinds(), {"CARTE": 1})
        self.assertEqual(guardrails.redact("commande 1234 5678 9012 3456").count, 0)

    def test_french_social_security_number(self):
        self.assertEqual(guardrails.redact("NIR 1 85 05 78 006 084 36").kinds(), {"NIR": 1})

    def test_confidentiality_levels_by_provider(self):
        self.assertTrue(guardrails.allowed("C2", "external"))
        self.assertFalse(guardrails.allowed("C3", "external"))
        self.assertTrue(guardrails.allowed("C3", "offline"))
        self.assertFalse(guardrails.allowed("C4", "offline"))

    def test_answer_check_rejects_missing_or_unknown_sources(self):
        given = {"a.md"}
        self.assertEqual(guardrails.check_answer("Texte [source: a.md]", given)[0], True)
        self.assertEqual(guardrails.check_answer("Texte sans source", given)[0], False)
        self.assertEqual(guardrails.check_answer("Texte [source: b.md]", given)[0], False)


class AssistantTests(Base):
    def test_answers_with_source_and_transparency_notice(self):
        a = Assistant(PROCS, OfflineProvider(), self.audit).ask("Qui doit valider une commande urgente ?")
        self.assertIn("[source: commande-urgente.md]", a.text)
        self.assertIn(guardrails.TRANSPARENCY_NOTICE, a.text)
        self.assertTrue(a.verified)

    def test_refuses_out_of_scope(self):
        a = Assistant(PROCS, OfflineProvider(), self.audit).ask("Quel est le menu de la cantine vendredi ?")
        self.assertTrue(a.text.startswith(NOT_FOUND))

    def test_secret_document_is_never_indexed(self):
        a = Assistant(PROCS, OfflineProvider(), self.audit)
        self.assertNotIn("plan-continuite.md", {p.source for p in a.passages})

    def test_external_provider_never_sees_confidential_passages(self):
        provider = ScriptedProvider(["Les remises sont confidentielles [source: conditions-tarifaires.md]"])
        a = Assistant(PROCS, provider, self.audit).ask("remises de fin d'année négociées par fournisseur")
        sent = " ".join(provider.prompts)
        self.assertNotIn("conditions-tarifaires.md", sent)
        self.assertTrue(a.text.startswith(NOT_FOUND))

    def test_invented_source_from_the_model_is_blocked(self):
        provider = ScriptedProvider(["Le délai est de 30 jours [source: invente.md]"])
        a = Assistant(PROCS, provider, self.audit).ask("Sous combien de jours le fournisseur doit-il répondre ?")
        self.assertFalse(a.verified)
        self.assertTrue(a.text.startswith(NOT_FOUND))

    def test_personal_data_is_masked_before_the_model_and_in_the_audit_log(self):
        provider = ScriptedProvider(["Sous 5 jours ouvrés [source: litige-fournisseur.md]"])
        Assistant(PROCS, provider, self.audit).ask("Je suis paul@ex.fr : délai de réponse d'un litige fournisseur ?")
        self.assertNotIn("paul@ex.fr", provider.prompts[0])
        self.assertNotIn("paul@ex.fr", (self.out / "audit.jsonl").read_text(encoding="utf-8"))


class AgentTests(Base):
    def make(self, provider):
        assistant = Assistant(PROCS, provider, self.audit)
        tools = Tools(assistant, ROOT / "data" / "stock.csv", self.out / "tickets.jsonl")
        return Agent(provider, tools, self.audit)

    def test_scripted_tool_call_then_answer(self):
        provider = ScriptedProvider([
            json.dumps({"tool": "stock_level", "args": {"reference": "REF-2001"}}),
            json.dumps({"answer": "Rupture sur REF-2001."}),
        ])
        res = self.make(provider).run("stock REF-2001 ?")
        self.assertTrue(res["ok"])
        self.assertIn("0 en stock", res["steps"][0]["result"])
        self.assertIn("Outil stock_level", provider.prompts[1])

    def test_unknown_tool_stops_the_run(self):
        res = self.make(ScriptedProvider([json.dumps({"tool": "delete_database", "args": {}})])).run("x")
        self.assertFalse(res["ok"])
        self.assertIn("non autorisé", res["answer"])

    def test_bad_json_stops_the_run(self):
        self.assertFalse(self.make(ScriptedProvider(["pas du json"])).run("x")["ok"])

    def test_step_limit(self):
        call = json.dumps({"tool": "search_procedures", "args": {"query": "stock"}})
        res = self.make(ScriptedProvider([call] * 10)).run("x")
        self.assertFalse(res["ok"])
        self.assertEqual(len(res["steps"]), 4)

    def test_ticket_is_only_a_draft(self):
        res = self.make(OfflineProvider()).run("ouvrir un ticket : rupture REF-2001")
        ticket = json.loads((self.out / "tickets.jsonl").read_text(encoding="utf-8").splitlines()[0])
        self.assertEqual(ticket["status"], "brouillon à valider")
        self.assertTrue(res["ok"])

    def test_invalid_reference_is_rejected(self):
        provider = ScriptedProvider([json.dumps({"tool": "stock_level", "args": {"reference": "1; DROP"}}),
                                     json.dumps({"answer": "fin"})])
        res = self.make(provider).run("x")
        self.assertIn("Référence invalide", res["steps"][0]["result"])


class WorkflowTests(Base):
    def test_triage_masks_classifies_and_waits_for_approval(self):
        wf = EmailWorkflow(OfflineProvider(), self.out, self.audit)
        item = wf.triage(ROOT / "data" / "emails" / "email_02.txt")
        self.assertEqual(item["category"], "facture")
        self.assertEqual(item["status"], "en_attente")
        self.assertNotIn("FR76", item["masked_email"])
        self.assertEqual(len(item["security_alerts"]), 1)
        self.assertEqual(list((self.out / "outbox").iterdir()), [])
        out = wf.approve("email_02", "relecteur")
        self.assertTrue(out.exists())
        self.assertEqual(json.loads((self.out / "approval_queue" / "email_02.json").read_text())["status"], "approuve")

    def test_categories_of_sample_emails(self):
        wf = EmailWorkflow(OfflineProvider(), self.out, self.audit)
        cats = {p.stem: wf.triage(p)["category"] for p in sorted((ROOT / "data" / "emails").glob("*.txt"))}
        self.assertEqual(cats, {"email_01": "retard", "email_02": "facture", "email_03": "qualite", "email_04": "autre"})

    def test_bank_change_alert(self):
        self.assertEqual(len(security_alerts("Merci d'utiliser notre nouveau RIB")), 1)
        self.assertEqual(security_alerts("Votre commande est expédiée"), [])


class AiActTests(unittest.TestCase):
    def test_levels(self):
        self.assertEqual(screen(UseCase("x", emotion_recognition_workplace=True)).level, "interdit")
        self.assertEqual(screen(UseCase("x", domain="rh_recrutement")).level, "haut_risque")
        self.assertEqual(screen(UseCase("x", safety_component_of_product=True)).level, "haut_risque")
        self.assertEqual(screen(UseCase("x", interacts_with_people=True)).level, "transparence")
        self.assertEqual(screen(UseCase("x")).level, "minimal")

    def test_dates_after_the_digital_omnibus(self):
        self.assertIn("2 décembre 2027", screen(UseCase("x", domain="rh_recrutement")).date)
        self.assertIn("2 août 2028", screen(UseCase("x", safety_component_of_product=True)).date)

    def test_personal_data_adds_gdpr_action(self):
        s = screen(UseCase("x", interacts_with_people=True, personal_data=True))
        self.assertTrue(any("RGPD" in r for r in s.references))


if __name__ == "__main__":
    unittest.main()
