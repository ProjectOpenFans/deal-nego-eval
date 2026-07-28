from negoeval.llm.liveconfig import _spec


def test_qwen_preset_targets_coolwei_qwen36():
    spec = _spec({"provider": "qwen"}, {"COOLWEI_API_KEY": "test-key"})

    assert spec.base_url == "http://192.168.55.237:8000/v1"
    assert spec.model == "Qwen3.6-27B-NVFP4"
    assert spec.extra["extra_body"]["chat_template_kwargs"]["enable_thinking"] is False
    assert spec.trust_env is False


def test_deepseek_default_uses_official_flash_api_and_key_env():
    spec = _spec({"provider": "deepseek"}, {"DEEPSEEK_API_KEY": "test-key"})

    assert spec.name == "deepseek"
    assert spec.base_url == "https://api.deepseek.com"
    assert spec.model == "deepseek-v4-flash"
    assert spec.api_key == "test-key"
    assert spec.extra["reasoning_effort"] == "high"
    assert spec.extra["extra_body"]["thinking"]["type"] == "enabled"
    assert spec.default_headers == {}


def test_deepseek_flash_alias_uses_flash_model():
    spec = _spec({"provider": "deepseek-v4-flash"}, {"DEEPSEEK_API_KEY": "test-key"})

    assert spec.name == "deepseek_flash"
    assert spec.base_url == "https://api.deepseek.com"
    assert spec.model == "deepseek-v4-flash"


def test_deepseek_pro_alias_uses_pro_model():
    spec = _spec({"provider": "deepseek_pro"}, {"DEEPSEEK_API_KEY": "test-key"})

    assert spec.name == "deepseek_pro"
    assert spec.base_url == "https://api.deepseek.com"
    assert spec.model == "deepseek-v4-pro"


def test_deepseek_thinking_and_effort_can_be_overridden():
    spec = _spec(
        {"provider": "deepseek_pro", "thinking": False, "reasoning_effort": "max"},
        {"DEEPSEEK_API_KEY": "test-key"},
    )

    assert spec.extra["reasoning_effort"] == "max"
    assert spec.extra["extra_body"]["thinking"]["type"] == "disabled"
