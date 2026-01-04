import json

from app.services.telegram import safe_log_extra


def test_safe_log_extra_serializes_nested_and_non_primitives():
    nested = {"a": {"b": [1, 2]}, "list": [{"x": 1}]}
    sample_object = object()
    extra = {
        **nested,
        "num": 5,
        "none": None,
        "flag": True,
        sample_object: "value",  # non-string key
        "obj": sample_object,
        "tuple": (1, 2),
        "set": {"x", "y"},
    }

    result = safe_log_extra(extra)

    assert result["a"] == json.dumps(nested["a"], default=str, separators=(",", ":"))
    assert result["list"] == json.dumps(nested["list"], default=str, separators=(",", ":"))
    assert result["num"] == 5
    assert result["none"] is None
    assert result["flag"] is True
    assert result["obj"] == str(sample_object)
    assert result["tuple"] == json.dumps((1, 2), default=str, separators=(",", ":"))
    assert result["set"] == json.dumps({"x", "y"}, default=str, separators=(",", ":"))
    # key derived from non-string should be stringified
    assert str(sample_object) in result
    assert all(isinstance(key, str) for key in result.keys())
