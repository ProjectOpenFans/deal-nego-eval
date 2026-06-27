from negoeval.llm.liveconfig import _spec
from negoeval.llm.openai_provider import OpenAISDKProvider


def test_openai_provider_can_omit_temperature_kwargs():
    provider = OpenAISDKProvider(
        api_key="test-key",
        base_url="https://api.example.invalid/v1",
        model="test-model",
        omit_temperature=True,
    )

    assert provider._temperature_kwargs(0.3) == {}


def test_kimi_uses_official_moonshot_api_without_temperature():
    spec = _spec({"provider": "kimi"}, {"KIMI_API_KEY": "test-key"})

    assert spec.name == "kimi"
    assert spec.base_url == "https://api.moonshot.cn/v1"
    assert spec.model == "kimi-k2.6"
    assert spec.api_key == "test-key"
    assert spec.extra["extra_body"]["thinking"]["type"] == "enabled"
    assert spec.default_headers == {}
    assert spec.omit_temperature is True


def test_kimi_accepts_official_moonshot_key_env_name():
    spec = _spec({"provider": "kimi"}, {"MOONSHOT_API_KEY": "test-key"})

    assert spec.api_key == "test-key"


def test_glm52_uses_official_bigmodel_api_and_zai_key_env():
    spec = _spec({"provider": "glm52"}, {"ZAI_API_KEY": "test-key"})

    assert spec.name == "glm52"
    assert spec.base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert spec.model == "glm-5.2"
    assert spec.api_key == "test-key"
    assert spec.temperature == 1.0
    assert spec.extra["reasoning_effort"] == "medium"
    assert spec.extra["extra_body"]["thinking"]["type"] == "enabled"
    assert spec.default_headers == {}


def test_glm52_alias_and_reasoning_effort_can_be_overridden():
    spec = _spec(
        {"provider": "glm-5-2", "thinking": False, "reasoning_effort": "high"},
        {"ZHIPU_API_KEY": "test-key"},
    )

    assert spec.name == "glm52"
    assert spec.api_key == "test-key"
    assert spec.extra["reasoning_effort"] == "high"
    assert spec.extra["extra_body"]["thinking"]["type"] == "disabled"


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
