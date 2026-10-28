
import pytest

from agents.diagnosis_agent import _extract_json_object


def test_extracts_plain_json():
    content = '{"diagnoses": []}'

    assert _extract_json_object(content) == '{"diagnoses": []}'


def test_extracts_json_from_markdown_fence():
    content = (
        "```json\n"
        '{"diagnoses": []}\n'
        "```"
    )

    assert _extract_json_object(content) == '{"diagnoses": []}'


def test_extracts_json_surrounded_by_explanatory_text():
    content = (
        "Here is the diagnosis:\n"
        '```json\n{"diagnoses": []}\n```\n'
        "That concludes the analysis."
    )

    assert _extract_json_object(content) == '{"diagnoses": []}'


def test_rejects_response_without_json_object():
    with pytest.raises(ValueError, match="contains no JSON object"):
        _extract_json_object("The diagnosis could not be determined.")
