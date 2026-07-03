import json
import subprocess
import sys
from pathlib import Path


def test_build_eval_corpus_generates_tool_entries(tmp_path: Path) -> None:
    output = tmp_path / "corpus.json"
    result = subprocess.run(
        [
            sys.executable,
            "scripts/build_eval_corpus.py",
            "tests/fixtures/evals/basic-routing.json",
            "--output",
            str(output),
        ],
        check=True,
        capture_output=True,
        text=True,
    )

    status = json.loads(result.stdout)
    corpus = json.loads(output.read_text(encoding="utf-8"))

    assert status["ok"] is True
    assert {entry["tool_name"] for entry in corpus} == {"create_text", "create_group"}
    assert any("Create a text" in utterance for entry in corpus for utterance in entry["utterances"])
