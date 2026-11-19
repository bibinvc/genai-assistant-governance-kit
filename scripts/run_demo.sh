#!/usr/bin/env bash
# Runs the tests and every feature in offline mode (no API key, nothing leaves the machine)
# and copies the outputs to evidence/.
set -euo pipefail
cd "$(dirname "$0")/.."
export LLM_PROVIDER=offline
rm -rf out && mkdir -p out evidence

python3 -m unittest discover -s tests -v 2> evidence/tests.txt || { cat evidence/tests.txt; exit 1; }
{
  echo '$ python -m kit.cli ask "Que faire si un colis arrive endommagé ?"'
  python3 -m kit.cli ask "Que faire si un colis arrive endommagé ?"
  echo
  echo '$ python -m kit.cli ask "Quel est le menu de la cantine vendredi ?"'
  python3 -m kit.cli ask "Quel est le menu de la cantine vendredi ?"
} > evidence/assistant.txt
{
  echo '$ python -m kit.cli agent "Quel est le stock de REF-1002 ?"'
  python3 -m kit.cli agent "Quel est le stock de REF-1002 ?"
  echo
  echo '$ python -m kit.cli agent "Peux-tu ouvrir un ticket : le capteur REF-2001 est en rupture"'
  python3 -m kit.cli agent "Peux-tu ouvrir un ticket : le capteur REF-2001 est en rupture"
} > evidence/agent.txt
{
  echo '$ python -m kit.cli triage'
  python3 -m kit.cli triage
  echo
  echo '$ python -m kit.cli approve email_01 "Relecteur Achats"'
  python3 -m kit.cli approve email_01 "Relecteur Achats" | sed "s#$(pwd)/##"
  echo
  cat out/outbox/email_01.txt
} > evidence/workflow.txt
cp out/approval_queue/email_02.json evidence/approval_queue_example.json
python3 -m kit.cli screen > /dev/null && cp out/ai_act_screening.json evidence/
python3 -m kit.cli eval > /dev/null && cp out/eval.md evidence/
cp out/audit.jsonl evidence/audit_log_example.jsonl
tail -3 evidence/tests.txt
echo "done: see evidence/"
