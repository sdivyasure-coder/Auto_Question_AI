import pandas as pd

from generator import GeneratorConfig, ai_generate_questions, get_questions


def write_csv(path):
    df = pd.DataFrame(
        [
            {"chapter": 1, "question": "Explain TCP fundamentals", "mark": 2, "subject": "CNCC"},
            {"chapter": 1, "question": "Describe UDP characteristics", "mark": 2, "subject": "CNCC"},
            {"chapter": 1, "question": "Analyze routing protocols", "mark": 7, "subject": "CNCC"},
            {"chapter": 1, "question": "Discuss congestion control", "mark": 7, "subject": "CNCC"},
            {"chapter": 1, "question": "Explain network security models", "mark": 15, "subject": "CNCC"},
        ]
    )
    df.to_csv(path, index=False)


def test_get_questions_regular_warnings(tmp_path):
    csv_path = tmp_path / "qb.csv"
    write_csv(csv_path)
    config = GeneratorConfig()

    result = get_questions(str(csv_path), "CNCC", "CNCC", "regular", config)
    assert result["subject"] == "CNCC"
    assert result["parts"]["A"]["qs"]
    assert result["warnings"]


def test_ai_generate_questions(tmp_path):
    csv_path = tmp_path / "qb.csv"
    write_csv(csv_path)
    output = ai_generate_questions(str(csv_path), "CNCC", 1, 2, 3)
    assert len(output) == 3
